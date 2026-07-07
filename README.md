# n8n 2.8.4 - Windows Fixes

Personal fork of n8n with fixes for issues hit while running n8n **locally on Windows**. This `main` README is a running index — every fix lives in its own branch with a full write-up; this page just gives the short version and links out.

> Add a new `## <emoji> <Fix title>` section below whenever a new fix branch is created, following the same template.

## Fixes

### 🐍 Python Task Runner on Windows

**Branch:** `fix/python-task-runner-windows`
**Tested:** Windows 11 · Python 3.13 · n8n 2.8.4

- **Problem:** Python Code nodes couldn't execute; n8n warned on startup that the Python task runner's virtual environment was missing and that internal mode is debugging-only. Root cause: the runner's IPC with its child process used POSIX file-descriptor APIs (`os.read()`, `os.write()`, `fileno()`), which aren't compatible with `multiprocessing.Connection` on Windows — tasks failed with `OSError: [Errno 9] Bad file descriptor`.
- **Fix:** rewrote the IPC layer to use the cross-platform `multiprocessing.Connection.send_bytes()` / `recv_bytes()` API. The wire format (4-byte length prefix + JSON payload) is unchanged, so nothing external breaks.
- **No Docker required.**
- **Status:** ✅ working, see branch for full README + screenshots.

### 🔌 "Available in MCP" Toggle Persistence

**Branch:** `fix/mcp-toggle-persistence`
**Tested:** Windows 11 · n8n 2.8.4
**Related upstream issue:** [n8n-io/n8n#25987](https://github.com/n8n-io/n8n/issues/25987)

- **Problem:** the "Available in MCP" workflow toggle could be turned on with no error, but silently reset to off whenever the workflow was re-fetched — navigating into it, reopening its settings, or refreshing (F5). As a result, `search_workflows` and other n8n MCP tools never saw the workflow.
- **Root cause:** `WorkflowService.update()` reactivates any *active* workflow whenever its `settings` change, to refresh its live triggers/webhooks — but this fires for **any** settings key, including `availableInMCP`, which is pure metadata and doesn't affect trigger behavior at all. If that reactivation fails for any reason, the workflow gets silently **unpublished**, which makes MCP access look disabled even though `availableInMCP` itself was still `true` in the database.
- **Fix:** `availableInMCP` is now excluded from the check that decides whether a settings change should trigger reactivation. Also fixed a related staleness bug: the `toggle-access` endpoint now returns `checksum`, so the editor's cached workflow checksum doesn't go stale after toggling access from the workflow list.
- **Status:** ✅ working, confirmed via MCP `search_workflows`. See branch for full README + list of changed files.


