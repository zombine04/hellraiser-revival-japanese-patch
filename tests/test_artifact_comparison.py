import hashlib
from pathlib import Path
import tempfile
import unittest

from scripts.compare_artifacts import compare


class ArtifactComparisonTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folders = [Path(temporary.name)/name for name in ('windows','linux')]
        for folder in self.folders:
            folder.mkdir()
            self.prepare(folder, b'self-authored package')

    def prepare(self, folder, payload):
        package = folder/'Hellraiser_Revival_Japanese_v1.0.0.zip'
        package.write_bytes(payload)
        package.with_suffix('.sha256').write_text(f'{hashlib.sha256(payload).hexdigest()}  {package.name}\n', encoding='ascii')

    def test_matching_artifacts(self):
        self.assertEqual(compare(self.folders, '1.0.0'), hashlib.sha256(b'self-authored package').hexdigest())

    def test_different_but_individually_valid_artifacts_fail(self):
        self.prepare(self.folders[1], b'another self-authored package')
        with self.assertRaises(ValueError):
            compare(self.folders, '1.0.0')

    def test_missing_or_corrupt_checksum_fails(self):
        package = self.folders[1]/'Hellraiser_Revival_Japanese_v1.0.0.zip'
        package.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            compare(self.folders, '1.0.0')
        with self.assertRaises(ValueError):
            compare(self.folders, '2.0.0')
