---
name: squad-reconcile
description: Update investment research source, workspace plugin and scheduled automations while preserving saved research and user pauses.
---
Read [deployment](references/deployment.md); it owns source updates and initial/later automation setup.

1. Attach [Dot computer](../squad-onboard/references/cloud.md#computer-and-command-access); resolve approved checkout/ref/interpreter and project `.env` configuration. Run shared sibling `squad-onboard/scripts/main.py deployment sync` there for approved fast-forward update. Start fresh process afterward; load project `.env`.
2. Install changed requirements, prepare FTS and run relevant Python tests through `scripts/check.py`. Repository skill paths symlink to plugin folders. `scripts/bundle.py` builds licensed release archive.
3. Refresh installed plugin through original installation route; read actual update result through deployment procedure.
4. Reconcile automations using deployment's [scheduled automations](references/deployment.md#scheduled-automations), preserving user pauses.
5. Apply [storage recovery](../squad-onboard/references/storage.md#recovery) when stores missing or damaged.
