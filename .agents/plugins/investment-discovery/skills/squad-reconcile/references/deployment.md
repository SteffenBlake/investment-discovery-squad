# Source updates and scheduled automations

## Source and plugin

Source: user's download repository/release from [onboarding checklist](../../squad-onboard/SKILL.md). Skills live under `.agents/plugins/investment-discovery/skills/`; `.agents/skills/` paths symlink there. `SQUAD_REPO` selects approved checkout on **This Dot’s cloud computer**.

`main.py deployment sync` requires clean tree, fetches approved origin ref and merges `--ff-only`. Preserve local edits/divergence. Start fresh process after update; remove retired `SQUAD_STARTING_CASH`, `SQUAD_MAX_TRADE_IDEAS_PER_DAY` and `SQUAD_TASK_KEY` assignments from project `.env`. Install changed dependencies, prepare FTS and run relevant Python tests. Refresh installed plugin through original exposed installation route; verify actual sync/install result. Missing controls require specific user/admin action.

Release packaging: `python .agents/skills/squad-reconcile/scripts/bundle.py --version ACTUAL_RELEASE_TAG` includes runtime, skills and license.

## Scheduled automations

[Onboarding checklist](../../squad-onboard/SKILL.md) gathers all three cadences together. `schedules.monitor/research/reconcile` in installation configuration owns reviewed timing/enabled choices; user pauses remain authoritative. Main Dot performs scheduled work on same computer/original stores.

| Automation | Saved invocation/work |
| --- | --- |
| research | Use $squad-research: explore historical sources, develop/register hypotheses, freeze plans and test untouched later history; track genuine future predictions |
| monitor | Use $squad-monitor: evaluate due predictions, report qualified alerts/corrections and review prediction outcomes |
| reconcile | Use $squad-reconcile: reconcile source/runtime, automations and recovery state |

1. Rediscover exposed automation tools. User-observed names: `automations_peek`, `automations_create_for_aeon`, `automations_update`, `automations_run_now`. Inspect actual schemas; prefix/control availability can change. Privately read existing automations; match `profile_id`, skill and `squad/PROFILE_ID/WORKFLOW` key. Reuse returned IDs; resolve installation's duplicates and preserve unrelated automations.
2. Save title, relevant skill prompt, reviewed iCal VEVENT/recurrence, `timing_mode` and timezone through supported fields (`default_timezone` when exposed). Prompt identifies returned Dot-computer environment ID, approved checkout/interpreter and original store identities; it directs Dot to attach that computer, explicitly load checkout’s `.env` before runtime commands and follow complete skill including connected backups. Environment comes from [project `.env`](../../squad-onboard/references/cloud.md#project-environment).
3. Update/pause by actual returned `jawbone_id`. Preserve explicit pauses, reviewed model/effort where supported, and null host defaults. Inspect saved state after uncertain mutation before retry; read back timing, destination, prompt and enabled state. Retain IDs/settings privately.
4. Invoke immediate-run tool when user requests immediate run. Otherwise observe next reviewed scheduled wake. Before investment work, wake must attach same computer and verify login environment/original stores; retain returned run/result in host history. Report creation separately from successful observed execution. Until observed, route remains pending verification. Failed route pauses affected automation and reports concrete error. Missing creation/read controls leave affected automation inactive and reported; user can inspect **Scheduled**.
5. Preserve reviewed enabled choices and user pauses. Research cadence repeats actual research/testing within configured resources.

[Alert delivery](../../squad-monitor/references/operations.md#claim-deliver-acknowledge) owns investment-alert receipts. [Onboarding checklist](../../squad-onboard/SKILL.md) owns setup message. [Scheduled review](https://learn.chatgpt.com/docs/dots/tasks-and-memory#recurring-tasks) documents host review; use exposed controls for actual mutations.

## Recovery and rollback

Follow [recovery](../../squad-onboard/references/storage.md#recovery) before reactivating automations. Verify same computer and original store identity, or recovered original identity on replacement runtime. Roll back to reviewed schema-compatible code. Preserve test plans/results, statistical attempt counts and uncertain deliveries.
