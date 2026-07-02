# Investigation: Running the n8n 2.8.4 Python Runner on Windows

## Current Status

**The root cause has been identified, and a minimal cross-platform patch has been implemented.**

The issue was not caused by `spawn`, `ForkServerProcess`, child process startup, or user Python code. The incompatibility was in the result-transfer mechanism between the child process and the parent runner process: the code used `Connection.fileno()` together with POSIX APIs `os.read()` / `os.write()`. This works on Linux/macOS, but on Windows it fails with `OSError(9, 'Bad file descriptor')`.

The fix moves IPC to the cross-platform `multiprocessing.Connection` API: `send_bytes()` and `recv_bytes()`. The JSON message format and the existing 4-byte length prefix are preserved.

---

## Initial Problem

After installing `n8n` through `npm`, application startup showed:

```text
Failed to start Python task runner in internal mode. because Python 3 is missing from this system.
```

Later, after creating a `python3` alias, the message changed to:

```text
Failed to start Python task runner in internal mode. because its virtual environment is missing from this system.
```

When executing a **Python Code** node in the n8n UI, the error was:

```text
Python runner unavailable: Virtual environment is missing from this system
```

## Why the Investigation Changed Direction

At first, the suspected causes were:

- Python was missing;
- `python3` was missing;
- the Python version was wrong;
- the virtual environment was missing.

After checking the environment, it became clear that:

- Python was installed;
- `python3` was available;
- the virtual environment could be created manually;
- the error was not about system Python itself, but about n8n's internal Python Runner.

From that point, the investigation moved to the Python Runner source code.

------------------------------------------------------------------------

# Investigation Timeline

1. The `n8n` source repository was cloned.
2. The following files were inspected:
   - `README.md`
   - `justfile`
3. A Python virtual environment was created.
4. `uv` was installed.
5. The following command was run:

```bash
python -m uv sync --group dev
```

After this, the runner started launching.

------------------------------------------------------------------------

# Source Code Investigation

The following Windows-related limitations were found.

## `task_state.py`

### Before

```python
from multiprocessing.context import ForkServerProcess
```

### After

```python
from multiprocessing.context import SpawnProcess as ForkServerProcess
```

Reason:

`ForkServerProcess` is not available on Windows and was used only as a type.

------------------------------------------------------------------------

## `task_executor.py`

### Before

```python
from multiprocessing.context import ForkServerProcess
```

Changed to:

```python
from multiprocessing.context import SpawnProcess as ForkServerProcess
```

Also, this:

```python
MULTIPROCESSING_CONTEXT = multiprocessing.get_context("forkserver")
```

was changed to:

```python
MULTIPROCESSING_CONTEXT = multiprocessing.get_context("spawn")
```

Reason:

Windows does not support `forkserver`, but it does support `spawn`.

------------------------------------------------------------------------

## `main.py`

An artificial Windows block was found:

```python
if platform.system() == "Windows":
    print(ERROR_WINDOWS_NOT_SUPPORTED, file=sys.stderr)
    sys.exit(1)
```

For investigation purposes, this block was temporarily removed. After that, the runner continued launching.

------------------------------------------------------------------------

# Next Stage

After removing those limitations, the runner reached real startup for the first time and printed:

```text
Environment variable N8N_RUNNERS_GRANT_TOKEN is required
```

This meant:

- the runner itself was working;
- it now needed to authenticate through the Task Broker.

------------------------------------------------------------------------

# Task Broker Authentication Investigation

The following files were inspected:

- `task-broker-auth.controller.js`
- `task-broker-auth.service.js`
- `task-broker-server.js`

Findings:

- authentication uses a two-step flow;
- first, an `authToken` must be provided;
- then a one-time `GRANT_TOKEN` is issued;
- if `authToken` is missing, n8n generates a random token at every startup.

------------------------------------------------------------------------

# Capturing the Token

The following environment variable was set:

