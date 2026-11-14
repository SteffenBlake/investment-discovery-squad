---
name: squad-onboard
description: Set up historical investment research, private storage, three-copy Drive backups and a live trial lasting at most 30 days.
---
Read [setup](references/setup.md); complete computer work using user's personal choices and account consent.

[Configuration](references/configuration.md) owns settings; [cloud](references/cloud.md) owns runtime/OAuth bindings; [storage](references/storage.md) owns provisioning, backups and recovery. [Deployment](../squad-reconcile/references/deployment.md#scheduled-automations) owns scheduled automations.

Shared runtime: `scripts/main.py`; Python 3.11+, pinned `scripts/requirements.txt`, timezone data and `setup-runtime` FTS preparation. Bind approved Git checkout through `SQUAD_REPO`. [Commands](references/commands.md) lists operations.
