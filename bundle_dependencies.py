"""Prepare pinned official redistributables; never install them on the build PC."""
import hashlib
import json
import stat
import urllib.request
import zipfile
from pathlib import Path


def prepare(base, work):
    lock = json.loads((base / 'runtime-lock.json').read_text(encoding='utf-8'))
    cache = work / 'dependencies'
    cache.mkdir(parents=True, exist_ok=True)
    node = download(lock['node'], cache)
    folder = cache / ('node-' + lock['node']['version'])
    extract_node(node, folder)
    bootstrap = download(lock['webview2'], cache)
    return folder, bootstrap


def download(item, cache):
    if cache.is_symlink() or cache.is_junction():
        raise ValueError('Dependency cache cannot be a link')
    file = cache / item['filename']
    if file.parent != cache or not item['url'].startswith(('https://nodejs.org/dist/', 'https://go.microsoft.com/fwlink/')):
        raise ValueError('Unsupported dependency source')
    if not file.is_file():
        request = urllib.request.Request(item['url'], headers={'User-Agent': 'ChatBrief-release-builder'})
        with urllib.request.urlopen(request, timeout=90) as response:
            data = response.read(80_000_001)
        if len(data) > 80_000_000 or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('Dependency download checksum mismatch')
        file.write_bytes(data)
    if file.is_symlink() or hashlib.sha256(file.read_bytes()).hexdigest() != item['sha256']:
        raise ValueError('Dependency cache checksum mismatch')
    return file


def extract_node(archive, folder):
    folder.mkdir(parents=True, exist_ok=True)
    if folder.is_symlink() or folder.is_junction():
        raise ValueError('Dependency folder cannot be a link')
    with zipfile.ZipFile(archive) as package:
        if sum(entry.file_size for entry in package.infolist()) > 300_000_000:
            raise ValueError('Dependency archive is too large')
        for entry in package.infolist():
            parts = entry.filename.replace('\\', '/').split('/')
            if len(parts) < 2 or not parts[0].startswith('node-') or '..' in parts or stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError('Unsafe dependency archive path')
            relative = '/'.join(parts[1:])
            if not relative or entry.is_dir():
                continue
            target = folder / relative
            if not target.resolve().is_relative_to(folder.resolve()):
                raise ValueError('Dependency archive escapes its folder')
            for parent in (target, *target.parents):
                if parent == folder.parent:
                    break
                if parent.is_symlink() or (parent.exists() and parent.is_junction()):
                    raise ValueError('Dependency path cannot be a link')
            data = package.read(entry)
            if target.exists():
                if target.read_bytes() != data:
                    raise ValueError('Extracted dependency differs from the official archive')
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(data)
    if not (folder / 'node.exe').is_file() or not (folder / 'node_modules/npm/bin/npm-cli.js').is_file():
        raise ValueError('Node runtime is incomplete')
