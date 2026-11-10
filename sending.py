"""Explicit preview/confirm sending; tokens are single-use and never persisted.

Gate file protocol follows nichirin/kanao sendgate.py at commit
6e7838c86064f88695d8b0b24b16b2c6a7a55b1e (MIT notices retained).
"""
import hashlib
import json
import os
import secrets
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import msvcrt
from send_win32 import Win32SendBackend, SendValidationError

MAX_TEXT = 2000
TTL_SECONDS = 60
TOKENS = {}
RECENT = {}
LOCK = threading.Lock()
SEND_LOCK = threading.Lock()


def resolve_room(room_id, read_catalog):
    if not isinstance(room_id, str) or not room_id.isdecimal() or len(room_id) > 20:
        raise SendValidationError('전송할 채팅방을 선택해 주세요.')
    catalog = read_catalog()
    if catalog.get('error'):
        raise SendValidationError('현재 채팅방 목록을 확인하지 못했습니다. 새로고침 후 다시 전송을 눌러 주세요.')
    rooms = catalog.get('rooms', [])
    chosen = [room for room in rooms if room.get('id') == room_id]
    if len(chosen) != 1 or not isinstance(chosen[0].get('title'), str) or not chosen[0]['title']:
        raise SendValidationError('전송할 채팅방을 현재 목록에서 확인하지 못했습니다.')
    title = chosen[0]['title']
    if len([room for room in rooms if (room.get('title') or '').casefold() == title.casefold()]) != 1:
        raise SendValidationError('같은 제목의 채팅방이 여러 개 있어 잘못 보낼 수 있으므로 차단했습니다. 카카오톡에서 방 제목을 구분해 주세요.')
    return {'id': room_id, 'title': title}


def preview(room_id, text, read_catalog, backend=None):
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT or '\x00' in text:
        raise SendValidationError('답장 본문은 비어 있지 않은 2,000자 이하의 텍스트여야 합니다.')
    try:
        text.encode('utf-8')
    except UnicodeError:
        raise SendValidationError('지원하지 않는 문자가 포함돼 있습니다.') from None
    room = resolve_room(room_id, read_catalog)
    backend = backend or Win32SendBackend()
    snapshot = backend.snapshot(room['title'])
    if resolve_room(room_id, read_catalog) != room:
        raise SendValidationError('현재 계정이나 채팅방이 바뀌었습니다. 다시 전송을 눌러 주세요.')
    backend.validate(snapshot)
    instant = time.monotonic()
    fingerprint = hashlib.sha256((room_id+'\0'+text).encode('utf-8')).hexdigest()
    with LOCK:
        for key in list(TOKENS):
            if TOKENS[key]['until'] <= instant:
                del TOKENS[key]
        for key in list(RECENT):
            if RECENT[key] <= instant:
                del RECENT[key]
        if RECENT.get(fingerprint, 0) > instant:
            raise SendValidationError('같은 내용의 전송을 최근에 시도했습니다. 카카오톡 대화에서 결과를 먼저 확인해 주세요.')
        if len(TOKENS) >= 64:
            raise SendValidationError('전송 준비 요청이 너무 많습니다. 잠시 후 다시 확인해 주세요.')
        token = secrets.token_urlsafe(32)
        TOKENS[token] = {'room': room, 'text': text, 'snapshot': snapshot,
                         'until': instant + TTL_SECONDS, 'fingerprint': fingerprint}
    return {'token': token, 'roomId': room_id, 'title': room['title'], 'text': text,
            'requiresHintReplacement': snapshot.get('initialText') == '메시지 입력',
            'expiresAt': (datetime.now(timezone(timedelta(hours=9))) + timedelta(seconds=TTL_SECONDS)).isoformat(timespec='seconds')}


