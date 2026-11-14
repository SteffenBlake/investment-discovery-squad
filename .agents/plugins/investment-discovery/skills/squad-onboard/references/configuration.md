# Installation settings

Shared research rules: [settings.json](settings.json). Personal settings: environment variables received by child task's cloud container. [Cloud controls](cloud.md#runtime-settings-and-credentials) define persistence, credential entry and later-run checks. Live files: private paths outside Git checkouts.

Use user context before asking personal choices. Review investment scope, resources, storage, delivery and schedule. Leave missing choices unset while preparing proposal.

| Settings | Meaning / consumer |
| --- | --- |
| profile_id | Stable installation identity; saved records retain this field name |
| timezone / jurisdiction | IANA timezone for code/messages; applicable country/account context for agent |
| base_currency / starting_cash | Currency and original allocated amount; frozen ownership/recovery history |
| brokerage.name / constraints | Agent's broker/account context |
| brokerage.entry_fee_fixed / entry_fee_per_unit | Purchase sizing fees; decimal strings; explicit zero permitted |
| max_trade_ideas_per_day / max_candidates_per_day | Code-enforced daily ceilings |
| round_trip_cost_bps | Estimated spreads/fees for research returns; frozen |
| worker.model / reasoning_effort | Supported automation preference or null for host default |
| spending.additional_services_budget | Agent's reviewed extra-service allowance, including zero |
| notification.destination | Host delivery destination/audience |
| instruments[] | Allowed symbol, same-denomination currency, IANA exchange_timezone, exchange_calendar, lot_size, price_tick |
| research_universe[] | Initial immutable hypotheses or empty list for historical prospecting |
| storage.database_path / knowledge_path | Distinct prediction/research files in same private directory |
| storage.backup_directory | Private staging separate from live files |
| storage.runtime_id | Database-owning runtime identity verified through scheduled Dot → saved cloud thread |
| storage.backup_interval_hours | Positive backup interval; changed evidence also triggers backup |
| storage.cloud_backup.folder_id | Authorized private Google Drive folder |
| storage.cloud_backup.max_bytes / max_archive_bytes | Project/archive budgets; allow temporary fourth copy during upload; archive at most 1 GiB |
| storage.decision_accepted | True after user's concrete storage arrangement accepted |
| schedules.monitor / research / reconcile | Enabled flags and RFC 5545 recurrence rules in selected timezone |
| gitops.ref | Approved Git ref; fast-forward update policy fixed |

Runtime `dot_cloud`, research backend `ladybug`, separate SQLite prediction ledger, Google Drive backups and human execution fixed in code. Three successful backups retained. [Storage](storage.md) owns backup behavior.

`exchange_calendar` uses exchange_calendars names, e.g. XNYS for New York equities, XLON for London, XTSE for Toronto. Select actual market. Calendar supplies historical/early closing times and holidays. `exchange_timezone` maps provider's session date.

## Environment variables

Run `python .agents/skills/squad-onboard/scripts/main.py onboarding` for generated names/types. Set listed variables individually through [verified runtime controls](cloud.md#runtime-settings-and-credentials). Strings raw text; arrays JSON; numbers/booleans JSON literals. Set null for host model/effort, [] for empty research universe. Fixed architecture fields come from code.

`SQUAD_REPO` selects approved checkout; `SQUAD_PYTHON` selects test interpreter; `SQUAD_TASK_KEY` identifies scheduled automation, distinct from durable child task ID. During update, remove retired `SQUAD_MONEY_DECIMALS` and `SQUAD_STORAGE_BACKUP_RETENTION_DAYS`; instrument calendar replaces fixed close time and weekday list.

Original cash/currency, costs and statistical rules stay frozen for history. Current user-pasted portfolio supplies holdings and available uninvested cash. Agent may recommend holding cash when evidence supports it. Saved configuration revisions retain earlier values; [automation procedure](../../squad-reconcile/references/deployment.md#scheduled-automations) owns changed scheduled settings.
