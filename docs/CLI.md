# CLI

Python 3.11+, pinned ladybug==0.22.3 plus stdlib. Install dependencies and run setup-runtime first. From the checkout: `python3 -m squad COMMAND`. Production requires every documented individual native SQUAD_* value on Dot's cloud owner. No profile-file, JSON-blob, --profile, configure or --db route exists. User data stay outside Git. `.env` files are not auto-loaded.

| Command | Effect |
| --- | --- |
| onboarding | Print unset profile template/guide; no production writes |
| storage-plan | Show selected storage/data/limitations even before acceptance; no database |
| setup-runtime | Install/load matching Ladybug FTS extension using a temporary probe; no production DB |
| init | Explicit accepted graph + ledger provisioning; idempotent same-profile identity |
| adopt --confirm-currency CODE --confirm-starting-cash VALUE | Back up and explicitly adopt a compatible unowned legacy ledger |
| doctor | Source/config/database readiness; never creates a missing DB or asserts account activation |
| status / portfolio / alerts | Inspect owned ledger; missing DB is an error |
| demo [--output-dir NEW_DIR] | Isolated synthetic acceptance; no user profile required |
| research / run [--offline] [--preflight] | Research or monitor; production requires current deployment, preflight only for empty forecast ledgers |
| discover --file SPEC / backtest --signal ID --dataset DATA | Register immutable hypothesis and compute its one formal holdout |
| forecast --file FORECAST / prices --file PRICES | Register actual new event/import real market observations |
| report --signal ID | Complete evidence, all live outcomes and uncertainty |
| state --signal ID --to DEGRADED --reason TEXT | Reject/degrade/invalidate, never manually qualify |
| claim --alert ID | Atomic claim/full notification, null if already owned/delivered |
| ack --alert ID --token TOKEN --receipt RECEIPT | Confirm actual delivery; identical repeat is idempotent |
| release --alert ID --token TOKEN --confirmed-not-sent EVIDENCE | Retry only after confirmed non-delivery |
| idea --prediction ID | Fresh qualified entry under profile cash/lot/tick/cap constraints |
| fill --file FILL | Append actual user-reported fill; duplicate same ID is idempotent |
| export [--output PATH] | Readable private numerical ledger export, not graph/recovery authority |
| backup snapshot --output NEW_PATH | Complete offline graph + ledger + sources archive; not cloud durability |
| backup cloud [--force] | New complete archive, Drive upload/download, checksum and full staging restore; actual success event |
| backup list | Inspect this profile's actual remote Drive versions |
| backup verify --file-id ID --expected-identity IDENTITY | Download and fully restore-check a selected remote version in staging |
| backup restore --file-id ID --expected-identity IDENTITY | Recover into a new empty data directory; preserve identity, require reconciliation |
| backup-due | Complete verified cloud backup when evidence/destination changed or interval elapsed |
| knowledge status | Graph identity/schema and record counts |
| knowledge ingest --file BATCH | Validate/atomically ingest immutable entities/sources/claims/relations; idempotent retry |
| knowledge search --query TEXT [--limit N] | Indexed BM25 claim search with provenance/contradictions |
| knowledge show --type Claim\|Entity\|Source\|Batch --id ID | Exact original immutable record |
| knowledge context [--portfolio FILE] [--symbols A,B] [--query TEXT] [--limit N] [--hops N] | Bounded portfolio graph/text/numerical evidence packet; no fills/balance changes |
| deployment plan [--observed FILE] | Native desired state; --observed adds actual-state diff |
| deployment record --file RECEIPT | Validate/store actual readback/runtime/delivery evidence |
| deployment check [--observed FILE] | Source/configuration/application drift; --observed checks actual native task state |
| deployment sync | Approved clean fast-forward only, or no-op under manual policy |

Output JSON. Exit 0 completed; 1 invalid input/operation; 2 completed run with errors requiring inspection. A later error may follow committed writes; inspect ledger before retry. Timestamps require explicit offsets; stored evidence normalizes to UTC, messages render in profile timezone.

## Data formats

Signal spec fields: id, name, phenomenon, mechanism, symbol (allowed by profile), horizon_days (1–90), target_return (fraction), limitations (list). Optional article enables the Wikipedia attention adapter. Changed rules require new immutable IDs. No geography/asset seeds are installed by default.

Historical dataset fields: synthetic=false for real evidence, source, availability_verified, availability_evidence, limitations, rows. Each chronological disjoint row: event_id, available_at, entry_at, exit_at, feature, entry_price, exit_price. Require available_at < entry_at < exit_at <= now and matching horizon. Defaults require at least 100 training/100 holdout windows and 20 triggered holdout events; the 60/40 split needs at least 250 total windows. Availability is a provenance assertion requiring actual archive evidence, never a way to override computed statistics. Preserve originals; assumed retrospective lags cannot pass.

Live forecast fields: signal_id, event_id, event_available_at, due_at, quote_at, reference_price, source. Registration timestamp is assigned now; caller cannot backdate it. Direction, target and costs freeze from the test. Quote must be current. Windows/underlying episodes cannot be double-counted. Success uses the first eligible actual close at/after due (within seven days), not the best intraperiod price. Missing/too-late endpoints remain pending.

Market import is an array of symbol, market_at, price, kind (quote or close), currency, source objects. Currency must match configured denomination; actual source timestamps only. Never replace an endpoint with a recent/favorable quote. Later revisions cannot rewrite first observations/outcomes. Built-in split detection blocks known price-return artifacts; custom adapters need equivalent review.

Human fill fields: fill_id, symbol, side (buy/sell), quantity (decimal string permitted within lot_size), price, fee, filled_at. Values are in the configured currency. Example data in tests are fictional. No approval/unfilled order is a fill. Use distinct IDs for partial fills. Cash overspending and sales beyond reported holdings are rejected. Taxes, settlement, transfers, dividends and FX accounting are outside this initial cash ledger.

Research batch and actual-portfolio input formats: [KNOWLEDGE.md](KNOWLEDGE.md). Native environment variable names/types: [ONBOARDING.md](ONBOARDING.md). Full cloud recovery/access limits: [STORAGE.md](STORAGE.md), [CLOUD.md](CLOUD.md).
