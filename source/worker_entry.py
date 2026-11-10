"""Console-subsystem helper, launched hidden with explicit inherited JSON pipes."""
import json
import runpy
import sys
import hashlib
from pathlib import Path
from runtime_paths import BUNDLE_ROOT

MODES = {'--reader-worker': 'vendor/reader/worker.py', '--catalog-worker': 'bridge_worker.py'}


def verify_install(folder, expected_version):
    from version import APP_VERSION
    try:
        manifest = json.loads((folder / 'install-manifest.json').read_text(encoding='utf-8'))
        if manifest['version'] != expected_version or APP_VERSION != expected_version or not manifest['files']:
            return False
        for relative, expected_hash in manifest['files'].items():
            file = folder / relative
            if not file.resolve().is_relative_to(folder.resolve()) or not file.is_file():
                return False
            if hashlib.sha256(file.read_bytes()).hexdigest() != expected_hash:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


if __name__ == '__main__':
    # Frozen Python ignores PYTHONIOENCODING; JSON pipes must support chat emoji.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding='utf-8', errors='strict')
    if len(sys.argv) == 3 and sys.argv[1] == '--verify-install':
        folder = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
        valid = verify_install(folder, sys.argv[2])
        print(json.dumps({'installationValid': valid}))
        raise SystemExit(0 if valid else 1)
    if len(sys.argv) != 2 or sys.argv[1] not in MODES:
        print(json.dumps({'error': 'READ_ONLY_OPERATION_BLOCKED'}))
        raise SystemExit(1)
    sys.path.insert(0, str(BUNDLE_ROOT / 'vendor/reader'))
    runpy.run_path(str(BUNDLE_ROOT / MODES[sys.argv[1]]), run_name='__main__')
