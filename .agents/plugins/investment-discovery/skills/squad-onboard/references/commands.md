# Shared commands

Python 3.11+; install `scripts/requirements.txt`, then `setup-runtime`. Checkout entry: `python .agents/skills/squad-onboard/scripts/main.py COMMAND`. Installed plugin resolves sibling squad-onboard entry. Run commands through [saved cloud thread](cloud.md#bind-and-verify-owner) in owner cloud container.

## Setup

| Command | Effect |
| --- | --- |
| onboarding | Generated native settings names/types and guides |
| setup-runtime | Prepare Ladybug full-text search extension |
| storage-plan | Concrete storage proposal |
| init | Check remote backups before empty setup; existing matching stores retain identity |
| adopt --confirm-currency CODE --confirm-starting-cash VALUE | Verify/snapshot/bind compatible legacy ledger |
| doctor | Inspect settings, database integrity, research and backup status |
| status / portfolio / alerts | Saved state, latest supplied portfolio, alert receipts |

## Research

| Command | Effect |
| --- | --- |
| research [--offline] [--preflight] [--continue-work] | Due results/delivery, historical research work and eligible future events |
| discover --file SPEC | Register immutable hypothesis within daily ceiling |
| prepare-test --file PLAN | Freeze development rule, exact untouched test windows and lifetime attempt number |
| backtest --signal ID --dataset HOLDOUT | Consume single test; pass qualifies for further investigation; failure rejects permanently |
| forecast --file FORECAST / prices --file PRICES | Register future prediction / import observations |
| knowledge status / ingest --file BATCH | Inspect/ingest research graph |
| knowledge search --query TEXT [--limit N] | Search claims with sources and contradictions |
| knowledge show --type Claim\|Entity\|Source\|Batch --id ID | Exact record |
| knowledge context [--portfolio FILE] [--symbols A,B] [--query TEXT] [--limit N] [--hops N] | Save supplied portfolio and return related research |

[Historical method](../../squad-research/references/methodology.md) owns one-shot rules and related-premise hatch.

Spec: nonempty `id`, `name`, `phenomenon`, `mechanism`, configured `symbol`, stable `family_id`, canonical measurement `input_id`, `feature_formula` object with canonical `operation` and parameters, `horizon_days` integer 1–90, numeric `target_return` fraction (0,1), nonempty `limitations` list. Optional `article` selects built-in Wikipedia adapter for `wikimedia:pageviews`, operation `ratio_to_mean`, `lookback_days:28`. Other formulas require reviewed custom adapter/manual future measurements.

Development/holdout dataset: `synthetic:false`, `source`, `availability_verified:true`, `availability_evidence`, `limitations`, `rows`. Row: `event_id`, `available_at`, `entry_at`, `exit_at`, `feature`, `entry_price`, `exit_price`. Original availability must precede simulated entry.

Plan file: `signal_id`, `development` dataset, `holdout_unseen:true`, `test_windows` list. Each window contains exactly `event_id`, `entry_at`, `exit_at`. Freeze dates/identities before accessing test outcomes. Submit later holdout dataset containing every frozen window in order. Plan fixes threshold/direction from development, costs, sample count and statistical check. Changed plans fail; malformed submitted test consumes attempt and rejects hypothesis.

Forecast: `signal_id`, `event_id`, `event_available_at`, `quote_at`, `reference_price`, `feature_value`, `source`. [Live validation](../../squad-monitor/references/validation.md) owns endpoints. Price import: array of `symbol`, `market_at`, `price`, `kind` (quote/close), `currency`, `source`. Use actual observation times.

## Monitor

| Command | Effect |
| --- | --- |
| run [--offline] [--continue-work] | Evaluate/deliver, then eligible collection |
| report --signal ID | Complete historical/future evidence and corrections |
| state --signal ID --to REJECTED\|DEGRADED\|INVALIDATED --reason TEXT | Record supported change |
| claim --alert ID | Claim complete message/token |
| ack --alert ID --token TOKEN --receipt RECEIPT | Save delivered message ID/link |
| release --alert ID --token TOKEN --confirmed-not-sent EVIDENCE | Release confirmed unsent message |
| trial status | Current observation period and full performance |
| trial review --file REVIEW | Record user decision following performance review |

Review JSON: `decision` continue/stop, nonempty `reason`, `user_approval` containing actual user decision evidence, `days` integer 1–30 (default 30). [Trial procedure](../../squad-monitor/references/validation.md#live-trial) owns continuation.

## Trades

`idea --prediction ID --portfolio FILE`: eligible bullish purchase sized from supplied available cash and entry fees. `fill --file FILL`: save reported execution. Fill fields: `fill_id`, `symbol`, buy/sell `side`, `quantity`, `price`, `fee`, `filled_at`. Decimal strings supported; lot size applies. [Portfolio](../../squad-trades/references/portfolio.md) owns assessment and follow-up.

## Backup

| Command | Effect |
| --- | --- |
| backup cloud [--force] / backup-due | Full upload, server-checksum verification, latest-three retention |
| backup snapshot --output NEW_ABSOLUTE_PATH | Local complete archive |
| backup list | Remote installation versions |
| backup verify --file-id ID --expected-identity IDENTITY | Explicit download and staged restore test |
| backup restore --file-id ID --expected-identity IDENTITY | Recover into empty target |
| export [--output ABSOLUTE_PATH] | Numerical inspection; defaults beside ledger |

[Storage](storage.md) owns procedures. `deployment sync` updates approved clean checkout; [deployment](../../squad-reconcile/references/deployment.md) owns plugin and jobs.

Output JSON. Exit 0 completed; 1 failed/rejected operation; 2 run errors. Inspect JSON/stderr and saved state before retry because earlier writes may have committed. [Operations](../../squad-monitor/references/operations.md) owns delivery and `remaining_work`. Timestamps require offsets and store UTC; messages use configured timezone. Imports reject credential-shaped fields and bound secret values before writes.
