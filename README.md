# n8n Python Task Runner Windows Fix

This repository contains a fix for running the **n8n Python Task Runner on Windows**.

## Problem

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
