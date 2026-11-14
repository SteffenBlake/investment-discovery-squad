import importlib.util
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('plugin_bundle', ROOT / '.agents/skills/squad-reconcile/scripts/bundle.py')
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


class BundleTests(unittest.TestCase):
    def test_release_versions_match_packaged_runtime_and_preserve_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plugin = root / 'plugin'
            shutil.copytree(bundle.PLUGIN, plugin, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            shutil.copyfile(ROOT / 'LICENSE', root / 'LICENSE')
            original = (plugin / 'plugin.json').read_bytes()
            source_version = json.loads(original)['version']
            with patch.object(bundle, 'ROOT', root), patch.object(bundle, 'PLUGIN', plugin):
                for tag, expected in ((None, source_version), ('1.2.3', '1.2.3'), ('v2.0.0-rc.1', '2.0.0-rc.1')):
                    with self.subTest(tag=tag):
                        result = bundle.archive(tag)
                        extracted = root / 'installed'
                        with zipfile.ZipFile(result['archive']) as archive:
                            self.assertEqual(json.loads(archive.read('plugin.json'))['version'], expected)
                            archive.extractall(extracted)
                        runtime = extracted / 'skills/squad-onboard/scripts/investment_engine/__init__.py'
                        namespace = {'__file__': str(runtime)}
                        exec(compile(runtime.read_text(), str(runtime), 'exec'), namespace)
                        self.assertEqual(namespace['__version__'], expected)
                        self.assertEqual((plugin / 'plugin.json').read_bytes(), original)
