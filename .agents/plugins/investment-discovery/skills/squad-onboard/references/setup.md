# Repository and runtime setup

[Onboarding checklist](../SKILL.md) owns conversation, prerequisites and order. Main Dot performs commands directly on **This Dot’s cloud computer**.

## Source and runtime

Use repository page URL user downloaded plugin from, including forks. Reuse URL already supplied. Resolve installed plugin version to matching release/tag there; ask downloaded release page/version when ambiguous. Save URL and selected release/tag as `gitops.ref` source.

Release ZIP bundles runtime under `skills/squad-onboard/scripts/`. Installed skills guide Dot; Git checkout supplies executable files and tests on computer. Reuse matching clean checkout after verifying origin/release, or clone supplied URL and check out selected release/tag. Checkout supports Git reconciliation. Read checkout's AGENTS.md; run commands from checkout root. `SQUAD_REPO` selects actual checkout path.

Python 3.11+ and timezone data required:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r .agents/skills/squad-onboard/scripts/requirements.txt
.venv/bin/python .agents/skills/squad-onboard/scripts/main.py onboarding
```

Use [computer access](cloud.md#computer-and-command-access) for actual permission failures; report concrete clone/dependency blockers.

## Configuration and storage commands

Copy checkout-root `.env.example` to `.env`; edit reviewed choices directly. `onboarding` supplies field names/types; [configuration](configuration.md) defines meanings. [Project environment](cloud.md#project-environment) owns quoting, permissions and explicit loading before each command.

After loading `.env`, prepare FTS and run Python checks using configured interpreter:

```sh
"$SQUAD_PYTHON" "$SQUAD_REPO/.agents/skills/squad-onboard/scripts/main.py" setup-runtime
"$SQUAD_PYTHON" "$SQUAD_REPO/.agents/skills/squad-reconcile/scripts/check.py"
```

Run `storage-plan`; set `SQUAD_STORAGE_DECISION_ACCEPTED=true` after user accepts arrangement, then reload `.env`. [Connected backup procedure](storage.md) owns inventory, `init`, upload acceptance and recovery. `doctor` checks local state; [automations](../../squad-reconcile/references/deployment.md#scheduled-automations) verify scheduled computer/store access.
