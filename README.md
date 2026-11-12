# Investment discovery for Dot

## Install

Open [ChatGPT](https://chatgpt.com) in a desktop web browser. Create an account or sign in, then select the workspace you will use for this project.

You need:

- **Access to Dot** on that account. Check [Dot availability](https://learn.chatgpt.com/docs/dots#access).
- **Workspace-admin access** to import the project through **Admin → Plugins**. This permission lets you manage the workspace's plugins. [Import requirements](https://learn.chatgpt.com/docs/enterprise/plugin-management).
- **A GitHub account** for ChatGPT's project-import and update connection.
- **A Google account with available Drive storage** for private backups.

### Add the project

1. In ChatGPT, open **Dots** and follow the introduction to create your Dot. [Dot setup](https://learn.chatgpt.com/docs/dots/getting-started).
2. Open **Admin → Plugins → Add → Import marketplace**. This adds the repository's plugin to your workspace's catalog of add-ons.
3. Enter `https://github.com/SteffenBlake/investment-discovery-squad` as **Source**, leave **Path** empty, and enter `main` under **Branch, tag, or commit**. Select **Import marketplace**, authorize GitHub access, and wait for the import to finish.
4. Open ChatGPT's **Plugins** page and install **investment-discovery**. Return to your Dot and send:

```text
Use squad-onboard and follow its bundled SETUP.md to set this up on your cloud computer.
```

Dot installs the software and guides you through your budget, broker, allowed investments, account authorization and schedules. Setup finishes by testing backups, scheduled execution and notification delivery. The complete instructions are in [DOT_START_HERE.md](DOT_START_HERE.md), also bundled with the plugin.

## What this repo is

Investment Discovery Squad is a research workflow for Dot, ChatGPT's assistant for ongoing work. It investigates whether clues such as shipping activity, hiring or supply shortages can predict market movements. It tests those ideas, tracks their predictions and alerts you when the evidence meets its validation requirements.

You can paste your current portfolio into chat and ask, **“What should we do with our investments today?”** Dot searches the collected research, weighs supporting and contradictory evidence, and explains recommended actions. You execute the trades and report what filled. Your budget, broker, location, costs and investment choices guide its work.

## How it works

1. **Research:** Dot saves dated findings, original sources, affected investments and proposed connections, including contrary evidence.
2. **Historical testing:** Python programs test proposed indicators against past market results, accounting for trading costs and when information became available.
3. **Live predictions and alerts:** Historically passing indicators produce precise predictions recorded before the movement. Scheduled checks evaluate them at their deadlines and retain every success, failure and unresolved result. Qualification requires at least three independent successful live predictions. Alerts report the full record, uncertainty and limitations.
4. **Private records:** LadybugDB stores connected research and sources. SQLite stores numerical tests, predictions, alert receipts and reported trades. These records, personal settings and credentials live privately on Dot's cloud computer, outside Git. The repository holds shared instructions and software.
5. **Recovery:** Complete backups of both stores and source files go to your private Google Drive folder. Each new backup is downloaded and restored into a test location to check that the saved work can be recovered.
