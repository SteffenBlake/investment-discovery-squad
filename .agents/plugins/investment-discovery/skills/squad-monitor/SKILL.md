---
name: squad-monitor
description: Evaluate forecasts, deliver historically qualified research alerts and review a live trial lasting at most 30 days.
---
Use central owner's sibling `squad-onboard/scripts/main.py`.

1. Run `run`; inspect JSON/stderr, errors, blocked predictions, corrections and trial status. `report --signal ID` retains full history.
2. Apply [operations](references/operations.md) for delivery and continuation work. [Validation](references/validation.md) owns endpoint rules and trial review.
3. Review-required/stopped trial pauses research/monitor jobs through [task procedure](../squad-reconcile/references/deployment.md#native-tasks). Present performance; continuation requires user's decision.
4. Apply shared [backup procedure](../squad-onboard/references/storage.md#full-cloud-backup). Operations owns incidents; portfolio/fill/exit questions use squad-trades.
