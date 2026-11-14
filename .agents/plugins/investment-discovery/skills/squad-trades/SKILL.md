---
name: squad-trades
description: Prepare configured human-executed trade recommendations, record actual reported fills, and review exits for qualified investment discovery forecasts.
---
Use configured central owner and shared sibling `squad-onboard/scripts/main.py`. Human places orders. [Configuration](../squad-onboard/references/configuration.md) supplies actual budget/currency, broker, jurisdiction, costs, lots and resource limits.

1. Perform squad-monitor's due outcome/delivery work before assessing advice. Review returned research corrections. Normalize actual portfolio snapshot per [portfolio](references/portfolio.md); run `knowledge context --portfolio PRIVATE_FILE --query TERMS`. Assess directed relationships, source dates, contradictions, missing symbols and truncation; retrieve fresh evidence when material facts changed. Explain buy/hold/sell/cash reasoning.
2. Actual supplied cash and holdings control purchase sizing; reported fills retain execution history. Use `report --signal ID` for complete outcomes/corrections.
3. For fresh qualified bullish forecast, run `idea --prediction ID --portfolio PRIVATE_FILE`. Explain symbol/venue, side/quantity, quote source/time/delay, limit/notional/currency, estimated entry fee and total cash, rationale/target/horizon, exit/invalidation review and skip conditions. User confirms broker spread, fees, settled cash, pending orders and restrictions.
4. Record actual fills using `fill --file PRIVATE_FILE`; [trade commands](../squad-onboard/references/commands.md#trades) owns fields/idempotency. [Portfolio follow-up](references/portfolio.md#fills-and-exit-follow-up) uses actual native saved-task and task-run/message-history tools with readback/receipts for exit reviews.
5. Handle alerts through squad-monitor, then `backup-due` per [storage](../squad-onboard/references/storage.md#full-cloud-backup). Python owns numerical sizing and reported fill records.
