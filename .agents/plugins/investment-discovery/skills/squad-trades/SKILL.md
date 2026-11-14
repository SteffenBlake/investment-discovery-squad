---
name: squad-trades
description: Recommend next actions from user-supplied current portfolio, available cash and investment research.
---
Follow [computer access](../squad-onboard/references/cloud.md#computer-and-command-access); run sibling `squad-onboard/scripts/main.py` on Dot computer. User executes orders.

1. Start from portfolio and available cash pasted with current request. [Portfolio](references/portfolio.md) owns input and advice flow.
2. Apply squad-monitor's due outcome/delivery work; review research corrections. Run `knowledge context --portfolio PRIVATE_FILE --query TERMS`; inspect sources, dates, directed relationships, contradictions, missing symbols and truncation. Fetch fresh evidence where needed.
3. Explain buy/hold/sell/cash choices against supplied account, user restrictions and evidence. `report --signal ID` supplies complete prediction history.
4. For fresh qualified bullish forecast, `idea --prediction ID --portfolio PRIVATE_FILE` calculates affordable purchase from supplied cash, price, fees and lot size. Explain quantity, venue, quote time/source, price limit, total cash, rationale, horizon and review conditions. Treat multiple options as alternatives unless jointly sized within supplied cash.
5. Remove completed private input files. Apply [backup procedure](../squad-onboard/references/storage.md#connected-backup-procedure) for research changes.
