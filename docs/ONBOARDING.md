# Configure your installation

Shared method: settings.json. Personal configuration: native injected variables on the central cloud owner. Credentials: native secret/vault bindings. Live graph, ledger and sources: private paths outside every Git checkout. No personal values are inferred from examples or previous users.

## Guided onboarding

Use squad-onboard; resolve facts from the user's context before asking. Review investing scope, resources/model, cloud owner/storage, notifications and cadence. Never infer jurisdiction from currency or supported model/runtime from a subscription name. If absent, leave missing choices unset and prepare a draft/proposal; source tests do not require production setup.

| Configuration | Required meaning |
| --- | --- |
| profile_id | Stable unique installation name, not an account credential |
| timezone / jurisdiction | Actual IANA timezone and applicable country/account context |
| base_currency / starting_cash / money_decimals | Allocated cash, denomination, reporting precision; no assumed amount |
| brokerage.name / execution_mode / constraints | Actual investing mechanism, human-executed recommendations, fees/permissions/settlement/account restrictions |
| max_trade_ideas_per_day / max_candidates_per_day | Reviewed ceilings; never promised activity |
| round_trip_cost_bps | Realistic estimated strategy costs, including spreads; not inferred from commission-free marketing |
| worker.model / reasoning_effort | Actual supported preference, or null for host default; does not pin Dot's internal router |
| spending.additional_services_budget | Explicit extra-service allowance, including zero; implementation needs no paid API |
| notification.destination | Exact supported destination/audience with delivery tested |
| instruments[] | Allowed symbol, same-denomination currency, IANA exchange timezone, HH:MM close, weekdays (Monday=0), lot_size, price_tick |
| research_universe[] | Initial immutable specs or empty list for researcher-led prospecting within allowed instruments |
| runtime.kind | Fixed in code: dot_cloud; no runtime-selection variable |
| storage.backend | Fixed ladybug research backend; SQLite is the separate transaction ledger |
| storage.database_path / knowledge_path | Distinct ledger/graph files in the same private data directory, outside every Git checkout/worktree |
| storage.backup_directory | Private staging separate from live data; not itself independent durability |
| storage.runtime_id | Actual central cloud owner identity, verified by saved execution |
| storage.backup_interval_hours / backup_retention_days | Positive interval/retention; changed evidence also triggers backup; operator reviews expired archives before removal |
| storage.cloud_backup.provider / folder_id | google_drive and an authorized private folder; folder ID is not a credential |
| storage.cloud_backup.max_bytes / max_archive_bytes | Explicit project backup budget and per-archive cap; cap fits budget and is at most 1 GiB; actual account free space also checked |
| storage.decision_accepted | false until the concrete graph/ledger/Drive/access/recovery arrangement is accepted |
| schedules.monitor / research / reconcile | Explicit enabled booleans and native RFC 5545 RRULEs in chosen timezone |
| gitops.ref | User's approved ref; update_policy is fixed fast_forward |

Review [cloud access and Google authorization](CLOUD.md), [knowledge representation](KNOWLEDGE.md) and [backup/recovery](STORAGE.md) before initialization.

## Native environment configuration

`python -m squad onboarding` prints the in-code configuration structure and complete variable map without creating state. Bind **every** variable below individually on the owner, including explicit `null` for model/effort when the host chooses them and `[]` for an empty research universe. Arrays use JSON; strings are raw text; booleans/integers/numbers use JSON literals. No profile-file or JSON-blob interface exists. Fixed schema/runtime/backend/execution/update-policy constants have no environment override switches. Do not shell-evaluate configuration content.

Native settings must be injected into the actual owner process. Codex Cloud Personal vault/environment settings apply to selected task environments, not automatically to Dot's own computer. Thin prompt markers do not set variables. [Official environment settings](https://learn.chatgpt.com/docs/environments/cloud-environments).

SQUAD_REPO points to the checkout when needed. SQUAD_PYTHON selects the interpreter for scripts/check.sh. SQUAD_TASK_KEY identifies a native logical task. These are execution bindings, not personal profile fields.

