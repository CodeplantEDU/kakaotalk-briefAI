"""Validate the frozen binary using an empty isolated test profile only."""
import json
import os
import subprocess
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent


def check(binary=None):
    executable = binary or BASE / '.build-dist/ChatBrief/ChatBrief.exe'
    from PyInstaller.archive.readers import CArchiveReader
    archive = CArchiveReader(str(executable))
    pyz = archive.open_embedded_archive(next(name for name in archive.toc if name.endswith('.pyz')))
    assert 'win32timezone' in pyz.toc, 'Pywin32 process-time conversion module is missing'
    from version import APP_VERSION
    verified = subprocess.run([str(executable.with_name('ChatBriefWorker.exe')), '--verify-install', APP_VERSION],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, creationflags=0x08000000)
    assert verified.returncode == 0 and json.loads(verified.stdout)['installationValid'], 'Installed files do not match this release'
    with tempfile.TemporaryDirectory(dir=BASE / '.build-work') as name:
        profile = Path(name) / 'profile'
        env = dict(os.environ, CHATBRIEF_DATA_DIR=str(profile))
        output = []
        for flag in ('--reader-worker', '--catalog-worker'):
            result = subprocess.run([str(executable.with_name('ChatBriefWorker.exe')), flag], input=b'{"op":"invalid-test-operation"}\n',
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=20, creationflags=0x08000000)
            assert result.returncode == 0, (flag, result.returncode, result.stderr[:300])
            body = json.loads(result.stdout.decode('utf-8'))
            assert body.get('error') == 'READ_ONLY_OPERATION_BLOCKED', (flag, body)
            assert '_encrypted_key_cache_update' not in body
            output.append({'mode': flag, 'safeInvalidRequest': True})
        result = subprocess.run([str(executable), '--smoke-test', '--port', '0'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=30, creationflags=0x08000000)
        assert result.returncode == 0, ('HTTP smoke', result.returncode, result.stderr[:300])
        state = json.loads((profile / 'smoke-result.json').read_text(encoding='utf-8'))
        assert state['http'] and state['freshProfile'] and state['frozen']
        assert not (profile / 'reader-private/db-keys.dpapi').exists()
        output.append(state)
        ui = subprocess.run([str(executable), '--ui-smoke-test', '--port', '0'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=40, creationflags=0x08000000)
        assert ui.returncode == 0, ('Native window smoke', ui.returncode, ui.stderr[:300])
        loaded = json.loads((profile / 'ui-smoke-result.json').read_text(encoding='utf-8'))
        assert loaded['nativeWindow'] and not loaded['realChatRead']
        output.append(loaded)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return output


if __name__ == '__main__':
    check()