```powershell
$env:N8N_RUNNERS_AUTH_TOKEN="6a5bcb3d9a4d5ef8b1d44d53bcb67e81"
```

After that, a working `GRANT_TOKEN` was obtained through:

```http
POST /runners/auth
```

------------------------------------------------------------------------

# Running a Custom Runner

After setting:

- `N8N_RUNNERS_GRANT_TOKEN`
- `N8N_RUNNERS_TASK_BROKER_URI`
- `PYTHONPATH`

and launching:

```powershell
.\.venv\Scripts\python.exe src\main.py
```

the runner started successfully.

Observed logs:

```text
INFO Starting runner...
INFO Connected to broker
INFO Registered with broker
```

This proved that, after minimal changes, the Python Runner could start and register on Windows.

------------------------------------------------------------------------

# State at That Point

Even though the custom runner registered successfully, executing a Python Code node still failed in the n8n UI with:

```text
Python runner unavailable: Virtual environment is missing from this system
```

Reason:

- the `n8n` instance installed through `npm` was still trying to start **its own built-in Internal Python Runner**;
- the built-in runner looked for its own `@n8n/task-runner-python` directory inside the installed `n8n` package;
- the manually built runner lived in a different directory and was not used automatically.

------------------------------------------------------------------------

# What Was Proven

Python Runner can be launched on Windows after minimal changes.

The runner can:

- start;
- connect to the Task Broker;
- register successfully.

------------------------------------------------------------------------

# New Investigation Results (2026-07-02)

## Status

The Windows version of Python Task Runner was brought to a working state up to user-code execution.

At that point, the sequence was:

1. Runner starts.
2. Runner connects to the Task Broker.
3. Runner registers.
4. Runner accepts a task.
5. Runner creates a child process.
6. User Python code executes successfully.
7. The error happens only while sending the result back to the parent process.

---

## Confirmed Findings

### The Runner Is Functioning

Logs showed:

```text
Connected to broker
Registered with broker
Accepted task
Received task
SUBPROCESS STARTED
```

---

### User Code Executes

Test code:

```python
print("Hello!")
return [{"json": {"ok": True}}]
```

Logs showed:

```text
[user code] Hello!
```

Therefore, the failure happens after user-code execution.

---

### `_put_result()` Is Called

Added diagnostics showed:

```text
ABOUT TO CALL _put_result
PUT_RESULT: json
PUT_RESULT: encoded
PUT_RESULT: write length
```

This means the result was serialized successfully.

---

### Error Localization

The error occurred during the first call to:

```python
TaskExecutor._write_bytes(write_fd, length_bytes)
```

Diagnostics showed:

```text
ENTER _write_bytes fd=524 len=4
EXCEPTION: OSError(9, 'Bad file descriptor')
```

---

## Confirmed Root Cause

At that point, inter-process data transfer was implemented as follows.

Pipe creation:

```python
read_conn, write_conn = multiprocessing_context.Pipe(duplex=False)
```

Write:

```python
write_fd = write_conn.fileno()
os.write(write_fd, ...)
```

Read:

```python
read_fd = read_conn.fileno()
os.read(read_fd, ...)
```

This mechanism works on Linux/macOS.

On Windows, this call:

```python
os.write(write_conn.fileno(), ...)
```

fails with:

```text
OSError(9, 'Bad file descriptor')
```

So the problem was not in user code and not in multiprocessing itself. It was caused by using POSIX APIs (`os.read` / `os.write`) on top of `multiprocessing.Connection`.

---

## `PipeReader`

It was also confirmed that result reading used the same incompatible mechanism.

File:

```text
src/pipe_reader.py
```

Method:

```python
PipeReader._read_exact_bytes()
```

used:

```python
os.read(fd, ...)
```

where `fd` was also obtained through:

```python
read_conn.fileno()
```

Even if writing were fixed, reading would still remain incompatible with Windows.

