# Forecast results and live trial

[Historical method](../../squad-research/references/methodology.md) owns qualification. Passed untouched-history test qualifies idea for further investigation. Forward results preserve all wins, losses, pending attempts and corrections.

## Forecast endpoints

Registration assigns current timestamp; due time equals registration plus saved duration. Measured feature exceeds frozen threshold. Fresh reference quote follows event availability; direction, target and costs match saved test plan.

Resolve preceding same-signal endpoint before another forecast. New reference quote strictly follows previous realized endpoint. Event IDs unique; consecutive attention spikes form one episode. Report residual dependence between events.

Price adapter uses configured exchange calendar for actual session closing times, including early closes and holidays. Accept closing price only from response captured at least 30 minutes after actual close. Missing session time leaves affected prediction pending with reported blocker. Manual observations retain supplied actual timestamps.

Evaluate first actual close at/after due, within seven calendar days. Missing/late prices remain pending. Ingest corporate actions before evaluation. Split crossing forecast window invalidates signal. Late split or legacy overlapping/shared endpoint appends correction and retains original result. [Delivery](operations.md#claim-deliver-acknowledge) handles affected alerts.

## Live trial

First genuine future prediction starts installation's initial 30-day trial. `trial status` returns every prediction, completed/pending/invalidated counts, forecast returns after costs, ordinary buy-and-hold comparison and reported fills. Forecast returns describe research observations; fills preserve actual user executions.

At deadline, scheduled research/monitor collection and direct forecast registration stop for review. Report results and uncertainty, including unresolved predictions. User decides continuation based on performance. `trial review --file PRIVATE_FILE` records continue/stop, reason and actual user approval evidence. Continuation lasts explicitly selected 1–30 days. Retain every earlier period and result.

When review required or stopped, disable this installation's research/monitor jobs through [task procedure](../../squad-reconcile/references/deployment.md#native-tasks). Reconciliation and backup remain available. User-approved continuation reuses same jobs.

## Tests

Root Python tests cover untouched-history qualification, one-shot failures/retry rules, actual-close timing, complete future outcomes, claims/receipts, restart, trial deadline and reviewed continuation. Fixtures use temporary storage.
