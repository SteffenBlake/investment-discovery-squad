# Operations

Read [STORAGE.md](STORAGE.md) for explicit provisioning/adoption, privacy, backups and recovery; [GITOPS.md](GITOPS.md) for native task deployment/drift/update; [ONBOARDING.md](ONBOARDING.md) for user variables.

## Notification state

| State | Meaning | Action |
| --- | --- | --- |
| pending | Qualification committed | Claim and deliver at this supported execution |
| claimed | Sender owns it; delivery may be in progress/unknown | Reconcile, never blindly resend |
| delivered | Actual receipt recorded | Do not send that qualification again |

Qualification and one outbox event commit atomically after the third independent live success. All prior failures/pending attempts remain in the record. A live opportunity is not required for qualification notification. Dot uses the configured supported destination; device push and OS urgency remain outside this CLI's guarantees.

A sender that dies after delivery but before ack must find the existing message and acknowledge its actual receipt. Confirmed non-delivery permits release. Ambiguity stays claimed and becomes an operational issue; claims never auto-expire. Exactly-once external delivery requires transport idempotency or reconciliation, not wishful retry logic.

## Incidents

- Missing DB/identity mismatch: stop, verify runtime/storage; never initialize a replacement.
- Changed code/profile/loaded plugin/native tasks: reconcile before financial operation.
- Feed failure: preserve error evidence; other queued alerts remain actionable; no synthetic substitute or unapproved spending.
- Stale quote: no new forecast/entry. Daily closes are not current intraday quotes.
- Missing or seven-day-late endpoint: keep pending with a blocker; no favorable later substitution.
- Unknown historical release timing: collect first-seen snapshots or find original archives; no assumed-lag pass.
- Known split or mechanism breakdown: record invalidation/degradation and preserve prior evidence.
- Reported fill discrepancy: reconcile actual user report before more cash-sensitive ideas; never infer holdings from approvals.

Review held ideas at their horizons/invalidation and retain actual follow-up receipts to avoid repeated exit reminders. User executes every order and reports actual fills. Research-only profiles have no entry ideas. Disable project tasks and follow-ups to stop; pausing a Dot conversation does not necessarily cancel saved tasks. [Official controls](https://learn.chatgpt.com/docs/dots/controls).

`sh scripts/check.sh` verifies synthetic acceptance, portability, storage ownership/adoption, native packaging and reconciliation invariants after runtime setup. Tests exercise real LadybugDB search/export/import and a fake Drive transport; they do not prove access to a real Google account. Live runtime, task availability and delivery are tested separately during each user's onboarding; tests do not activate an account or certify a profitable signal.

## Research, portfolio context and cloud recovery

Research workers return batches described in [KNOWLEDGE.md](KNOWLEDGE.md); only the central owner ingests them. The trading agent uses knowledge context with the user's actual portfolio before reasoning. Check dated sources, contradictions, missing symbols and truncation. Read-only context does not create fills or replace the cash ledger.

After handling alerts, call backup-due after monitor/research/fill work. It uploads changed evidence or an overdue archive and verifies actual downloaded bytes with a staged restore. Local snapshots/legacy SQLite backups are not complete cloud recovery. Preserve pending-upload.json after ambiguous upload responses; the next call reconciles the same archive. Report quota/authentication/verification failures, keep evidence, and never buy storage automatically.

Periodically verify a retained remote archive. Stop relevant tasks before restore, use a new empty data directory, preserve original identities and reconcile post-backup notification history before resuming. A restore marker blocks partially installed state. An original identity alone does not mean deployment remains active after recovery. [Recovery procedure](STORAGE.md).
