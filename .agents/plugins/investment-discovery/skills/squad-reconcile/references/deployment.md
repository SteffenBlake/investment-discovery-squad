# Source updates and scheduled jobs

## Source and plugin

Skills live in `.agents/plugins/investment-discovery/skills/squad-*`. Repository discovery paths under `.agents/skills/` symlink to those folders. Edit either path. `SQUAD_REPO` binds approved Git checkout; runtime resources resolve from owning skill.

`main.py deployment sync` requires clean tree, fetches approved origin ref and merges `--ff-only`. Preserve local edits and divergent history. Start fresh process after update; install changed requirements, prepare FTS and run relevant Python tests.

Workspace installation: refresh registered repository/ref through **Admin → Plugins → Marketplaces → selected marketplace → Sync now**, or exposed workspace sync tool. Read sync report and individual plugin failures. [Workspace sync](https://learn.chatgpt.com/docs/enterprise/plugin-management#keep-plugins-up-to-date).

For release, run `python .agents/skills/squad-reconcile/scripts/bundle.py`; archive includes plugin resources and license.

## Native tasks

This procedure owns scheduled-job creation and later changes. [Cloud setup](../../squad-onboard/references/cloud.md#bind-and-verify-owner) owns durable child task (cloud thread), title and reuse. Discover host's tools to list, create, update and read saved jobs. Identify installation by owner, `profile_id`, skill invocation and existing `squad/PROFILE_ID/WORKFLOW` task key. Ask when ownership ambiguous.

| Workflow | Invocation |
| --- | --- |
| monitor | Use $squad-monitor |
| research | Use $squad-research |
| reconcile | Use $squad-reconcile |

1. List jobs; update matching returned IDs or create missing jobs. Preserve unrelated jobs and explicit user pauses. Resolve project-owned duplicates.
2. Set reviewed schedule/timezone, enabled state and destination through supported host controls. Schedule wakes coordinating Dot to follow relevant skill and send container-dependent work to saved cloud thread; save task/thread reference in job instructions. Set model/effort where supported; null restores host preference. Cloud thread runs work in owner cloud container using approved checkout and interpreter.
3. After uncertain mutation, inspect saved state before retry. Read each job back; retain IDs and settings privately.
4. Execute saved schedule. Verify coordinating Dot follows relevant skill, continues saved cloud thread and receives result confirming original research/prediction stores reopened with matching installation identities. Retain observed result in host history. Failed route leaves affected scheduled workflow inactive; report specific failure.
5. Apply [trial](../../squad-monitor/references/validation.md#live-trial) status: expired/stopped trial disables research/monitor jobs; approved continuation restores reviewed enabled choices. Preserve user pauses. Reconcile job remains available.

[Delivery](../../squad-monitor/references/operations.md#claim-deliver-acknowledge) owns message checks. [Native controls](https://learn.chatgpt.com/docs/dots/controls).

## Recovery and rollback

Follow [storage recovery](../../squad-onboard/references/storage.md#recovery) before reactivating jobs. Roll back to reviewed schema-compatible code. Preserve research, prediction results, test plans, statistical attempt counts and uncertain deliveries.
