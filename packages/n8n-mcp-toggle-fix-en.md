# Fix: "Available in MCP" toggle not persisting

Date: 2026-07-07
Related bug: n8n-io/n8n **#25987** — "Available in MCP toggle not persisting"

## Symptoms (how it was reproduced)

The "Available in MCP" toggle could be turned on (the request goes through, no error), but the state reset back to off after any of the following actions:

- navigating into the workflow itself from the list;
- reopening the workflow's settings;
- refreshing the page (F5).

Because of this, `search_workflows` in n8n's MCP tools always returned an empty list, even when the test workflow was published and visibly present in the UI.

## Root cause

In `workflow.service.ts` (`WorkflowService.update`) there's a mechanism: if `settings` change on an **active (published)** workflow, the service automatically runs it through a deactivate → reactivate cycle (`activateWorkflow`) to apply the new settings to the already-running triggers/webhooks.

The problem is that this fires on **any** change to `settings`, including `availableInMCP` — but that flag doesn't affect trigger behavior at all; it's purely metadata for MCP tooling.

If the reactivation fails for any reason (webhook conflict, an external hook error, etc.), the `_addToActiveWorkflowManager` method rolls the workflow back to `active: false, activeVersionId: null` — meaning the workflow is **silently unpublished**. Since MCP access is only allowed for published workflows, the toggle in the UI then appears off/unavailable on any data refresh (navigating into the workflow, opening settings, F5) — exactly the behavior described in the bug report.

The `availableInMCP` flag itself could physically still be `true` in the database the whole time — what got reset wasn't the setting itself, but the workflow's publish state, which is a prerequisite for MCP access to be visible/available at all.

## Secondary finding

The `PATCH /mcp/workflows/:workflowId/toggle-access` endpoint didn't return a `checksum` in its response (unlike the general `PATCH /workflows/:id`). Because of this, after toggling access from the workflow list (`WorkflowCard.vue`), the workflow's checksum in the editor store (`workflowsStore.workflowChecksum`) stayed stale — this could cause a separate "workflow locked / conflict" error on the next save within the same editor session.

## What was fixed

1. `availableInMCP` is now excluded from the comparison that decides whether the workflow needs to be reactivated. The setting still persists normally to the database — it just can no longer drag the whole workflow offline as a side effect.
2. The `toggle-access` endpoint now returns `checksum`, and the frontend stores it — the checksum no longer goes stale after toggling access from the list.

## Files affected

### Source files (`n8n-fork` repository, `local-2.8.4` branch)

| File | Change |
|---|---|
| `packages/cli/src/workflows/workflow.service.ts` | Added the constant `SETTINGS_KEYS_EXCLUDED_FROM_REACTIVATION = ['availableInMCP']`; `settingsChanged` now compares `settings` with this key omitted (via `lodash/omit`) |
| `packages/cli/src/modules/mcp/mcp.settings.controller.ts` | `toggleWorkflowMCPAccess` now additionally returns `checksum` (via `calculateWorkflowChecksum` from `n8n-workflow`) |
| `packages/frontend/editor-ui/src/features/ai/mcpAccess/mcp.api.ts` | The response type of `toggleWorkflowMcpAccessApi` was extended with a `checksum` field |
| `packages/frontend/editor-ui/src/features/ai/mcpAccess/mcp.store.ts` | `toggleWorkflowMcpAccess` now passes the received `checksum` into `workflowsStore.setWorkflowVersionData(...)` |

### Compiled files (global `n8n` install, `C:\Users\PC\AppData\Roaming\npm\node_modules\n8n`)

Patched by hand for testing without rebuilding the monorepo — they mirror the changes to `workflow.service.ts` and `mcp.settings.controller.ts` above:

| File | Change |
|---|---|
| `dist/workflows/workflow.service.js` | added `require("lodash/omit")` + the same exclusion constant and the `settingsChanged` logic patch |
| `dist/modules/mcp/mcp.settings.controller.js` | added `require("n8n-workflow")` + `checksum` returned in the response |

The frontend part (`mcp.api.ts` / `mcp.store.ts`) was **not** patched in compiled form — it's part of a single minified editor bundle, and hand-patching it isn't practical. This isn't critical: the root cause of the main bug is entirely on the backend.

⚠️ The compiled-file patch will only survive until the next `npm install -g n8n` / update — reinstalling the package will overwrite the changes in `dist/`. For a permanent fix, the changes need to be merged into the source and the project rebuilt the standard way.

## How to verify

1. Restart the `n8n` process (`n8n start`) — no rebuild needed, the changes are already in the compiled files.
2. Enable "Available in MCP" on a published workflow with a supported trigger.
3. Reopen the workflow's settings or refresh the page (F5) — the toggle should stay on.
4. Verify that `search_workflows` via MCP now sees the workflow.
