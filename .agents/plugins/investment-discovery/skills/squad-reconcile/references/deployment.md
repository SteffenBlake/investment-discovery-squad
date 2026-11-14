# Source updates and scheduled automations

## Source and plugin

Skills live in `.agents/plugins/investment-discovery/skills/squad-*`. Repository discovery paths under `.agents/skills/` symlink to those folders. Edit either path. `SQUAD_REPO` binds approved Git checkout; runtime resources resolve from owning skill.

`main.py deployment sync` requires clean tree, fetches approved origin ref and merges `--ff-only`. Preserve local edits and divergent history. Start fresh process after update; install changed requirements, prepare FTS and run relevant Python tests.

Update plugin through original installation route. Exposed marketplace registration: refresh its reviewed repository/ref through available sync control; read sync report and plugin failures. ZIP installation: obtain reviewed release ZIP from [user-supplied repository](../../squad-onboard/references/setup.md#source-and-runtime), then use exposed plugin-update control or identify required user/admin action. Verify returned installation result. [Workspace sync](https://learn.chatgpt.com/docs/enterprise/plugin-management#keep-plugins-up-to-date).

For release, run `python .agents/skills/squad-reconcile/scripts/bundle.py --version ACTUAL_RELEASE_TAG`; archive includes plugin resources and license.

## Scheduled automations

Scheduled automation wakes coordinating Dot, which follows skill and continues saved durable child task. Child task's cloud container runs code and holds stores. [Child-task setup](../../squad-onboard/references/cloud.md#durable-child-task) owns that separate task's title/reference and reuse.

Inspect currently exposed automation tools for list/create/update/read, pause/cancel, supported timing and immediate-run capability. Use actual tool names/arguments; if unavailable, report specific gap and direct user to **Scheduled** for review. Identify installation by database-owning runtime, `profile_id`, skill invocation and existing `squad/PROFILE_ID/WORKFLOW` automation key. Ask when installation unclear.

| Workflow | Invocation |
| --- | --- |
| monitor | Use $squad-monitor |
| research | Use $squad-research |
| reconcile | Use $squad-reconcile |

1. List scheduled automations; update matching returned IDs or create missing automations. Preserve unrelated automations and explicit user pauses. Resolve installation's duplicates. Store automation IDs separately from durable child task ID.
2. Set reviewed timing/timezone, enabled state and destination through exposed controls. Save relevant skill invocation and child task reference in automation instructions. Child task uses approved checkout/interpreter and verified runtime settings. Set model/effort where supported; null restores host preference.
3. After uncertain mutation, inspect saved state before retry. Read each automation back; retain returned IDs and settings privately.
4. Test saved automation using immediate-run control if exposed. Otherwise manually send same instructions through Dot → saved child task, verify original research/prediction stores and installation identities, then use next reviewed scheduled wake to verify full route. Saved instructions require those checks before investment work. Mark automation pending verification until observed wake/result; retain evidence in host history. Failed route leaves affected automation inactive; report specific failure.
5. Apply [trial](../../squad-monitor/references/validation.md#live-trial) status: expired/stopped trial disables research/monitor automations; approved continuation restores reviewed enabled choices. Preserve user pauses. Reconcile automation remains available.

[Alert delivery](../../squad-monitor/references/operations.md#claim-deliver-acknowledge) owns investment-alert receipts and uncertain sends. [Setup](../../squad-onboard/references/setup.md#initial-scheduled-automations) owns setup confirmation message. [Official scheduling guidance](https://learn.chatgpt.com/docs/dots/tasks-and-memory#recurring-tasks) covers **Scheduled** review; exposed tools determine available automation controls.

## Recovery and rollback

Follow [storage recovery](../../squad-onboard/references/storage.md#recovery) before reactivating automations. Roll back to reviewed schema-compatible code. Preserve research, prediction results, test plans, statistical attempt counts and uncertain deliveries.
