# n8n ↔ Claude MCP connection — status and how it was made to work

Date: 2026-07-07
Status: **MCP connection works.** A separate n8n bug with the "Available in MCP" toggle was still open (see "Current blocker" below) — now fixed, see `n8n-mcp-toggle-fix.md`.

## Goal

Connect a locally installed n8n instance (Windows, run via `npx`/`npm`) to Claude over MCP, so Claude can directly search/run (and eventually create) workflows.

## Environment

- OS: Windows (device "asus-vivobook")
- n8n: run locally via `npx`/`npm` (`n8n start`), port 5678
- Node.js: v22.22.3 / v20.20.2 (in different processes), npx 10.9.8
- App: Claude (Cowork desktop app), NOT the classic "Claude Desktop"
- The actual app config file (important — not `%APPDATA%\Claude\...`, but):
  `C:\Users\PC\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`
  (the app is installed as a packaged/MSIX app, so the usual `%APPDATA%` path is not the right one)

## ✅ WORKING CONFIGURATION (final)

In the config file above, under the `mcpServers` key:

```json
{
  "mcpServers": {
    "n8n-mcp": {
      "command": "C:\\Users\\PC\\AppData\\Roaming\\npm\\mcp-remote.cmd",
      "args": [
        "http://localhost:5678/mcp-server/http",
        "--header",
        "Authorization: Bearer <ACCESS_TOKEN>"
      ]
    }
  }
}
```

Plus mandatory preparation steps:

1. In n8n: Settings → Instance-level MCP → enable, Connection details → **Access Token** tab → generate a token (paste it into the config above instead of `<ACCESS_TOKEN>`).
2. The `mcp-remote` package is installed **globally** (not via `npx -y` on every run!):
   ```powershell
   npm install -g mcp-remote
   ```
   The command in the config points to the direct path of the globally installed binary (`C:\Users\PC\AppData\Roaming\npm\mcp-remote.cmd`), instead of plain `"npx"` or `"mcp-remote"` — this works around two bugs at once (see below).
3. Fully restart Claude Desktop via the tray icon (Quit → reopen) after any config change.
4. **Important:** the connection is only picked up in **new** conversations/chats — a chat that was already open when the tools weren't yet available won't pick them up even after reconnecting. Always test in a fresh chat.

An ngrok tunnel is **not needed** for this approach — the `mcp-remote` process runs locally on the user's machine, launched by the same Claude Desktop app (via `mcpServers`), so it talks to n8n directly over `localhost` rather than from the cloud.

## How the working setup was reached — three bugs found and worked around

### Bug 1: the official cloud connector "n8n" (Directory → n8n) is unstable for self-hosted instances

- Requires a URL in the form `https://<domain>/mcp-server/http` (not just the domain) — a common startup error: "Server URL doesn't match expected format".
- Even with the correct URL, the OAuth handshake breaks: `Couldn't register with n8n's sign-in service` (`ofid_...`). Based on n8n community reports, this is either a Claude bug (not attaching the Bearer token after OAuth) or a proxy header issue (`X-Forwarded-For`) — either way, it's currently unstable for self-hosted + ngrok tunnel setups. **This path was abandoned.**

### Bug 2: the Claude app incorrectly substitutes a path containing a space on Windows

- With `"command": "npx"`, the app resolves the full path itself (`C:\Program Files\nodejs\npx.cmd`) and passes it to `cmd.exe` **without quotes** → the command breaks at the space: `'C:\Program' is not recognized...`.
- **Workaround:** specify a ready-made absolute path with no spaces in `command` (`C:\Users\PC\AppData\Roaming\npm\mcp-remote.cmd` — there are no spaces under `AppData\Roaming\npm`), or wrap everything via `cmd /c "..."` (works, but is a more fragile option — see Bug 3).

### Bug 3: corrupted `npx` cache + a quoting bug when wrapping in `cmd /c "string"`

- Every `npx -y <package>` re-downloads/unpacks the package into a temporary cache at `%LOCALAPPDATA%\npm-cache\_npx\...`. On this machine, unpacking periodically failed (`EPERM: operation not permitted, unlink`, `TAR_ENTRY_ERROR`), leaving the package partially unpacked → `Cannot find module ... is-promise.js`, `Cannot find module './db.json'` on the next run.
- Separately: if the whole command is wrapped in a single string like `cmd /c "npx ... --header \"Authorization: Bearer TOKEN\""`, the nested quotes don't survive `cmd.exe`'s re-parsing — the header gets truncated (`Warning: ignoring invalid header argument: "Authorization:`), so `mcp-remote` doesn't see the token and tries to start OAuth on its own (which fails on n8n's side with `Internal Server Error` when exchanging the code for a token — a separate n8n bug that simply wasn't hit in the final version, since the OAuth path is no longer used).
- **Workaround (final):** install `mcp-remote` globally (`npm install -g mcp-remote`) — this removes the need to rebuild/unpack the `_npx` cache on every run — and specify the direct path to the binary plus arguments as a separate JSON array (not a single string via `cmd /c`), to avoid the quote re-parsing issue.

## How it was confirmed the connection genuinely works (not just "looks plausible")

1. Independent check via **MCP Inspector** (`npx @modelcontextprotocol/inspector`, Streamable HTTP, `http://localhost:5678/mcp-server/http` + Bearer token) — connected instantly, `tools/list` returned real tools (`search_workflows`, `execute_workflow`, `get_workflow_details`, etc.). This proved the n8n MCP server itself was fully functional, independent of Claude.
2. After the final configuration — in a **new** chat, Claude actually loaded the `n8n-mcp` tools and called `search_workflows`. The set of tool names Claude listed in that chat **exactly matched** what MCP Inspector had shown — i.e. this wasn't the model making things up, but a real server response.

## Blocker at the time (not our configuration — a bug in n8n itself)

`search_workflows` returned an empty list, even though a test workflow ("Test") genuinely existed and was visible in the n8n UI. Cause — a confirmed, open n8n bug:

- The n8n UI has an **"Enable MCP"** / "Available in MCP" toggle / context-menu item for workflows.
- The toggle could be turned on, but when navigating into the workflow itself, into its settings, or **on page refresh (F5)** — the state reset back to off.
- Matches the open GitHub issue **n8n-io/n8n #25987** — "Available in MCP toggle not persisting", status at the time of writing was unresolved (needs-info).
- As long as the toggle didn't persist, no workflow could show up in the list visible via `search_workflows` — this was a limitation on n8n's side, not an MCP connection or Claude configuration issue.

## Ideas for how to fix this further

- UPDATE: Fixed — the solution is described in `n8n-mcp-toggle-fix.md`

## Values used (placeholders instead of secrets)

- Local n8n MCP endpoint: `http://localhost:5678/mcp-server/http`
- Ngrok domain (only used for the cloud connector attempt, which was abandoned): `https://prewar-judo-lucid.ngrok-free.dev`
- App config file: `C:\Users\PC\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`
- Path to the global `mcp-remote`: `C:\Users\PC\AppData\Roaming\npm\mcp-remote.cmd`
- n8n Access Token — generated at Settings → Instance-level MCP → Connection details → Access Token (not copied into this file for security reasons; the config needs to be updated if the token is regenerated)
