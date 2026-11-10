"""Release sources are an explicit allowlist; private files are never discovered."""
import hashlib
import json
import stat
import zipfile
from pathlib import Path
from version import APP_VERSION

BASE = Path(__file__).resolve().parent
ROOT_FILES = {
    '.gitignore', 'README.md', 'RELEASE-NOTES.md', 'THIRD_PARTY_LICENSE.txt', 'THIRD_PARTY_NOTICES.md',
    'app.py', 'app.js', 'index.html', 'style.css', 'providers.py', 'media.py', 'sending.py', 'send_win32.py', 'test_sending.py',
    'bridge_worker.py', 'worker.py', 'runtime_paths.py', 'setup_service.py',
    'desktop.py', 'worker_entry.py', 'version.py', 'summary.schema.json', 'deny-tools.toml',
    'gemini-settings.json', 'requirements.txt', 'requirements-build.txt',
    'requirements-build.lock', 'package_source.py', 'register_catalog.py',
    'build_release.py', 'bundle_dependencies.py', 'runtime-lock.json', 'test_reply_style.py', 'test_bundle_dependencies.py', 'test_app.py', 'test_backend_release.py', 'test_ui_fixture.py',
    'test_ui_browser.mjs', 'test_packaging.py', 'test_desktop_release.py', 'test_installer.ps1',
    '설치.cmd', '설치.ps1', '실행.cmd', '실행.ps1', 'TESTING.md', 'RELEASE-CHECKLIST.md', 'RELEASE-TEST-RESULTS.md',
}
VENDOR_FILES = {
    'LICENSE', 'SOURCE.json', 'backend.py', 'key_cache.py', 'layout32.py', 'runner.py', 'worker.py',
    'kanao/__init__.py', 'kanao/cng.py', 'kanao/context.py', 'kanao/errors.py',
    'kanao/keyring.py', 'kanao/model.py', 'kanao/names.py', 'kanao/page.py',
    'kanao/paths.py', 'kanao/process.py', 'kanao/reader.py', 'kanao/snapshot.py',
    'kakaocommon/__init__.py', 'kakaocommon/disposition.py', 'kakaocommon/wal.py',
}
ASSETS = {'fonts/OFL.txt', 'fonts/PretendardVariable.woff2', 'assets/chatbrief.ico',
          'assets/chatbrief.png', 'assets/chatbrief-bundle.json', 'installer/ChatBrief.nsi'}


def checked_file(relative, root=BASE):
    path = root / relative
    for segment in (path, *path.parents):
        if segment == root.parent:
            break
        if segment.is_symlink() or (segment.exists() and segment.is_junction()):
            raise ValueError('Release path cannot be a link: ' + str(relative))
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError('Release path escapes source root')
    if not path.exists():
        return None
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ValueError('Release file must be a regular single-link file')
    return path


def source_files(root=BASE):
    expected = ROOT_FILES | ASSETS | {'vendor/reader/' + item for item in VENDOR_FILES}
    for relative in sorted(expected):
        path = checked_file(relative, root)
        if path:
            yield path


def build():
    files = list(source_files())
    manifest = {'version': APP_VERSION, 'files': {p.relative_to(BASE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    manifest_path = BASE / 'SOURCE-MANIFEST.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    target = BASE.parent / f'ChatBrief-{APP_VERSION}-source.zip'
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files + [manifest_path]:
            archive.write(path, 'chatbrief/' + path.relative_to(BASE).as_posix())
    print(f'Source bundle: {len(files)} allowlisted files; private/runtime/build files excluded')
    return target


if __name__ == '__main__':
    build()
