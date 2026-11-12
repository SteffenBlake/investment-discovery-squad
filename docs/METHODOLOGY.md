# Methodology and limits

## Historical qualification

1. Register an immutable candidate specification before its formal test. Keep source artifacts, mechanisms, horizon, market outcome and limitations.
2. Require `available_at < entry_at < exit_at <= now` for every row, distinct underlying events, chronological disjoint windows, and the registered horizon. A presumed publication lag is not proof of original public availability.
3. Split once: first 60% train, last 40% holdout. Windows cannot cross/overlap the boundary. Default minimums: 100 train, 100 test, 20 triggered holdout events.
4. Fix an upper 80th-percentile feature threshold on training data. Learn up/down direction from the difference between triggered and unconditional training returns. Never select these on the holdout.
5. Measure signed price returns minus the user's predeclared realistic round-trip cost estimate. Compare triggered mean net return with cash (zero) and an unconditional same-direction position over identical disjoint holdout windows. Require positive improvement over both.
6. Compute a one-sided circular-shift alignment p-value. Rotate the trigger mask relative to the ordered holdout returns, retaining within-series order/clustering. Include the observed alignment among all offsets. Require `p <= family_alpha / (k * (k + 1))`, where k is the lifetime formal-trial ordinal, including rejects and new versions. The thresholds sum to family_alpha, initially 0.05.
7. Store every result, full input dataset, digest and event evidence. A failed test rejects that immutable version. No rerunning/tuning the same version to erase failure.

The circular-shift p-value assumes approximate stationarity and exchangeable alignment under the null; disjoint windows alone do not prove independence. Alpha spending limits multiplicity only when underlying p-values are valid. It does not repair selectively chosen/incorrectly timestamped data or adaptively tuned holdouts. Do not recycle holdout results to design a passing revision. Use genuinely untouched evidence for revisions. The built-in fixed algorithm and explicit assumptions make the result auditable, not infallible.

Initial seed/source selection is not a survivorship-free search of all possible indicators. Markets change. A statistical pass is not proof of causation or guaranteed trading profitability. Price returns exclude dividends and do not reproduce actual fills. Transaction costs must match the strategy's realistic entry/exit conditions. The configured cost/statistical settings freeze when a production ledger is initialized.

## Forward validation

Historical passes transition through BACKTESTED to FORWARD_TESTING with zero live successes. CLI registration timestamps are assigned now, never accepted from an input file. Evidence must already exist, reference quotes must be current, and due times must be future and match the tested horizon. Direction/target/cost are frozen.

Reject overlapping forecast windows and repeated episode IDs for the same signal. The built-in adapter groups consecutive attention spikes into one episode; a new timestamp during the same spike does not create a new live attempt. Correlation between distinct real events can still exist and must be reported. All submitted predictions persist, including failures and unresolved outcomes.

At horizon expiry, evaluate the first eligible actual close, not the best intraperiod price. Endpoint data must be available. Missing data remain pending; no silent denominator changes. Revisions cannot change an existing result. A known split crossing a live window invalidates the signal for review rather than fabricating a return.

Three successful independently evaluated live attempts qualify a historically passing signal. They need not be consecutive. Qualification reports total registered/evaluated/pending attempts and all failures, even if the success rate is weak. Three wins are a minimum gate, not proof of reliability. The displayed Wilson interval is descriptive and assumes independent Bernoulli outcomes; repeated monitoring and stopping decisions and residual dependence limit its interpretation.

## Notification semantics

Third success evaluation, QUALIFIED transition and one outbox event commit in the same transaction. A notification is due even if the signal is not currently actionable. Every later report continues to include losses.

Dot's configured execution cadence determines detection delay. Delivery runs immediately within that execution, using supported messaging; a HIGH PRIORITY label does not guarantee OS critical-alert delivery. A persistent claim prevents duplicates while a send/receipt is uncertain. Exactly-once external delivery across an ambiguous transport failure cannot be guaranteed without transport idempotency or reconciliation. This project preserves ambiguity and refuses blind resend rather than pretending it disappeared.

## Acceptance

`python3 -m squad demo` creates causal synthetic historical data, computes a real passing validation result, then registers four distinct disjoint synthetic live forecasts. The additional loss matures before the third success so the initial immediate alert can truthfully contain 3-of-4. It tests no early alert, same-execution qualification, complete failure record, saved delivery receipt, restart persistence and deduplication.

Synthetic clocks/data are isolated from production. The demo uses a synthetic delivery receipt and does not test your actual Dot account/phone. Onboarding performs a separate labelled real transport test before claiming activation.
