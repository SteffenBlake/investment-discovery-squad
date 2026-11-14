# Investment discovery for Dot

Dot researches existing market history for useful patterns. Develop idea on earlier data, freeze test plan, then test once against untouched later data. Statistically supported result qualifies idea for further investigation. Failed ideas stay rejected; related new premises follow strict retry rules.

Qualified ideas produce future predictions during initial trial lasting at most 30 days. Review all results, pending predictions, returns after costs and ordinary investment comparison before choosing whether to continue. [Historical method](.agents/skills/squad-research/references/methodology.md) and [live trial](.agents/skills/squad-monitor/references/validation.md#live-trial).

Paste current holdings and available uninvested cash for portfolio assessment. Dot explains hold/buy/sell/cash choices using current evidence. Python sizes eligible purchases from supplied cash and fees. You execute trades and report fills; updated portfolios capture account changes.

Private Ladybug database stores research; SQLite stores test plans, predictions/results, portfolios and receipts. Complete recovery ZIPs upload to private Google Drive folder. Upload checks Drive's reported checksum; latest three successful backups retained. [Storage/recovery](.agents/skills/squad-onboard/references/storage.md).

## Install

Need Dot, workspace-admin plugin import, GitHub access and authorized private Google Drive storage.

1. Create Dot in ChatGPT.
2. Open **Admin → Plugins → Add → Import marketplace**. Source: `https://github.com/SteffenBlake/investment-discovery-squad`; Path: empty; Branch: `main` or reviewed fork/ref.
3. Authorize GitHub and install **investment-discovery**. [Workspace import](https://learn.chatgpt.com/docs/enterprise/plugin-management).
4. Tell Dot: “Use squad-onboard and follow bundled references/setup.md to set this up on your cloud computer.”

[Setup](.agents/skills/squad-onboard/references/setup.md) covers runtime, personal choices, storage consent, account access, backups and scheduled jobs.
