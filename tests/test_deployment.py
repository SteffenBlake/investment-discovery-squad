import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from squad.configuration import settings
from squad.deployment import check, compare, deployment_command, desired, record
from squad.storage import open_store
from squad.knowledge import Knowledge
from squad.backups import covered_sequence, ledger_revision, artifact_revision
from squad.util import stamp, now_utc
from tests.fixtures import completed_profile


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.profile = completed_profile(self.temp.name)
        self.settings = settings(self.profile)
        store = open_store(self.settings, initialize=True)
        with Knowledge(self.settings, store.identity, create=True) as graph:
            revision = graph.meta("revision")
        # Synthetic test evidence only; real CLI writes this event after actual Drive verification.
        store.event("cloud_backup_verified", folder_id=self.settings["storage"]["cloud_backup"]["folder_id"],
                    file_id="synthetic://backup", covered_seq=covered_sequence(store), graph_revision=revision,
                    ledger_revision=ledger_revision(store), artifact_revision=artifact_revision(store),
                    verified_at=stamp(store.clock()), restore_tested=True)
        store.close()
        self.source = {"revision": "0" * 40, "digest": "fictional-code", "dirty": False, "skills_digest": "fictional-skills"}
        self.patch = patch("squad.deployment.source_state", return_value=self.source)
        self.patch.start()
        self.plan = desired(self.settings)

    def tearDown(self):
        self.patch.stop()
        self.temp.cleanup()

    def receipt(self):
        tasks = [{**task, "id": "synthetic-native-" + str(i)} for i, task in enumerate(self.plan["tasks"])]
        return {"observed_at": stamp(now_utc()), "tasks": tasks,
                "loaded_skills": {"digest": self.source["skills_digest"], "source": "repository"},
                "runtime_probe": {"setup_identity": self.plan["setup_identity"], "database_path": self.plan["database_path"],
                                  "knowledge_path": self.plan["knowledge_path"], "runtime_kind": self.plan["runtime_kind"],
                                  "graph_setup_identity": self.plan["graph_setup_identity"],
                                  "runtime_id": self.settings["storage"]["runtime_id"], "observed_at": stamp(now_utc()),
                                  "independent_run_receipt": "synthetic://worker-run"},
                "delivery": {"destination": self.settings["notification"]["destination"], "receipt": "synthetic://message"}}

    def test_native_task_plan_invokes_skills_and_has_no_copied_method(self):
        for task in self.plan["tasks"]:
            self.assertIn("Use $squad-", task["prompt"])
            self.assertIn("required individual native SQUAD_*", task["prompt"])
            self.assertNotIn(self.profile["starting_cash"], task["prompt"])
            self.assertIsNone(task["model"])

    def test_native_configuration_plan_needs_no_secret_profile_file(self):
        plan = desired(self.settings)
        for task in plan['tasks']:
            self.assertIn('required individual native SQUAD_*', task['prompt'])
            self.assertNotIn('SQUAD_PROFILE=environment', task['prompt'])
            self.assertNotIn(self.profile['starting_cash'], task['prompt'])

    def test_unverified_backup_blocks_activation(self):
        store = open_store(self.settings)
        try:
            store.event('new-evidence', proof='not yet uploaded')
        finally:
            store.close()
        with self.assertRaisesRegex(ValueError, 'restore-tested cloud backup'):
            record(self.plan, self.settings, self.receipt())

    def test_restore_invalidates_previous_deployment_even_with_same_signature(self):
        record(self.plan, self.settings, self.receipt())
        store = open_store(self.settings)
        try:
            store.event('restore_completed', requires_reconciliation=True)
        finally:
            store.close()
        result = check(self.plan, self.settings)
        self.assertFalse(result['current'])
        self.assertTrue(result['restore_requires_reconciliation'])

    def test_reconciliation_is_idempotent_and_preserves_foreign_tasks(self):
        observed = self.receipt()
        observed["tasks"].append({"key": "unrelated-job", "id": "foreign", "is_enabled": True})
        self.assertEqual(compare(self.plan, observed), [])
        record(self.plan, self.settings, observed)
        self.assertTrue(check(self.plan, self.settings, observed)["current"])
        self.assertEqual(compare(self.plan, observed), [])

    def test_missing_tasks_generate_creates_not_fabricated_ids(self):
        actions = compare(self.plan, {"tasks": []})
        self.assertEqual([a["action"] for a in actions], ["create"] * 3)
        self.assertTrue(all("id" not in a for a in actions))

    def test_schedule_and_model_drift_reuse_native_id(self):
        observed = self.receipt()
        observed["tasks"][0]["rrule"] = "RRULE:FREQ=WEEKLY"
        actions = compare(self.plan, observed)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["action"], "update")
        self.assertEqual(actions[0]["id"], "synthetic-native-0")

    def test_duplicates_block_receipt(self):
        observed = self.receipt()
        observed["tasks"].append({**observed["tasks"][0], "id": "duplicate"})
        with self.assertRaisesRegex(ValueError, "drift"):
            record(self.plan, self.settings, observed)

    def test_dirty_source_cannot_be_deployed(self):
        self.plan["ready_to_apply"] = False
        with self.assertRaisesRegex(ValueError, "Commit"):
            record(self.plan, self.settings, self.receipt())

    def test_stale_plugin_cache_cannot_pass_as_current(self):
        receipt = self.receipt()
        receipt["loaded_skills"]["digest"] = "old-content"
        with self.assertRaisesRegex(ValueError, "refresh"):
            record(self.plan, self.settings, receipt)

    def test_wrong_runtime_or_missing_delivery_not_deployed(self):
        for field in ("runtime_probe", "delivery"):
            receipt = self.receipt()
            receipt[field] = {}
            with self.assertRaises(ValueError):
                record(self.plan, self.settings, receipt)

    def test_code_change_invalidates_cached_deployment(self):
        record(self.plan, self.settings, self.receipt())
        changed = copy.deepcopy(self.plan)
        changed["signature"] = "new-signature"
        self.assertFalse(check(changed, self.settings)["current"])

    def test_all_private_configuration_changes_invalidate_deployment(self):
        record(self.plan, self.settings, self.receipt())
        changed = copy.deepcopy(self.settings)
        changed["notification"]["destination"] = "synthetic://new-destination"
        new_plan = desired(changed)
        self.assertNotEqual(new_plan["signature"], self.plan["signature"])
        self.assertFalse(check(new_plan, changed)["current"])

    def test_stale_external_readback_cannot_prove_current_state(self):
        receipt = self.receipt()
        record(self.plan, self.settings, receipt)
        receipt["observed_at"] = "2020-01-01T00:00:00+00:00"
        result = check(self.plan, self.settings, receipt)
        self.assertFalse(result["current"])
        self.assertEqual(result["actions"][-1]["action"], "refresh_readback")

    def test_editable_projection_is_not_deployment_authority(self):
        record(self.plan, self.settings, self.receipt())
        projection = Path(self.settings["storage"]["database_path"]).parent / "deployment.json"
        projection.write_text("{}")
        self.assertTrue(check(self.plan, self.settings)["current"])

    def test_disabled_and_obsolete_project_tasks_are_paused(self):
        observed = self.receipt()
        self.plan["tasks"][0]["is_enabled"] = False
        observed["tasks"].append({"key": "squad/test-owner/obsolete", "id": "old-task", "is_enabled": True})
        actions = compare(self.plan, observed)
        self.assertEqual({a["action"] for a in actions}, {"disable", "disable_obsolete"})

    def test_unsupported_update_policy_cannot_run_git_operations(self):
        from argparse import Namespace
        with patch("squad.deployment.git") as git:
            unsupported = copy.deepcopy(self.settings)
            unsupported["gitops"]["update_policy"] = "manual"
            with self.assertRaisesRegex(ValueError, "fast-forward"):
                deployment_command(Namespace(action="sync"), unsupported)
            git.assert_not_called()

    def test_automatic_pull_updates_clean_checkout_and_preserves_divergent_history(self):
        from argparse import Namespace
        folder = Path(self.temp.name)
        origin, publisher, checkout = (folder / name for name in ("origin.git", "publisher", "checkout"))

        def command(*args, cwd=None):
            return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()

        command("init", "--bare", str(origin))
        command("init", "-b", "main", str(publisher))
        command("config", "user.name", "Synthetic fixture", cwd=publisher)
        command("config", "user.email", "fixture@example.invalid", cwd=publisher)
        (publisher / "method.txt").write_text("version 1")
        command("add", ".", cwd=publisher)
        command("commit", "-m", "fixture 1", cwd=publisher)
        command("remote", "add", "origin", str(origin), cwd=publisher)
        command("push", "origin", "main", cwd=publisher)
        command("clone", "-b", "main", str(origin), str(checkout))
        (publisher / "method.txt").write_text("version 2")
        command("commit", "-am", "fixture 2", cwd=publisher)
        command("push", "origin", "main", cwd=publisher)
        automatic = copy.deepcopy(self.settings)
        automatic["gitops"] = {"ref": "main", "update_policy": "fast_forward"}
        with patch("squad.deployment.ROOT", checkout):
            result = deployment_command(Namespace(action="sync"), automatic)
            self.assertTrue(result["changed"])
            self.assertEqual((checkout / "method.txt").read_text(), "version 2")
            command("config", "user.name", "Synthetic fixture", cwd=checkout)
            command("config", "user.email", "fixture@example.invalid", cwd=checkout)
            (checkout / "local.txt").write_text("Preserve local reviewed history")
            command("add", ".", cwd=checkout)
            command("commit", "-m", "local branch change", cwd=checkout)
            local_revision = command("rev-parse", "HEAD", cwd=checkout)
            (publisher / "method.txt").write_text("version 3")
            command("commit", "-am", "fixture 3", cwd=publisher)
            command("push", "origin", "main", cwd=publisher)
            with self.assertRaisesRegex(ValueError, "Git operation failed"):
                deployment_command(Namespace(action="sync"), automatic)
            self.assertEqual(command("rev-parse", "HEAD", cwd=checkout), local_revision)
            self.assertEqual((checkout / "local.txt").read_text(), "Preserve local reviewed history")