| Variable | Configuration path | Value type |
| --- | --- | --- |
| SQUAD_PROFILE_ID | profile_id | string |
| SQUAD_TIMEZONE | timezone | string |
| SQUAD_JURISDICTION | jurisdiction | string |
| SQUAD_BASE_CURRENCY | base_currency | string |
| SQUAD_STARTING_CASH | starting_cash | string |
| SQUAD_MONEY_DECIMALS | money_decimals | integer |
| SQUAD_MAX_TRADE_IDEAS_PER_DAY | max_trade_ideas_per_day | integer |
| SQUAD_MAX_CANDIDATES_PER_DAY | max_candidates_per_day | integer |
| SQUAD_ROUND_TRIP_COST_BPS | round_trip_cost_bps | number |
| SQUAD_BROKERAGE_NAME | brokerage.name | string |
| SQUAD_BROKERAGE_CONSTRAINTS | brokerage.constraints | string |
| SQUAD_WORKER_MODEL | worker.model | string |
| SQUAD_WORKER_REASONING_EFFORT | worker.reasoning_effort | string |
| SQUAD_SPENDING_ADDITIONAL_SERVICES_BUDGET | spending.additional_services_budget | string |
| SQUAD_NOTIFICATION_DESTINATION | notification.destination | string |
| SQUAD_INSTRUMENTS | instruments | JSON array |
| SQUAD_RESEARCH_UNIVERSE | research_universe | JSON array |
| SQUAD_STORAGE_DATABASE_PATH | storage.database_path | string |
| SQUAD_STORAGE_BACKUP_DIRECTORY | storage.backup_directory | string |
| SQUAD_STORAGE_BACKUP_INTERVAL_HOURS | storage.backup_interval_hours | integer |
| SQUAD_STORAGE_BACKUP_RETENTION_DAYS | storage.backup_retention_days | integer |
| SQUAD_STORAGE_RUNTIME_ID | storage.runtime_id | string |
| SQUAD_STORAGE_DECISION_ACCEPTED | storage.decision_accepted | boolean |
| SQUAD_STORAGE_KNOWLEDGE_PATH | storage.knowledge_path | string |
| SQUAD_STORAGE_CLOUD_BACKUP_FOLDER_ID | storage.cloud_backup.folder_id | string |
| SQUAD_STORAGE_CLOUD_BACKUP_MAX_BYTES | storage.cloud_backup.max_bytes | integer |
| SQUAD_STORAGE_CLOUD_BACKUP_MAX_ARCHIVE_BYTES | storage.cloud_backup.max_archive_bytes | integer |
| SQUAD_SCHEDULES_MONITOR_ENABLED | schedules.monitor.enabled | boolean |
| SQUAD_SCHEDULES_MONITOR_RRULE | schedules.monitor.rrule | string |
| SQUAD_SCHEDULES_RESEARCH_ENABLED | schedules.research.enabled | boolean |
| SQUAD_SCHEDULES_RESEARCH_RRULE | schedules.research.rrule | string |
| SQUAD_SCHEDULES_RECONCILE_ENABLED | schedules.reconcile.enabled | boolean |
| SQUAD_SCHEDULES_RECONCILE_RRULE | schedules.reconcile.rrule | string |
| SQUAD_GITOPS_REF | gitops.ref | string |

Required secret bindings: SQUAD_GOOGLE_REFRESH_TOKEN, SQUAD_GOOGLE_CLIENT_ID and SQUAD_GOOGLE_CLIENT_SECRET. Keep all three in native runtime secrets, never ordinary configuration, source evidence or Git. The client obtains renewable access tokens in memory. The CLI rejects credential-shaped JSON fields and redacts known runtime secret values from errors. Agents must avoid copying secret text into arbitrary prose/source content.

`.env.example` documents names only; it is not automatically loaded and must not be completed in Git. Use actual native runtime settings. The obsolete SQUAD_PROFILE/SQUAD_PROFILE_JSON variables and --profile/configure CLI routes are rejected. No profile JSON template remains in the repository; field definitions live in squad/configuration.py.

## Initialize and activate

1. Install the pinned Python dependency and run setup-runtime; it installs the matching FTS extension using a temporary probe only.
2. Prepare complete configuration with storage acceptance false. Run storage-plan; it creates nothing. Review ownership, privacy, cloud quota, loss window and recovery; then set acceptance true.
3. Explicit init provisions/binds the graph and ledger. Ordinary reads/runs never create missing state. Doctor reports identities and backup readiness without asserting native activation.
4. Make the initial backup cloud; it must upload, download and fully restore in staging. Production activation requires its actual verified event. Initial research --preflight is limited to an empty forecast ledger; back up again after collecting evidence.
5. Use squad-reconcile to apply actual native tasks and inspect actual loaded skills. Independently reopen both database paths on the configured owner and test a labelled setup notification. Record only actual fresh platform receipts.

Cash, currency, cost assumptions and statistical gate settings freeze on initialization. Schedule/model/destination changes retain non-secret revisions and require deployment reconciliation. A path change requires restoring/adopting the original identity or deliberately starting a separate experiment. Never silently reset evidence or reinterpret cash. User-reported fills remain the sole fill authority; a pasted portfolio is read-only context until discrepancies are reconciled.
