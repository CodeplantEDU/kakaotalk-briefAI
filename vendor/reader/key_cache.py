"""DPAPI cache of DB keys validated by successful local SQLite reads."""
import base64
import hashlib
import json
from pathlib import Path
import win32crypt
from pywintypes import error as DPAPIError

BASE=Path(__file__).resolve().parent
from runtime_paths import READER_PRIVATE
CACHE=READER_PRIVATE/'db-keys.dpapi'
MAX_CACHE_BYTES=1_000_000


def profile_id(profile):
    return hashlib.sha256(str(profile.resolve()).casefold().encode('utf-8')).hexdigest()


def relative_name(profile,database):
    resolved=database.resolve()
    if not resolved.is_relative_to(profile.resolve()) or resolved.suffix.lower()!='.edb':
        raise ValueError('INVALID_CACHE_DATABASE')
    return resolved.relative_to(profile.resolve()).as_posix()


def load(profile):
    try:
        if CACHE.stat().st_size>MAX_CACHE_BYTES:
            return {}
        decoded=win32crypt.CryptUnprotectData(CACHE.read_bytes(),None,None,None,0)[1]
        data=json.loads(decoded.decode('utf-8'))
        if data.get('profile')!=profile_id(profile) or data.get('schema')!=1:
            return {}
        entries={}
        for name,item in data['keys'].items():
            database=profile/name
            if relative_name(profile,database)!=name:
                continue
            key=base64.b64decode(item['key'],validate=True)
            salt=base64.b64decode(item['salt'],validate=True)
            if len(key)!=32 or len(salt)!=16:
                continue
            try:
                with database.open('rb') as stream:
                    if stream.read(16)!=salt:
                        continue
            except OSError:
                continue
            entries[name]={'key':item['key'],'salt':item['salt']}
        return entries
    except (OSError,ValueError,KeyError,TypeError,AttributeError,DPAPIError):
        return {}


def keys(entries):
    return {name:base64.b64decode(item['key'],validate=True) for name,item in entries.items()}


def record(profile,entries,database,key):
    name=relative_name(profile,database)
    with database.open('rb') as stream:
        salt=stream.read(16)
    if len(salt)!=16 or len(key)!=32:
        raise ValueError('INVALID_CACHE_KEY')
    entries[name]={'key':base64.b64encode(key).decode('ascii'),
                   'salt':base64.b64encode(salt).decode('ascii')}


def encrypted_update(profile,entries):
    plaintext=json.dumps({'schema':1,'profile':profile_id(profile),'keys':entries},separators=(',',':')).encode('utf-8')
    if len(plaintext)>MAX_CACHE_BYTES//2:
        raise ValueError('KEY_CACHE_LIMIT')
    encrypted=win32crypt.CryptProtectData(plaintext,'Kakao local DB keys',None,None,None,0)
    return base64.b64encode(encrypted).decode('ascii')


def save_encrypted(value):
    encrypted=base64.b64decode(value,validate=True)
    if len(encrypted)>MAX_CACHE_BYTES:
        raise ValueError('KEY_CACHE_LIMIT')
    # The installer creates this directory with current-user + SYSTEM ACLs.
    if not CACHE.parent.is_dir():
        raise RuntimeError('PRIVATE_CACHE_DIRECTORY_MISSING')
    temporary=CACHE.with_suffix('.tmp')
    temporary.write_bytes(encrypted)
    temporary.replace(CACHE)
