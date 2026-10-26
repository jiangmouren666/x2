"""Missing, altered and escaping assets must fail the offline gate."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
from offline_check import assets_check, snapshot


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='x2 path with spaces ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'assets').mkdir()
        self.fixture = self.root/'fixture.json'
        self.fixture.write_text('{}')
        self.entry = dict(name='fixture', path='fixture.json', required_for_offline=True,
                          sha256=hashlib.sha256(b'{}').hexdigest())

    def check(self):
        (self.root/'assets/manifest.json').write_text(json.dumps(dict(schema_version=1,assets=[self.entry])))
        return assets_check(self.root)[0]['status']

    def test_missing_and_changed_fixture_fail(self):
        self.assertEqual(self.check(),'PASS')
        self.fixture.write_text('{"changed": true}')
        self.assertEqual(self.check(),'FAIL')
        self.fixture.unlink()
        self.assertEqual(self.check(),'FAIL')

    def test_unknown_hash_cannot_pass(self):
        self.entry['sha256'] = None
        self.assertEqual(self.check(),'FAIL')

    def test_manifest_cannot_escape_root(self):
        self.entry['path'] = '../outside'
        with self.assertRaises(ValueError): self.check()

    def test_missing_declared_source_fails(self):
        (self.root/'config').mkdir()
        (self.root/'config/baseline-files.json').write_text('{"files":["missing.py"]}')
        with self.assertRaises(FileNotFoundError): snapshot(self.root)
