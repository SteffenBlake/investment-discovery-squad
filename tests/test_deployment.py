import copy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from investment_engine.configuration import build_runtime_settings
from investment_engine.deployment import deployment_command
from tests.fixtures import completed_installation


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = build_runtime_settings(completed_installation(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_unsupported_update_policy_cannot_run_git_operations(self):
        from argparse import Namespace
        with patch("investment_engine.deployment.git") as git:
            unsupported = copy.deepcopy(self.settings)
            unsupported["gitops"]["update_policy"] = "manual"
            with self.assertRaisesRegex(ValueError, "fast-forward"):
                deployment_command(Namespace(action="sync"), unsupported)
            git.assert_not_called()

    def test_dirty_checkout_and_unapproved_ref_stop_before_fetch(self):
        from argparse import Namespace
        for dirty, ref in ((" M edited.py", "main"), ("", "../other"), ("", "--all")):
            with self.subTest(dirty=dirty, ref=ref), patch("investment_engine.deployment.git", return_value=dirty) as git:
                self.settings["gitops"]["ref"] = ref
                with self.assertRaises(ValueError):
                    deployment_command(Namespace(action="sync"), self.settings)
                git.assert_called_once_with("status", "--porcelain", "--untracked-files=normal")

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
        with patch("investment_engine.deployment.ROOT", checkout):
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
