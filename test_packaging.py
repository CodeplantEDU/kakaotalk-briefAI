import tempfile
import unittest
from pathlib import Path
from package_source import BASE, source_files, checked_file


class SourceBoundaryTests(unittest.TestCase):
    def test_runtime_json_is_not_packaged(self):
        with tempfile.TemporaryDirectory(dir=BASE) as name:
            root = Path(name)
            (root / 'app.py').write_text('print("synthetic")', encoding='utf-8')
            for path in ('private/state.json', 'ai-workspace/log.json', 'settings.backup.json', '.build-dist/config.json'):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text('dummy-not-a-secret', encoding='utf-8')
            self.assertEqual([p.relative_to(root).as_posix() for p in source_files(root)], ['app.py'])

    def test_escape_rejected(self):
        with self.assertRaises(ValueError):
            checked_file('../outside.py')

    def test_allowed_file_link_rejected(self):
        with tempfile.TemporaryDirectory(dir=BASE) as name:
            root = Path(name)
            real = root / 'original.py'
            real.write_text('dummy', encoding='utf-8')
            try:
                (root / 'app.py').symlink_to(real)
            except OSError:
                self.skipTest('Windows symlink privilege unavailable')
            with self.assertRaises(ValueError):
                list(source_files(root))


if __name__ == '__main__':
    unittest.main()
