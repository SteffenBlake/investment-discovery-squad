# Dot computer, environment and connected Drive

[Onboarding checklist](../SKILL.md) owns order/questions. Main Dot reads installed skills and executes setup/runtime directly on its computer. Research batches enter that computer's original stores; runtime lock serializes commands.

## Computer and command access

Discover current `environment_management.list` / `attach` tools. Select list entry described **This Dot’s cloud computer**; attach its returned `environment_id`. Missing entry: user opens Dot icon atop conversation → **Your dot’s computer**; re-list and attach. Owner-facing label and tool description identify same computer. Record actual environment ID privately.

Use exposed command tool on attached computer. Command sandbox permissions and underlying filesystem permissions have separate causes. For required write blocked by command sandbox, use available approval/escalation mechanism under current permissions; retry specific authorized operation. Report actual result. Keep existing files when testing; explain artifacts requiring permanent deletion approval.

## Project environment

Copy repository-root `.env.example` to `.env`; agent edits reviewed values directly. Example supplies runtime defaults; blanks require user choices, broker terms or observed computer/folder IDs. Keep `.env` gitignored with mode 0600. Use shell-quoted assignments: raw strings, quoted JSON arrays, JSON numbers/booleans and `null` for host model defaults. Connected Drive keeps its own authorization.

Each command session explicitly loads `.env` from checkout root before invoking runtime:

```sh
cd ACTUAL_CHECKOUT
set -a
. ./.env
set +a
"$SQUAD_PYTHON" "$SQUAD_REPO/.agents/skills/squad-onboard/scripts/main.py" doctor
```

Use same loading sequence for setup, later commands and scheduled execution. Verify new command session and Python child receive required names/correct values; keep private values out of reports. Scheduled persistence remains unverified until actual scheduled run succeeds.

Ladybug `SQUAD_LADYBUG_HOME` selects absolute writable extension-storage directory; example places it beside live-data directory. `setup-runtime` and later commands use same value. Runtime creates private directories before setting Ladybug `home_directory`. Default without override uses system temporary directory under `squad-runtime-<user ID>/ladybug`; cleanup requires rerunning `setup-runtime`.

## Connected Drive

Discover Google Drive connector tools by current names. Missing integration: use plugin search/suggestion connection flow; rediscover after connection changes. Successful `get_profile({})` read verifies account connection. Python exchanges private inventory/upload-receipt JSON with Dot; connector authorization stays with integration.

Supported operations: `create_folder({name,parent_folder})`; `list_folder({url,top_k})`; paginated `search({special_filter_query_str,item_type,page_token,topn})`; `upload_file({file_uri,file_name,mime_type,parent_folder_id})`; `update_file({fileId,file_uri,mime_type,name})` replaces raw file contents while preserving ID; `get_file_metadata({fileId,fields})`; deliberate raw `fetch({url,download_raw_file:true,include_base64:false})`; permanent `delete_file({url})`. Inspect exposed schemas; upload needs absolute local path and raw parent folder ID. Listing takes folder URL or `root`; `top_k` is bound, not cursor. Search can lag listing. [Storage](storage.md) owns inventory/receipts, same-file updates and recovery.

Verify computer → connected Drive path through actual reviewed backup upload. Report returned file identity/metadata and upload acceptance. Deliberate restore and scheduled computer/store route require separately observed results. Restrict command network to required source/dependency/feed destinations; connector manages Drive requests.
