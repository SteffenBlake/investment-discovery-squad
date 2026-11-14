# Shared commands

Python 3.11+; install `scripts/requirements.txt`, then `setup-runtime`. Checkout entry: `python .agents/skills/squad-onboard/scripts/main.py COMMAND`. Installed plugin resolves sibling squad-onboard entry. Run commands through [Dot computer](cloud.md#computer-and-command-access) in Dot’s cloud computer.

## Setup

| Command | Effect |
| --- | --- |
| onboarding | Generated environment variable names/types and guides |
| setup-runtime | Prepare Ladybug full-text search extension |
| storage-plan | Concrete storage proposal |
| init --inventory FILE | Check connected Drive inventory before empty setup; existing matching stores retain identity |
| adopt --confirm-currency CODE | Verify/snapshot/bind compatible legacy ledger |
| doctor | Inspect settings, database integrity, research and backup status |
| status / alerts | Saved research state and alert receipts |

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
| knowledge context [--portfolio FILE] [--symbols A,B] [--query TEXT] [--limit N] [--hops N] | Read supplied current portfolio and return related research |

[Historical method](../../squad-research/references/methodology.md) owns one-shot rules and related-premise hatch.

Spec: nonempty `id`, `name`, `phenomenon`, `mechanism`, configured `symbol`, stable `family_id`, canonical measurement `input_id`, `feature_formula` object with canonical `operation` and parameters, `horizon_days` integer 1–90, numeric `target_return` fraction (0,1), nonempty `limitations` list. Optional `article` selects built-in Wikipedia adapter for `wikimedia:pageviews`, operation `ratio_to_mean`, `lookback_days:28`. Other formulas require reviewed custom adapter/manual future measurements.

Development/holdout dataset: `synthetic:false`, `source`, `availability_verified:true`, `availability_evidence`, `limitations`, `rows`. Row: `event_id`, `available_at`, `entry_at`, `exit_at`, `feature`, `entry_price`, `exit_price`. Original availability must precede simulated entry.

Plan file: `signal_id`, `development` dataset, `holdout_unseen:true`, `test_windows` list. Each window contains exactly `event_id`, `entry_at`, `exit_at`. Freeze dates/identities before accessing test outcomes. Submit later holdout dataset containing every frozen window in order. Plan fixes threshold/direction from development, costs, sample count and statistical check. Input errors return `tested=false` and recorded error; repair source data against same frozen plan. Completed valid test returns `passed`; failed result permanently rejects hypothesis.

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

## Trades

`idea --prediction ID --portfolio FILE`: calculate eligible bullish purchase from current supplied cash and entry fees. [Portfolio](../../squad-trades/references/portfolio.md) owns next-action advice and temporary input.

## Backup

| Command | Effect |
| --- | --- |
| backup cloud [--inventory FILE] [--force] / backup-due [--inventory FILE] | Prepare/recover connector handoff for same Drive backup file |
| backup started | Persist upload attempt before connector call |
| backup accept --file RECEIPT_JSON | Record actual connected upload acceptance |
| backup retry --file EVIDENCE_JSON | Retry confirmed failure before remote write |
| backup snapshot --output NEW_ABSOLUTE_PATH | Local complete archive |
| backup list --inventory FILE | Archives from connected folder inventory |
| backup verify --file DOWNLOADED_ZIP --expected-identity IDENTITY | Deliberate staged restore test |
| backup restore --file DOWNLOADED_ZIP --file-id ID --expected-identity IDENTITY | Recover original stores into empty target |
| export [--output ABSOLUTE_PATH] | Numerical inspection; defaults beside ledger |

[Storage](storage.md) owns procedures. `deployment sync` updates approved clean checkout; [deployment](../../squad-reconcile/references/deployment.md) owns plugin and automations.

Output JSON. Exit 0 command completed, including failed investment test. Read `passed` for test result. Exit 1 invalid input/failed operation; 2 run errors. Inspect JSON/stderr and saved state before retry because earlier writes may have committed. [Operations](../../squad-monitor/references/operations.md) owns delivery and `remaining_work`. Timestamps require offsets and store UTC; messages use configured timezone. Imports reject credential-shaped fields and bound secret values before writes.
