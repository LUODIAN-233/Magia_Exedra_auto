import hashlib
import json
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from src.update import update_check


def _minimal_amd64_pe():
    header = bytearray(64)
    header[:2] = b'MZ'
    struct.pack_into('<I', header, 0x3C, 64)
    return bytes(header) + b'PE\0\0' + struct.pack('<H', 0x8664)


class VersionAndAssetTests(unittest.TestCase):
    def test_semver_release_sorts_after_prerelease(self):
        self.assertGreater(update_check.parse_version('v2.4.0'),
                           update_check.parse_version('2.4.0-beta.2'))

    def test_asset_requires_unique_uploaded_github_zip_with_digest(self):
        digest = hashlib.sha256(b'zip').hexdigest()
        release = {
            'assets': [{
                'name': 'MagiaExedra_auto_v2.4.0_win64.zip',
                'size': 3,
                'state': 'uploaded',
                'browser_download_url': (
                    'https://github.com/LUODIAN-233/Magia_Exedra_auto/'
                    'releases/download/v2.4.0/MagiaExedra_auto_v2.4.0_win64.zip'
                ),
                'digest': f'sha256:{digest}',
            }],
        }
        asset = update_check.find_asset(release, 'v2.4.0')
        self.assertEqual(asset['sha256'], digest)


class ExtractionTests(unittest.TestCase):
    def test_extract_update_builds_manifest_for_amd64_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / 'update.zip'
            with zipfile.ZipFile(archive, 'w') as zip_file:
                zip_file.writestr('Magia_Exedra_auto.exe', _minimal_amd64_pe())
                zip_file.writestr('resource/main.ico', b'icon')
            staging = root / 'staging'
            release_root = Path(update_check.extract_update(
                str(archive), str(staging), 'v2.4.0'
            ))
            manifest = json.loads(
                (release_root / update_check.UPDATE_MANIFEST).read_text(encoding='utf-8')
            )
            self.assertEqual(manifest['version'], '2.4.0')
            self.assertIn('Magia_Exedra_auto.exe', manifest['files'])

    def test_extract_update_rejects_parent_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / 'unsafe.zip'
            with zipfile.ZipFile(archive, 'w') as zip_file:
                zip_file.writestr('../outside.txt', b'bad')
            staging = root / 'staging'
            with self.assertRaises(ValueError):
                update_check.extract_update(str(archive), str(staging), 'v2.4.0')
            self.assertFalse(staging.exists())


if __name__ == '__main__':
    unittest.main()