---

## Conclusion

The root cause was localized.

To fully support Windows, the following had to be replaced:

- `os.write()`
- `os.read()`
- `Connection.fileno()`

with a cross-platform data exchange mechanism using the `multiprocessing.Connection` API: `send_bytes()`, `recv_bytes()`, or an equivalent implementation.

The rest of Python Task Runner already worked on Windows: registration, receiving tasks, starting processes, and executing user code.

------------------------------------------------------------------------

# Final IPC Fix (2026-07-02)

## Patch Goal

After localizing the root cause, it became clear that the fix should not target runner startup, `spawn`, or user code. It should target only the internal result-transfer mechanism between processes.

Patch requirements:

- preserve the existing JSON message format;
- preserve the 4-byte big-endian length prefix;
- do not change the public Python Task Runner API;
- preserve Linux/macOS compatibility;
- add Windows support;
- remove POSIX file descriptor usage for `multiprocessing.Connection`.

## Chosen Solution

Instead of:

```python
write_fd = write_conn.fileno()
os.write(write_fd, ...)
```

and:

```python
read_fd = read_conn.fileno()
os.read(read_fd, ...)
```

the patch uses the cross-platform API of `multiprocessing.Connection` itself:

```python
write_conn.send_bytes(...)
read_conn.recv_bytes()
```

Important detail: `send_bytes()` / `recv_bytes()` were chosen instead of `send()` / `recv()` because `send()` / `recv()` work with pickle objects, while the runner already has its own JSON protocol. The new code sends raw bytes directly and does not change the data format.

## Write-Side Change

Before the fix, `_put_result()` and `_put_error()` received a file descriptor:

```python
TaskExecutor._put_result(write_conn.fileno(), result, print_args)
TaskExecutor._put_error(write_conn.fileno(), e, stderr, print_args)
```

The data was then written to the pipe with `os.write()` in two steps:

```python
TaskExecutor._write_bytes(write_fd, length_bytes)
TaskExecutor._write_bytes(write_fd, data)
```

After the fix, those methods receive the `Connection` object itself:

```python
TaskExecutor._put_result(write_conn, result, print_args)
TaskExecutor._put_error(write_conn, e, stderr, print_args)
```

Serialization remains unchanged:

```python
data = json.dumps(message, default=str, ensure_ascii=False).encode("utf-8")
```

The message frame is still built logically the same way:

```python
length_bytes = len(data).to_bytes(PIPE_MSG_PREFIX_LENGTH, "big")
```

but it is sent with one cross-platform call:

```python
write_conn.send_bytes(length_bytes + data)
```

After sending, the connection is closed through the `Connection` API:

```python
write_conn.close()
```

`os.close(write_fd)` is no longer used.

## Read-Side Change

Before the fix, `PipeReader` was created with a file descriptor:

```python
pipe_reader = PipeReader(read_conn.fileno(), read_conn)
```

and read data through:

```python
chunk = os.read(fd, n - offset)
```

After the fix, `PipeReader` receives only the `Connection` object:

```python
pipe_reader = PipeReader(read_conn)
```

Reading is performed through:

```python
framed_data = read_conn.recv_bytes()
```

The data is then parsed using the same internal format:

1. the first 4 bytes are interpreted as the JSON message length;
2. the remaining bytes are treated as the JSON payload;
3. the actual payload length is checked against the declared length;
4. JSON is decoded and passed through the existing structural validation.

Added validations:

- messages shorter than 4 bytes are rejected;
- zero or negative declared lengths are rejected;
- declared/factual length mismatch is rejected;
- messages without `result` or `error` are rejected by the existing validation.

## Why the Message Format Was Preserved

Although `Connection.send_bytes()` already has its own transport framing, the existing 4-byte length prefix was intentionally kept.

Reasons:

