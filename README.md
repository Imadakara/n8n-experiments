# n8n "Available in MCP" Toggle Persistence Fix

## Tested

- Windows 11
- Node.js v20.20.2 / v22.22.3
- n8n 2.8.4

This repository contains a fix for the **"Available in MCP" workflow toggle not persisting** in n8n.
Corresponds to open issue [n8n-io/n8n#25987](https://github.com/n8n-io/n8n/issues/25987) — "Available in MCP toggle not persisting".

## Problem

The "Available in MCP" toggle (Workflow → Settings, workflow list card menu, and the MCP settings page) can be turned on with no error, but the state silently reverts to off whenever the workflow data gets re-fetched — e.g.:

- navigating into the workflow from the list;
- reopening the workflow's settings;
- refreshing the page (F5).

As a result, `search_workflows` (and the rest of n8n's MCP tools) never sees the workflow, even though it's published and visible in the UI.

`WorkflowService.update()` reactivates any **active (published)** workflow whenever its `settings` object changes, so its running triggers/webhooks pick up the new values:

```
Merge settings → removeDefaultValues → settingsChanged?
  → activateWorkflow() → deactivate + re-add to ActiveWorkflowManager
```

This reactivation is triggered by **any** settings change — including `availableInMCP`, a pure metadata flag that has no effect on trigger/webhook behavior at all. If the reactivation fails for any reason (webhook conflict, external hook error, etc.), `_addToActiveWorkflowManager` rolls the workflow back to `active: false, activeVersionId: null`, silently **unpublishing** it. Since MCP access requires an active workflow, the toggle then reads as off/unavailable on the next data refresh — even though `settings.availableInMCP` may still be `true` in the database the whole time.

## Solution

- `availableInMCP` is excluded from the comparison `WorkflowService.update()` uses to decide whether a reactivation cycle is needed. The setting still persists to the database exactly as before — it just can no longer drag an otherwise-healthy workflow offline as a side effect.
- The `PATCH /mcp/workflows/:workflowId/toggle-access` endpoint now also returns `checksum` (previously omitted, unlike the general `PATCH /workflows/:id`), so the editor's in-memory workflow checksum no longer goes stale after toggling MCP access from the workflow list — preventing a follow-up spurious "workflow locked / conflict" error on the next save in the same session.

The external API contract (request/response shapes, endpoint URLs) is unchanged — this is a behavioral fix only.

### Files changed

| File | Change |
|---|---|
| `packages/cli/src/workflows/workflow.service.ts` | `settingsChanged` now ignores `availableInMCP` (via `lodash/omit`) when deciding whether to reactivate the workflow |
| `packages/cli/src/modules/mcp/mcp.settings.controller.ts` | `toggleWorkflowMCPAccess` now returns `checksum` alongside `id`/`settings`/`versionId` |
| `packages/frontend/editor-ui/src/features/ai/mcpAccess/mcp.api.ts` | Response type of `toggleWorkflowMcpAccessApi` extended with `checksum` |
| `packages/frontend/editor-ui/src/features/ai/mcpAccess/mcp.store.ts` | `toggleWorkflowMcpAccess` forwards `checksum` into `workflowsStore.setWorkflowVersionData(...)` |

**NO REBUILD NEEDED to test** — the same logic patched here has been mirror-applied by hand to the compiled `dist/` output of a global `npm install -g n8n` install and confirmed working; a full `pnpm build` is only required to ship these source changes for real. See the repo's `n8n-mcp-toggle-fix.md` for the manual compiled-file patch, if you want to verify before rebuilding.

## How to verify

1. Build (or, for a quick check, apply the equivalent patch to your compiled `dist/` output) and restart n8n.
2. Enable "Available in MCP" on a published workflow that has a supported trigger node.
3. Reopen the workflow's settings, or refresh the page (F5) — the toggle should stay on.
4. Confirm `search_workflows` over MCP now returns the workflow.
