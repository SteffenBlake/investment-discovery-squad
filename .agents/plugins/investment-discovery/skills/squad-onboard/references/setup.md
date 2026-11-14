# Set up investment discovery

Handle computer work; obtain personal choices, account authorization and storage consent from user context.

## Source and runtime

Ask user: “What repository URL did you download this plugin from? Paste that repository's page link.” Reuse URL already supplied in user context. Resolve installed plugin version to matching release/tag in that repository; if unclear, ask for downloaded release's page link or version. Save repository URL and selected release/tag as source for setup and `gitops.ref`.

Follow [child-task setup](cloud.md#durable-child-task): reuse suitable durable child task (cloud thread), or create one with fresh cloud container using available saved environment configuration. Dot performs creation and continues setup there, including first run with empty connected-environment list.

Release ZIP bundles executable runtime at `skills/squad-onboard/scripts/` plus sibling skills/references. Dot reads installed skills directly; child container receives executable files by cloning user-supplied repository. Checkout required for Git-based reconciliation and repository test runner. In child container, reuse matching clean checkout after verifying origin and release, or clone supplied URL and check out selected release/tag. Read checkout's AGENTS.md. Set `SQUAD_REPO` to actual checkout path; run commands below from checkout root. Installed skill files remain separately available to Dot. Report clone/access failure with exact missing capability.

Python 3.11+ and timezone data required:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r .agents/skills/squad-onboard/scripts/requirements.txt
.venv/bin/python .agents/skills/squad-onboard/scripts/main.py setup-runtime
.venv/bin/python .agents/skills/squad-onboard/scripts/main.py onboarding
.venv/bin/python .agents/skills/squad-reconcile/scripts/check.py
```

## Configuration and storage

Use [configuration](configuration.md) for personal choices. `onboarding` generates environment variable names/types. Configure child runtime through [documented environment controls](cloud.md#runtime-settings-and-credentials) and [Google authorization](cloud.md#google-authorization-and-renewal). Missing persistent settings/credential access blocks unattended operation; report specific gap while continuing independent preparation.

Run `storage-plan` before acceptance. Explain private research/prediction files, original sources, Drive budget and recovery window. After user accepts, initialize following [storage](storage.md#provision-or-adopt). `init` checks remote backup target before creating empty stores; existing backup requires recovery. Then run `doctor` and `backup cloud`.

Research existing history using [one-shot method](../../squad-research/references/methodology.md). Initial future trial follows [30-day procedure](../../squad-monitor/references/validation.md#live-trial).

## Initial scheduled automations

Use [automation procedure](../../squad-reconcile/references/deployment.md#scheduled-automations) to create/update installation's scheduled automations and verify automation wake → Dot → saved child task → original stores → returned result. Send setup status through `user_message.send_message` with `channel="chatgpt"`; save returned message reference privately. Report completed work, pending checks and blockers accurately. Push delivery depends on user's app settings.

Report durable child task title/reference, installed source/runtime, private paths, backup result, saved automation IDs, observed schedule/thread result and setup message receipt, plus unresolved steps.
