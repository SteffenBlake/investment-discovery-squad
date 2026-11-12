# Git-managed Dot workflow operations

This implementation follows documented agent skills, native plugin packaging and native scheduled tasks. There is no official Dot-specific GitOps scheduler schema/certification claimed here. OpenGitOps defines declarative, versioned, automatically pulled and continuously reconciled desired state. This project requires an approved Git ref, fast-forward-only pulls and continuous native reconciliation. [OpenGitOps principles](https://opengitops.dev/), [OpenAI workflow conventions](https://learn.chatgpt.com/docs/learn/best-practices).

## Source and distribution

Canonical method files live in `.agents/skills/squad-*`. `scripts/build_plugin.py` generates byte-identical copies in the native plugin; CI rejects drift. `.agents/plugins/marketplace.json` is a native catalog, `plugins/investment-discovery/plugin.json` a portable Agent Plugins manifest, and `.codex/config.toml` uses documented trusted-project enablement. An instruction plugin expects an accessible checkout/Python runtime; it does not invent server execution.

Register the Git-backed marketplace with `codex plugin marketplace add`, selecting a real approved source/ref. Use the host Plugins directory to install/test. `codex plugin marketplace upgrade` refreshes Git marketplace snapshots; the actual installed cache must also be refreshed/read and verified through supported host controls. Source changes alone do not prove a loaded skill changed. Workspace-admin GitHub import/sync is not part of this deployment workflow. [Packaging and refresh](https://developers.openai.com/plugins/build/plugins), [admin sync](https://learn.chatgpt.com/docs/enterprise/plugin-management).

The repo and plugin expose the same skill names; choose the installed plugin or matching repo skill consistently. Deployment requires the digest of actually loaded canonical skill contents to match the source. Do not mix cached older plugin methods with newer Python.

## Desired state

Versioned workflows.json declares logical tasks and skill names. Required individual native SQUAD_* configuration supplies per-user timing, timezone, notification destination, worker preference and runtime. Their composition generates thin native task prompts. Financial profile data do not get copied into Git or full method text into task prompts. Config revisions are retained in the private knowledge ledger.

`deployment plan` returns committed revision/source digest, skill digest, ledger identity, stable `squad/PROFILE_ID/TASK` keys, thin prompts and expected native task fields. This is a **project planner format**, not an OpenAI import API. It cannot install tasks itself.

`deployment plan --observed FILE` compares actual normalized native task readback:

- Missing enabled key → create.
- Changed enabled task fields → update existing native ID.
- Duplicate project keys → resolve/pause extras; do not record success.
- Disabled/obsolete project key → pause.
- Unrelated profile/task → preserve.
- Matching state → no action.

Only real native platform tools perform creates/updates/disables. Preserve exact returned IDs. After uncertain responses, inspect actual state before retry. Native schedule RRULE/timezone and model/runtime representation must be supported on the actual surface; unsupported fields are blockers, not fabricated matching observations. Worker model null means host default; Dot's internal model routing is not pinned.

## Readback contract

Normalize *observed platform values* into a private JSON object. Do not copy desired values as if observed:

```text
observed_at: fresh ISO timestamp (within 15 minutes)
tasks: [{key, id, title, prompt, rrule, timezone, is_enabled,
         model, reasoning_effort, runtime_id}]
loaded_skills: {source: repository|installed_plugin, digest: actual loaded contents digest}
runtime_probe: {setup_identity, database_path, knowledge_path, runtime_kind,
                graph_setup_identity, runtime_id,
                observed_at, independent_run_receipt}
delivery: {destination, receipt}
```

Compute loaded skill digest using the same relative `squad-NAME/...` path → file-text mapping as source_state; use the actual loaded files, not just an asserted package version. A repo route reads canonical files directly; an installed route inspects the installed bundle. If the host cannot expose/verify matching contents, report that limitation.

An independent actual saved-worker execution must reopen both the LadybugDB graph and SQLite ledger on the central owner and return the matching identities/paths/runtime. Native environment variables must be injected there, not assumed to transfer from a separate Codex Cloud task. A labelled setup notification must have a real receipt at the configured destination. Test logs and accepted execution IDs alone are insufficient. `deployment record --file FILE` checks shape, freshness, drift, source cleanliness, skill digest and identity, requires a current uploaded/downloaded/restore-tested cloud backup event, then records immutable evidence in SQLite plus a private projection. It cannot independently authenticate a platform receipt supplied as JSON; the actual tools/agent observations are the trust boundary.

`deployment check --observed FILE` verifies current source/config against the applied observation and fresh task readback. Without --observed it checks only the cached application record, not current external task enablement. Production run/research/forecast/idea/claim commands require current applied source/config. A code/profile change therefore blocks financial operation until reconciled. Initial --preflight collection is limited to ledgers with no submitted predictions.

## Pull, reconcile and rollback

The required setup uses gitops.update_policy=fast_forward, the user's approved ref, and an enabled reconcile schedule. Each native squad-reconcile run observes tasks and checks source. `deployment sync` fetches origin's selected ref and merges with --ff-only on a clean tree; no reset/force/discard operation exists. Start a fresh process after updates, run relevant checks, refresh the actual loaded skills and reconcile native tasks. Code changes must be reviewed/committed; no untracked/dirty revision may be recorded as deployed.

A failed/disabled reconciler or unreachable owner means required automatic convergence is unavailable; report the incident when execution resumes. Never fall back to a different deployment mode.

Rollback selects a reviewed compatible Git revision, refreshes the plugin and reapplies native desired state. Never rewind prediction evidence, reset the database or restore old chat state to hide outcomes. Stop if the target code cannot read the DB schema. Database restore is a separate reviewed recovery operation with notification reconciliation. A restore_completed event invalidates cached deployment even if Git/configuration signatures are unchanged; obtain fresh probe/task/delivery observations and a verified cloud archive before resuming. [Storage recovery](STORAGE.md).

## Cloud configuration boundary

Plans contain only the required individual native-variable binding; they never copy a completed profile or credentials into prompts. Dot cloud is the sole owner; researchers in isolated environments hand back batches. A plugin install does not itself mount a shared filesystem. See [cloud routing and secrets](CLOUD.md). Actual native tools, not a project-invented scheduler API, provide runtime binding and task mutation.
