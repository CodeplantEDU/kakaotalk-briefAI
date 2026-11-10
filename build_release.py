"""Build local RC artifacts only. This script never uploads a release."""
import hashlib
import importlib.metadata
import json
import shutil
import subprocess
import sys
import io
import urllib.request
import zipfile
from pathlib import Path
from package_source import BASE, VENDOR_FILES, checked_file
from version import APP_VERSION

RELEASE = BASE / 'release'
DIST = BASE / '.build-dist'
WORK = BASE / '.build-work'


def run(command):
    subprocess.run([str(v) for v in command], cwd=BASE, check=True)


def assets():
    from PIL import Image, ImageDraw
    folder = BASE / 'assets'
    folder.mkdir(exist_ok=True)
    font = BASE / 'fonts/PretendardVariable.woff2'
    if not font.is_file():
        request = urllib.request.Request('https://raw.githubusercontent.com/orioncactus/pretendard/v1.3.9/packages/pretendard/dist/web/variable/woff2/PretendardVariable.woff2', headers={'Accept':'application/octet-stream'})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(3_000_000)
        if hashlib.sha256(data).hexdigest() != '9599f12fd42fc0bce1cd50b47a0c022e108d7aa64dd0d1bb0ed44f3282d900b4':
            raise RuntimeError('Pretendard checksum mismatch')
        font.parent.mkdir(exist_ok=True)
        font.write_bytes(data)
    image = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((12, 12, 244, 244), radius=54, fill='#273e64')
    draw.rounded_rectangle((53, 58, 203, 174), radius=23, outline='white', width=10)
    draw.line((77, 171, 77, 205, 113, 173), fill='white', width=10, joint='curve')
    draw.line((85, 99, 172, 99), fill='white', width=10)
    draw.line((85, 132, 145, 132), fill='white', width=10)
    image.save(folder / 'chatbrief.png')
    image.save(folder / 'chatbrief.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
    (folder / 'chatbrief-bundle.json').write_text(json.dumps({'product':'ChatBrief','version':APP_VERSION,'channel':'release-candidate'}), encoding='utf-8')


def licenses():
    target = WORK / 'licenses'
    target.mkdir(parents=True, exist_ok=True)
    dependencies = ['pywin32', 'pywebview', 'pythonnet', 'clr_loader', 'cffi', 'pycparser', 'bottle',
                    'proxy_tools', 'typing_extensions', 'pyinstaller', 'altgraph', 'pefile',
                    'pywin32-ctypes', 'pyinstaller-hooks-contrib', 'packaging', 'pillow', 'setuptools']
    inventory = []
    for name in dependencies:
        distribution = importlib.metadata.distribution(name)
        folder = target / name
        folder.mkdir(exist_ok=True)
        copied = []
        for file in distribution.files or []:
            if not any(token in Path(str(file)).name.lower() for token in ('license', 'copying', 'notice')):
                continue
            source = Path(distribution.locate_file(file))
            if not source.is_file() or source.is_symlink() or source.stat().st_size > 2_000_000:
                continue
            destination = folder / (hashlib.sha256(str(file).encode()).hexdigest()[:8] + '-' + source.name)
            shutil.copyfile(source, destination)
            copied.append(destination.name)
        metadata = {'name': name, 'version': distribution.version,
                    'license': distribution.metadata.get('License-Expression') or distribution.metadata.get('License'),
                    'home': distribution.metadata.get('Home-page'), 'license_files': copied}
        # Some small wheels omit a standalone LICENSE; preserve their original metadata.
        (folder / 'METADATA.txt').write_text(distribution.read_text('METADATA') or '', encoding='utf-8')
        inventory.append(metadata)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.is_file():
        raise RuntimeError('CPython license is required for the release bundle')
    shutil.copyfile(python_license, target / 'CPython-LICENSE.txt')
    extra = WORK / 'extra-licenses'
    extra.mkdir(exist_ok=True)
    sdk_license = extra / 'WebView2-SDK-0-LICENSE.txt'
    if not sdk_license.is_file():
        request = urllib.request.Request('https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/1.0.3856.49/microsoft.web.webview2.1.0.3856.49.nupkg', headers={'Accept':'application/octet-stream'})
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read(30_000_000)
        with zipfile.ZipFile(io.BytesIO(payload)) as package:
            sdk_license.write_bytes(package.read('LICENSE.txt'))
    proxy_license = extra / 'proxy_tools-LICENSE.txt'
    if not proxy_license.is_file():
        with urllib.request.urlopen('https://raw.githubusercontent.com/jtushman/proxy_tools/master/LICENSE.txt', timeout=20) as response:
            proxy_license.write_bytes(response.read(100_000))
    for file in (sdk_license, proxy_license):
        shutil.copyfile(file, target / file.name)
    (target / 'DEPENDENCIES.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding='utf-8')
    return target


def build():
    for path in (DIST, WORK, DIST / 'ChatBrief'):
        if not path.resolve().is_relative_to(BASE.resolve()) or path.is_symlink() or (path.exists() and path.is_junction()):
            raise RuntimeError('Build output must stay inside the project workspace')
    RELEASE.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)
    assets()
    license_dir = licenses()
    from bundle_dependencies import prepare
    node_runtime, webview_installer = prepare(BASE, WORK)
    data_names = ['index.html','app.js','style.css','summary.schema.json','deny-tools.toml','gemini-settings.json',
                  'bridge_worker.py','THIRD_PARTY_LICENSE.txt','THIRD_PARTY_NOTICES.md','README.md','TESTING.md',
                  'fonts/OFL.txt','fonts/PretendardVariable.woff2','assets/chatbrief.ico','assets/chatbrief-bundle.json','runtime-lock.json']
    data_names += ['vendor/reader/' + name for name in VENDOR_FILES]
    data = []
    for name in data_names:
        path = checked_file(name)
        if path is None:
            raise RuntimeError('Missing release asset: ' + name)
        data.append((str(path), Path(name).parent.as_posix()))
    data.append((str(license_dir), 'licenses'))
    data.append((str(node_runtime), 'runtime/node'))
    spec = """from PyInstaller.utils.hooks import collect_submodules
a = Analysis(['desktop.py'], pathex=PATHS, binaries=[], datas=DATA,
 hiddenimports=['backend','key_cache','layout32','runner','win32timezone']+collect_submodules('kanao')+collect_submodules('kakaocommon'),
 hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=['PyQt5','PyQt6','PySide2','PySide6','cefpython3','tkinter'], noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='ChatBrief',debug=False,bootloader_ignore_signals=False,
 strip=False,upx=False,console=False,disable_windowed_traceback=True,icon='assets/chatbrief.ico')
b=Analysis(['worker_entry.py'],pathex=PATHS,binaries=[],datas=[],
 hiddenimports=['backend','key_cache','layout32','runner','win32timezone']+collect_submodules('kanao')+collect_submodules('kakaocommon'),
 hookspath=[],hooksconfig={},runtime_hooks=[],excludes=['webview','PyQt5','PyQt6','PySide2','PySide6','cefpython3','tkinter'],noarchive=False)
worker_pyz=PYZ(b.pure)
worker=EXE(worker_pyz,b.scripts,[],exclude_binaries=True,name='ChatBriefWorker',debug=False,bootloader_ignore_signals=False,
 strip=False,upx=False,console=True)
coll=COLLECT(exe,worker,a.binaries,a.datas,b.binaries,b.datas,strip=False,upx=False,name='ChatBrief')
""".replace('PATHS', repr([str(BASE), str(BASE / 'vendor/reader')])).replace('DATA', repr(data))
    spec_path = BASE / 'ChatBrief.spec'
    spec_path.write_text(spec, encoding='utf-8')
    run([sys.executable,'-m','PyInstaller','--noconfirm','--distpath',DIST,'--workpath',WORK/'pyinstaller',spec_path])
    bundle = DIST / 'ChatBrief'
    shutil.copyfile(BASE / 'assets/chatbrief-bundle.json', bundle / 'chatbrief-bundle.json')
    shutil.copyfile(BASE / 'TESTING.md', bundle / '사용자-테스트-안내.md')
    manifest = {'version': APP_VERSION, 'files': {
        path.relative_to(bundle).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(bundle.rglob('*')) if path.is_file()}}
    (bundle / 'install-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    portable = RELEASE / f'ChatBrief-{APP_VERSION}-windows-x64-portable.zip'
    with zipfile.ZipFile(portable, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle.rglob('*')):
            if path.is_file():
                assert not path.is_symlink() and 'private' not in path.relative_to(bundle).parts
                archive.write(path, 'ChatBrief/' + path.relative_to(bundle).as_posix())
    # Uninstall only files that this build installs; never recursively delete a tree.
    def literal(path):
        return path.replace('$', '$$').replace('"', '$\\"').replace('/', '\\')
    installed_files = [p for p in sorted(bundle.rglob('*')) if p.is_file()]
    installed_dirs = sorted((p for p in bundle.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True)
    guards = []
    for index, path in enumerate(installed_dirs):
        relative = literal(path.relative_to(bundle).as_posix())
        done = f'verify_directory_{index}_done'
        guards += [f'System::Call \'kernel32::GetFileAttributesW(w "$INSTDIR\\{relative}") i .r0\'',
                   f'IntCmp $0 -1 {done}', 'IntOp $0 $0 & 0x400', f'IntCmp $0 0 {done}',
                   'MessageBox MB_OK|MB_ICONSTOP "설치 폴더 안의 연결 경로를 발견해 설치/제거를 중단합니다." /SD IDOK',
                   'Abort', done + ':']
    (WORK / 'uninstall-verify.nsh').write_text('\n'.join(guards) + '\n', encoding='utf-8')
    uninstall = ['Delete "$INSTDIR\\' + literal(p.relative_to(bundle).as_posix()) + '"' for p in installed_files]
    uninstall += ['RMDir "$INSTDIR\\' + literal(p.relative_to(bundle).as_posix()) + '"' for p in installed_dirs]
    (WORK / 'uninstall-files.nsh').write_text('\n'.join(uninstall) + '\n', encoding='utf-8')
    compiler = BASE / '.build-tools/nsis-3.13/Bin/makensis.exe'
    if not compiler.is_file():
        raise RuntimeError('Verified NSIS 3.13 compiler is required')
    run([compiler, '/V2', '/INPUTCHARSET', 'UTF8', f'/DAPP_VERSION={APP_VERSION}', BASE/'installer/ChatBrief.nsi'])
    artifacts = [portable, RELEASE / f'ChatBrief-{APP_VERSION}-windows-x64-setup.exe']
    (RELEASE/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in artifacts), encoding='utf-8')
    print('Local release candidate artifacts created; nothing uploaded.')


if __name__ == '__main__':
    build()
