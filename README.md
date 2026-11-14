# Investment discovery for Dot

Dot researches existing market history for useful patterns. Develop idea on earlier data, freeze test plan, then test once against untouched later data. Statistically supported result qualifies idea for further investigation. Failed ideas stay rejected; related new premises follow strict retry rules.

Qualified ideas produce future predictions during initial trial lasting at most 30 days. Review all results, pending predictions, returns after costs and ordinary investment comparison before choosing whether to continue. [Historical method](.agents/plugins/investment-discovery/skills/squad-research/references/methodology.md) and [live trial](.agents/plugins/investment-discovery/skills/squad-monitor/references/validation.md#live-trial).

Paste current holdings and available uninvested cash for portfolio assessment. Dot explains hold/buy/sell/cash choices using current evidence. Python sizes eligible purchases from supplied cash and fees. You execute trades and report fills; updated portfolios capture account changes.

Private Ladybug database stores research; SQLite stores test plans, predictions/results, portfolios and receipts. Complete recovery ZIPs upload to private Google Drive folder. Upload checks Drive's reported checksum; latest three successful backups retained. [Storage/recovery](.agents/plugins/investment-discovery/skills/squad-onboard/references/storage.md).

## Install

Need Dot, permission to upload plugins in ChatGPT and authorized private Google Drive storage.

1. Create Dot in ChatGPT.
2. Download `investment-discovery-plugin.zip` from [latest release](https://github.com/SteffenBlake/investment-discovery-squad/releases/latest).
3. Upload ZIP through ChatGPT's plugin upload and install **investment-discovery**.
4. Tell Dot: “Use squad-onboard and follow bundled references/setup.md to set this up on your cloud computer.”

[Setup](.agents/plugins/investment-discovery/skills/squad-onboard/references/setup.md) covers runtime, personal choices, storage consent, account access, backups and scheduled jobs.

## Releases

Publish a GitHub release, including a prerelease. [Release workflow](.github/workflows/release.yml) builds tagged source and attaches `investment-discovery-plugin.zip` to release assets. Download that ZIP for ChatGPT plugin upload. Rerunning workflow replaces same-named asset. GitHub supplies workflow token automatically.

ZIP contains one plugin with root `plugin.json`, five skills, runtime resources and license, following [OpenAI package requirements](https://developers.openai.com/plugins/deploy/submission-errors#plugin-root-errors).
