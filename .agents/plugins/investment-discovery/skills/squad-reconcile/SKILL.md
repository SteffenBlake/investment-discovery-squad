---
name: squad-reconcile
description: Update investment research source, workspace plugin and scheduled jobs while preserving saved research and user pauses.
---
Read [deployment](references/deployment.md); it owns source updates and initial/later task setup.

1. Resolve [saved cloud thread](../squad-onboard/references/cloud.md#bind-and-verify-owner), approved checkout/ref/interpreter and configuration. Run shared sibling `squad-onboard/scripts/main.py deployment sync` in owner cloud container for approved fast-forward update. Start fresh process afterward.
2. Install changed requirements, prepare FTS and run relevant Python tests through `scripts/check.py`. Repository skill paths symlink to plugin folders. `scripts/bundle.py` builds licensed release archive.
3. Refresh workspace marketplace and read sync status through deployment procedure.
4. Reconcile jobs using deployment's [native tasks](references/deployment.md#native-tasks), including live-trial expiry and user pauses.
5. Apply [storage recovery](../squad-onboard/references/storage.md#recovery) when stores missing or damaged.
