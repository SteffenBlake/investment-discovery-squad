# Set up investment discovery

Handle computer work; obtain personal choices, account authorization and storage consent from user context.

## Source and runtime

Resolve registered repository and approved ref from workspace marketplace. Reuse matching clean checkout on persistent Dot cloud owner or clone through authorized Git access. Read checkout's AGENTS.md. [Cloud](cloud.md) owns runtime bindings and account access.

Python 3.11+ and timezone data required:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r .agents/skills/squad-onboard/scripts/requirements.txt
.venv/bin/python .agents/skills/squad-onboard/scripts/main.py setup-runtime
.venv/bin/python .agents/skills/squad-onboard/scripts/main.py onboarding
.venv/bin/python .agents/skills/squad-reconcile/scripts/check.py
```

Installed plugin includes sibling squad-onboard runtime/resources. Bind `SQUAD_REPO` separately to approved checkout.

## Configuration and storage

Use [configuration](configuration.md) for personal choices. `onboarding` generates variable names/types. Bind native settings and [Google secrets](cloud.md#google-authorization-and-renewal) on owner.

Run `storage-plan` before acceptance. Explain private research/prediction files, original sources, Drive budget and recovery window. After user accepts, initialize following [storage](storage.md#provision-or-adopt). `init` checks remote backup target before creating empty stores; existing backup requires recovery. Then run `doctor` and `backup cloud`.

Research existing history using [one-shot method](../../squad-research/references/methodology.md). Initial future trial follows [30-day procedure](../../squad-monitor/references/validation.md#live-trial).

## Initial native tasks

Use [native task procedure](../../squad-reconcile/references/deployment.md#native-tasks) to create or update this installation's jobs and verify owner execution. Send labelled setup notification using [delivery requirements](../../squad-monitor/references/operations.md#claim-deliver-acknowledge); retain message ID/link in private history.

Report installed source/runtime, private paths, backup result, saved task IDs, owner run and setup message receipt, plus unresolved steps.
