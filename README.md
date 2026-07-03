# n8n Python Task Runner Windows Fix

## Tested

- Windows 11
- Python 3.13
- n8n 2.8.4

This repository contains a fix for running the **n8n Python Task Runner on Windows**.
**WARNING! Read installation guide - need additional actions!**

## Problem

Can't execute Python Code and warning on start:
```
Failed to start Python task runner in internal mode because its virtual environment is missing from this system.
Launching a Python runner in internal mode is intended only for debugging and is not recommended for production.
Users are encouraged to deploy in external mode.
```

The original implementation uses POSIX file descriptor APIs (`os.read()`, `os.write()`, `fileno()`) for IPC between the runner and its child process. These APIs are not compatible with `multiprocessing.Connection` on Windows, causing Python tasks to fail with errors such as:

```
Task subprocess exited with code 1
OSError: [Errno 9] Bad file descriptor
```

## Solution

The IPC implementation was rewritten to use the cross-platform `multiprocessing.Connection` API:

* `Connection.send_bytes()`
* `Connection.recv_bytes()`

The existing message format (4-byte length prefix + JSON payload) is preserved, so the external protocol remains unchanged while making the Python Task Runner work correctly on Windows.

**NO DOCKER NEEDED** =)

<img width="1860" height="750" alt="image" src="https://github.com/user-attachments/assets/23160112-a545-4177-8767-c575205ca3aa" />

<img width="1888" height="818" alt="image" src="https://github.com/user-attachments/assets/7a615a1b-daf9-4923-a71f-b56db9bfc250" />