- this is a minimal patch;
- the runner's internal JSON protocol does not change;
- the existing `message_size` value is preserved as the JSON payload size;
- regression risk on Linux/macOS is reduced;
- the fix affects only transport, not message semantics.

## Removing Temporary Diagnostics

During investigation, these temporary diagnostic messages were added:

```text
SUBPROCESS STARTED
ABOUT TO CALL _put_result
PUT_RESULT: json
PUT_RESULT: encoded
PUT_RESULT: write length
ENTER _write_bytes fd=...
```

After implementing the fix, they were removed because:

- the root cause had already been confirmed;
- the messages polluted runner logs;
- part of the diagnostics referred to the removed POSIX `_write_bytes()` path.

Unused imports `platform` and `ERROR_WINDOWS_NOT_SUPPORTED` were also removed. The obsolete `ERROR_WINDOWS_NOT_SUPPORTED` constant was removed from `constants.py`, because Windows is no longer artificially blocked.

## Changed Files

Main changes were made in:

- `packages/@n8n/task-runner-python/src/pipe_reader.py`
- `packages/@n8n/task-runner-python/src/task_executor.py`
- `packages/@n8n/task-runner-python/src/main.py`
- `packages/@n8n/task-runner-python/src/constants.py`
- `packages/@n8n/task-runner-python/tests/unit/test_task_executor.py`

## Test Updates

Old unit tests covered the low-level POSIX path by mocking `os.read()` and `os.write()`.

After the fix, tests were moved to the new model:

- successful result message reading through `recv_bytes()`;
- successful error message reading through `recv_bytes()`;
- error on too-short messages;
- error on zero declared length;
- error on declared/factual length mismatch;
- successful sending through `send_bytes()`;
- error propagation from `send_bytes()`;
- live round-trip through `MULTIPROCESSING_CONTEXT.Pipe(duplex=False)`, when the environment allows pipe creation.

The live round-trip test was skipped in the current Windows sandbox because the environment blocks Windows named pipe creation with:

```text
PermissionError: [WinError 5] Access is denied
```

This is a test environment restriction, not a patch issue.

## Verification

In this environment, `uv` was not available in `PATH`, so checks were run through the package's local virtual environment:

```powershell
.\.venv\Scripts\pytest.exe tests/unit/test_task_executor.py
.\.venv\Scripts\ruff.exe check src/constants.py src/main.py src/pipe_reader.py src/task_executor.py tests/unit/test_task_executor.py
.\.venv\Scripts\ruff.exe format --check src/constants.py src/main.py src/pipe_reader.py src/task_executor.py tests/unit/test_task_executor.py
.\.venv\Scripts\ty.exe check src/
```

Results:

- focused unit tests in `test_task_executor.py`: `12 passed, 1 skipped`;
- `ruff check`: passed;
- `ruff format --check`: passed;
- `ty check src/`: only errors for the missing optional package `sentry_sdk` remained.

The `ty` errors are in `src/sentry.py` and are unrelated to the IPC patch:

```text
Cannot resolve imported module `sentry_sdk`
Cannot resolve imported module `sentry_sdk.integrations.logging`
Cannot resolve imported module `sentry_sdk.profiler`
```

Full `pytest` in the current sandbox was also not representative because some unrelated tests failed due to Windows permission issues with temporary files and named pipes.

## Final State

After the patch, the execution path is:

1. Runner starts on Windows.
2. Runner connects to the Task Broker.
3. Runner registers.
4. Runner accepts a task.
5. Runner creates a child process through `spawn`.
6. User Python code executes.
7. The child process serializes the result to JSON.
8. The result is sent to the parent process through `Connection.send_bytes()`.
9. The parent process reads the result through `Connection.recv_bytes()`.
10. JSON is validated and returned to the normal n8n pipeline.

The main difference from the broken version: IPC no longer uses `Connection.fileno()`, `os.write()`, or `os.read()`.

The minimal patch preserves the Python Task Runner architecture and changes only the transport layer between processes.
