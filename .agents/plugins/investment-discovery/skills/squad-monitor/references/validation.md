# Forecast results

[Historical method](../../squad-research/references/methodology.md) owns qualification. Passed untouched-history test qualifies idea for further investigation. Forward results preserve all wins, losses, pending attempts and corrections.

## Forecast endpoints

Registration assigns current timestamp; due time equals registration plus saved duration. Measured feature exceeds frozen threshold. Collect indicator first; obtain reference quote timestamp at/after evidence availability. Await suitable quote when market data older. Direction, target and costs match saved test plan.

Resolve preceding same-signal endpoint before another forecast. New reference quote strictly follows previous realized endpoint. Event IDs unique; consecutive attention spikes form one episode. Report residual dependence between events.

Price adapter uses configured exchange calendar for actual session closing times, including early closes and holidays. Accept closing price only from response captured at least 30 minutes after actual close. Missing session time leaves affected prediction pending with reported blocker. Manual observations retain supplied actual timestamps.

Evaluate first actual close at/after due, within seven calendar days. Missing/late prices remain pending. Ingest corporate actions before evaluation. Split crossing forecast window invalidates signal. Late split or legacy overlapping/shared endpoint appends correction and retains original result. [Delivery](operations.md#claim-deliver-acknowledge) handles affected alerts.

## Performance review

`report --signal ID` shows every registered prediction, completed result, failure, pending endpoint and correction. Includes research returns after costs and ordinary buy-and-hold comparison across full prediction history. Compare measurement periods and unresolved predictions when assessing usefulness. User controls Dot's operation and schedules through [automations](../../squad-reconcile/references/deployment.md#scheduled-automations).

Root Python tests cover untouched-history qualification, one-shot results, corrected input errors, actual-close timing, complete future outcomes, delivery receipts and restart. Fixtures use temporary storage.
