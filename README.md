# Investment discovery for Dot

Dot researches existing market history for useful patterns. Develop idea on earlier data, freeze test plan, then test once against untouched later data. Statistically supported result qualifies idea for further investigation. Failed ideas stay rejected; related new premises follow strict retry rules.

Qualified ideas produce future predictions. Review complete results, pending predictions, returns after costs, ordinary buy-and-hold comparison and limitations. User controls Dot's operation and schedules. [Historical method](.agents/plugins/investment-discovery/skills/squad-research/references/methodology.md); [prediction results](.agents/plugins/investment-discovery/skills/squad-monitor/references/validation.md).

Paste current portfolio and available cash; ask what to do next. Dot explains buy/hold/sell/cash choices using research. Python sizes eligible purchases from supplied cash, prices and fees. Each request uses supplied current account.

Private Ladybug database stores research; SQLite stores test plans, predictions/results and receipts. Complete recovery ZIP updates same private Google Drive file. Drive version history holds earlier contents under normal expiry rules. [Storage/recovery](.agents/plugins/investment-discovery/skills/squad-onboard/references/storage.md).

## Install

Need Dot, permission to upload plugins in ChatGPT and authorized private Google Drive storage.

1. Create Dot in ChatGPT.
2. Download `investment-discovery-plugin-<tag>.zip` from [latest release](https://github.com/SteffenBlake/investment-discovery-squad/releases/latest).
3. Upload ZIP through ChatGPT's plugin upload and install **investment-discovery**.
4. Tell Dot: “Use squad-onboard checklist to set this up directly on This Dot’s cloud computer.”

[Setup](.agents/plugins/investment-discovery/skills/squad-onboard/references/setup.md) covers runtime, personal choices, storage consent, account access, backups and scheduled automations.

## Releases

Publish a GitHub release, including a prerelease. [Release workflow](.github/workflows/release.yml) builds tagged source and attaches `investment-discovery-plugin-<tag>.zip` to release assets, e.g. `investment-discovery-plugin-v1.2.3.zip`. Download that ZIP for ChatGPT plugin upload. Rerunning workflow replaces same-named asset. GitHub supplies workflow token automatically.

ZIP contains one plugin with root `plugin.json`, five skills, runtime resources and license, following [OpenAI package requirements](https://developers.openai.com/plugins/deploy/submission-errors#plugin-root-errors).
