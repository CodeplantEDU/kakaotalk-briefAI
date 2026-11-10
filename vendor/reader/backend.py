"""Read-only adaptation with DPAPI-protected validated DB-key caching."""
import os
import sqlite3
from pathlib import Path
import win32api
import win32security
import win32process
import key_cache

from kanao import process, keyring, snapshot, paths
from kanao.reader import Reader
from kanao.errors import KanaoError


def owned_pid():
    pid=process.find_pid()
    if pid is None:
        return None
    handle=win32api.OpenProcess(0x0410,False,pid)
    try:
        if os.path.basename(win32process.GetModuleFileNameEx(handle,0)).lower()!='kakaotalk.exe':
            raise RuntimeError('PROCESS_IDENTITY_MISMATCH')
        token=win32security.OpenProcessToken(handle,win32security.TOKEN_QUERY)
        current=win32security.OpenProcessToken(win32api.GetCurrentProcess(),win32security.TOKEN_QUERY)
        try:
            if win32security.GetTokenInformation(token,win32security.TokenUser)[0]!=win32security.GetTokenInformation(current,win32security.TokenUser)[0]:
                raise RuntimeError('PROCESS_OWNER_MISMATCH')
        finally:
            token.Close()
            current.Close()
    finally:
        handle.Close()
    return pid


def memory_connection(image):
    connection=sqlite3.connect(':memory:',check_same_thread=False)
    try:
        if not hasattr(connection,'deserialize'):
            raise RuntimeError('SQLITE_DESERIALIZE_REQUIRED')
        connection.deserialize(image)
        connection.execute('PRAGMA query_only = ON')
        return connection
    except BaseException:
        connection.close()
        raise


def reading_pid():
    pid=owned_pid()
    if pid is None:
        return None
    handle=win32api.OpenProcess(0x0410,False,pid)
    try:
        is_32bit=win32process.IsWow64Process(handle)
    finally:
        handle.Close()
    if is_32bit:
        from layout32 import resolve32
        salts=set()
        for database in paths.database_paths(paths.user_directory()):
            try:
                with database.open('rb') as stream:
                    salt=stream.read(16)
                if len(salt)==16:
                    salts.add(salt)
            except OSError:
                continue
        process.resolve_context=lambda address,blob,read:resolve32(address,blob,read,salts)
    return pid


# No address cache, nickname ledger, plaintext fallback or automatic room opening.
keyring.find_pid=reading_pid
keyring._remembered=lambda _pid:([],0)
keyring._remember=lambda *_args:None
snapshot._connect=memory_connection
_live_discover=keyring.Keyring.discover.__func__
_original_connect=snapshot.SnapshotCache.connect
_cache_profile=None
_cache_entries={}
_cache_changed=False
_live_key_scans=0
_scan_process=keyring.scan_process


def counted_scan(pid):
    global _live_key_scans
    _live_key_scans+=1
    return _scan_process(pid)


keyring.scan_process=counted_scan


def cached_discover(cls,user_directory,rescan=False):
    global _cache_profile,_cache_entries
    _cache_profile=user_directory
    if not _cache_entries:
        _cache_entries=key_cache.load(user_directory)
    remembered=key_cache.keys(_cache_entries)
    if remembered and not rescan:
        return cls(user_directory=user_directory,pid=owned_pid(),keys=remembered,remembered=True)
    live=_live_discover(cls,user_directory,rescan=True)
    return cls(user_directory=user_directory,pid=live.pid,keys={**remembered,**live.keys})


def validated_connect(cache,database,key,*args,**kwargs):
    global _cache_changed
    try:
        connection=_original_connect(cache,database,key,*args,**kwargs)
    except (KanaoError,sqlite3.DatabaseError) as error:
        if (isinstance(error,KanaoError) and error.code.value!='READ_FAILED') or _cache_profile is None:
            raise
        name=key_cache.relative_name(_cache_profile,database)
        if name not in _cache_entries:
            raise
        # A rotated key may retain the same salt. Re-scan once, then require validation.
        del _cache_entries[name]
        _cache_changed=True
        live=_live_discover(keyring.Keyring,_cache_profile,rescan=True)
        key=live.key_for(name)
        connection=_original_connect(cache,database,key,*args,**kwargs)
    if _cache_profile is not None:
        key_cache.record(_cache_profile,_cache_entries,database,key)
        _cache_changed=True
    return connection


keyring.Keyring.discover=classmethod(cached_discover)
snapshot.SnapshotCache.connect=validated_connect


def cache_update():
    return key_cache.encrypted_update(_cache_profile,_cache_entries) if _cache_changed and _cache_profile is not None else None


def room_json(room):
    data=room.as_json()
    return {key:value for key,value in data.items() if key not in ('images','image','picture')}


def perform(request,reader_factory=Reader):
    operation=request.get('op')
    if operation=='status':
        return {'running':owned_pid() is not None,'mode':'local-memory-and-DB-read-only',
                'network':False,'window_or_clipboard':False,'new_login':False,
                'plaintext_files':False,'encrypted_key_cache':key_cache.CACHE.is_file(),
                'sqlite_deserialize':hasattr(sqlite3.Connection,'deserialize')}
    if operation not in ('find','read'):
        raise ValueError('READ_ONLY_OPERATION_BLOCKED')
    if operation=='find':
        query=request.get('query')
        if not isinstance(query,str) or not query.strip() or len(query)>100:
            raise ValueError('INVALID_QUERY')
    else:
        target=request.get('target')
        limit=request.get('limit',100)
        before=request.get('before_id')
        if not isinstance(target,str) or not target.strip() or len(target)>300:
            raise ValueError('INVALID_TARGET')
        if type(limit) is not int or not 1<=limit<=500:
            raise ValueError('INVALID_LIMIT')
        if before is not None and (not isinstance(before,str) or not before.isdecimal() or len(before)>20):
            raise ValueError('INVALID_CURSOR')
    with reader_factory(ledger=None) as reader:
        if operation=='find':
            return {'rooms':[room_json(room) for room in reader.resolve(query.strip())]}
        matches=([reader.room(int(target))] if target.isdecimal() else reader.resolve(target.strip()))
        matches=[room for room in matches if room is not None]
        if len(matches)!=1:
            return {'error':'CHAT_NOT_FOUND' if not matches else 'AMBIGUOUS_CHAT',
                    'candidates':[room_json(room) for room in matches]}
        room=matches[0]
        if not room.readable:
            try:
                reader._key_for(paths.chat_log_name(room.id))
            except KanaoError:
                return {'error':'KEY_UNAVAILABLE','room':room_json(room),
                        'detail':'No valid cached or live key for this room. Open it once; no automatic opening was attempted.'}
        window=reader.messages(room.id,limit=limit+1,before_id=int(before) if before else None)
        has_earlier=len(window)>limit
        messages=window[-limit:]
        safe_keys={'id','roomId','senderId','sender','text','kind','sentAt','fromMe','replyTo','mentions','mentionsMe','mentionsAll','repliesToMe','edited','covered'}
        newest=max((message.id for message in messages),default=None)
        return {'room':{**room_json(room),'readable':True},
                'messages':[{key:value for key,value in message.as_json().items() if key in safe_keys} for message in messages],
                'next_before_id':str(messages[0].id) if has_earlier and messages else None,
                'coverage':{'localOnly':True,'hasEarlier':has_earlier,
                    'liveKeyScans':_live_key_scans,
                    'reachesLatestKnown':newest is not None and room.last_log_id is not None and newest>=room.last_log_id,
                    'storedLocally':reader.count_messages(room.id)}}
