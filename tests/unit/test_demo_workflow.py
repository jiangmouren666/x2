"""Workflow failure and provenance contracts, without hardware or real images."""
import base64
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('demo_workflow', ROOT/'scripts/demo_workflow.py')
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


class WorkflowTests(unittest.TestCase):
    def run_images(self, cameras):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'capture.txt'
            # Synthetic marker bytes test extraction only, not JPEG decoding.
            source.write_text('HAND_REVIEW='+json.dumps(dict(
                provenance={'kind': 'synthetic_test'}, jpeg_base64=cameras))+'\n')
            argv = ['demo_workflow.py', '--output-root', str(root), 'images', '--capture', str(source)]
            with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = workflow.main()
            out = next(root.glob('demo-images-*'))
            return code, json.loads((out/'workflow.json').read_text()), (out/'head.jpg').read_bytes()

    def test_extraction_preserves_bytes_and_provenance(self):
        raw = b'\xff\xd8synthetic-marker\xff\xd9'
        value = base64.b64encode(raw).decode()
        code, report, image = self.run_images({'head': value, 'wrist': value})
        self.assertEqual((code, report['status'], image), (0, 'PASS', raw))
        self.assertEqual(report['source_provenance']['kind'], 'synthetic_test')
        self.assertEqual(len(report['source_sha256']), 64)
        self.assertIn('finished_at', report)

    def test_missing_camera_fails_and_retains_partial_output(self):
        value = base64.b64encode(b'\xff\xd8synthetic-marker').decode()
        code, report, _ = self.run_images({'head': value})
        self.assertEqual((code, report['status']), (1, 'FAIL'))
        self.assertIn('Missing cameras: wrist', report['error'])

    def test_interruption_is_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            argv = ['demo_workflow.py', '--output-root', directory, 'offline']
            with patch.object(sys, 'argv', argv), patch.object(workflow, 'step', side_effect=KeyboardInterrupt), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(workflow.main(), 130)
            report = json.loads(next(Path(directory).glob('demo-offline-*/workflow.json')).read_text())
            self.assertEqual(report['status'], 'INTERRUPTED')


if __name__ == '__main__':
    unittest.main()