@contextmanager
def send_gate(directory=None):
    # Match the original kanao gate so this app cannot type beside its CLI/serve.
    folder = directory or Path(os.environ.get('LOCALAPPDATA', Path.home()/'AppData/Local'))/'kanao-cli'
    folder.mkdir(parents=True, exist_ok=True)
    with (folder/'send.lock').open('a+b') as guard:
        guard.seek(0)
        try:
            msvcrt.locking(guard.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise SendValidationError('다른 전송 작업이 진행 중입니다. 대기하거나 자동 재시도하지 않았습니다.') from None
        try:
            record = folder/'send-pacing.json'
            previous = None
            if record.exists():
                try:
                    previous = json.loads(record.read_text(encoding='utf-8')).get('startedAt')
                    if type(previous) not in (int, float):
                        raise ValueError()
                except (OSError, ValueError, AttributeError):
                    raise SendValidationError('기존 전송 상태를 확인하지 못해 전송을 차단했습니다.') from None
            if previous is not None and min(previous + 2 - time.time(), 2) > 0:
                raise SendValidationError('최근 전송이 진행됐습니다. 잠시 후 대화에서 결과를 확인해 주세요.')
            temporary = record.with_suffix('.tmp')
            temporary.write_text(json.dumps({'startedAt': time.time()}), encoding='utf-8')
            os.replace(temporary, record)
            yield
        finally:
            guard.seek(0)
            msvcrt.locking(guard.fileno(), msvcrt.LK_UNLCK, 1)


def confirm(token, read_catalog, backend=None, gate=None, replace_hint=False):
    with LOCK:
        record = TOKENS.pop(token, None) if isinstance(token, str) else None
    if record is None or record['until'] <= time.monotonic():
        return {'submitted': False, 'delivery': 'not_delivered', 'message': '전송 준비 정보가 만료됐거나 이미 사용됐습니다. 새로 확인해 주세요.'}
    if record['snapshot'].get('initialText') == '메시지 입력' and replace_hint is not True:
        return {'submitted': False, 'delivery': 'not_delivered', 'message': '입력란의 ‘메시지 입력’ 문구 대체에 동의하지 않아 전송하지 않았습니다. 다시 전송을 눌러 주세요.'}
    if not SEND_LOCK.acquire(blocking=False):
        return {'submitted': False, 'delivery': 'not_delivered', 'message': '다른 전송이 진행 중입니다. 이 전송 준비 정보는 다시 사용하지 않습니다.'}
    try:
        with (gate or send_gate)():
            backend = backend or Win32SendBackend()
            backend.validate(record['snapshot'])
            room = resolve_room(record['room']['id'], read_catalog)
            if room != record['room']:
                raise SendValidationError('채팅방 제목이나 대상이 바뀌었습니다. 다시 전송을 눌러 주세요.')
            if RECENT.get(record['fingerprint'], 0) > time.monotonic():
                raise SendValidationError('같은 내용의 전송을 최근에 시도했습니다. 카카오톡에서 결과를 확인해 주세요.')
            if record['until'] <= time.monotonic():
                raise SendValidationError('대상 확인 중 전송 준비 정보가 만료됐습니다. 새로 확인해 주세요.')
            with LOCK:
                RECENT[record['fingerprint']] = time.monotonic() + 180
            try:
                result = backend.submit(record['snapshot'], record['text'], replace_hint=replace_hint)
            except Exception:
                return {'submitted': False, 'delivery': 'unknown', 'message': '전송 상태를 확인하지 못했습니다. 같은 내용을 자동으로 다시 보내지 않습니다. 카카오톡 대화를 확인해 주세요.'}
            if result['delivery'] == 'not_delivered':
                with LOCK:
                    RECENT.pop(record['fingerprint'], None)
            return result
    except SendValidationError as error:
        return {'submitted': False, 'delivery': 'not_delivered', 'message': str(error)}
    except Exception:
        return {'submitted': False, 'delivery': 'unknown', 'message': '전송 상태를 확인하지 못했습니다. 자동 재시도하지 않습니다. 카카오톡 대화를 확인해 주세요.'}
    finally:
        SEND_LOCK.release()
