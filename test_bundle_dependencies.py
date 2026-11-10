import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from bundle_dependencies import download, extract_node


class DependencyBundleTests(unittest.TestCase):
    def test_extracted_runtime_is_verified_and_rejects_modified_files(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as name:
            root = Path(name)
            archive = root / 'node.zip'
            with zipfile.ZipFile(archive, 'w') as package:
                package.writestr('node-fixture/node.exe', b'fake-runtime')
                package.writestr('node-fixture/node_modules/npm/bin/npm-cli.js', b'fake-npm')
            folder = root / 'unpacked'
            extract_node(archive, folder)
            extract_node(archive, folder)
            (folder / 'node.exe').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                extract_node(archive, folder)

    def test_archive_cannot_escape_runtime_folder(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as name:
            root = Path(name)
            archive = root / 'bad.zip'
            with zipfile.ZipFile(archive, 'w') as package:
                package.writestr('node-fixture/../../escaped.txt', b'bad')
            with self.assertRaises(ValueError):
                extract_node(archive, root / 'unpacked')
            self.assertFalse((root / 'escaped.txt').exists())

    def test_wrong_download_cache_hash_is_rejected_without_network(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as name:
            root = Path(name)
            (root / 'node.zip').write_bytes(b'bad')
            item = {'filename': 'node.zip', 'url': 'https://nodejs.org/dist/fixture.zip',
                    'sha256': hashlib.sha256(b'expected').hexdigest()}
            with self.assertRaises(ValueError):
                download(item, root)


if __name__ == '__main__':
    unittest.main()
