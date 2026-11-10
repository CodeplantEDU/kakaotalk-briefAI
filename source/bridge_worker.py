"""Catalog-only extension of the installed read-only worker."""
import sys, json
import importlib.util
from runtime_paths import BUNDLE_ROOT
installed = BUNDLE_ROOT / 'vendor/reader'
sys.path.insert(0, str(installed))
audit_spec = importlib.util.spec_from_file_location('chatbrief_reader_audit', installed / 'worker.py')
audit_module = importlib.util.module_from_spec(audit_spec)
audit_spec.loader.exec_module(audit_module)
sys.addaudithook(audit_module.read_only_audit)
try:
    import backend
    request = json.loads(sys.stdin.buffer.readline(20_001))
    if request.get('op') == 'rooms':
        with backend.Reader(ledger=None) as reader:
            result = {'rooms': [backend.room_json(room) for room in reader.rooms()]}
    elif request.get('op') == 'history':
        target = request.get('target')
        if not isinstance(target, str) or not target.isdecimal() or len(target) > 20:
            raise ValueError('INVALID_TARGET')
        before = request.get('before_id')
        if before is not None and (not isinstance(before, str) or not before.isdecimal() or len(before) > 20):
            raise ValueError('INVALID_CURSOR')
        result = backend.perform({'op': 'read', 'target': target, 'limit': 100, 'before_id': before})
        if not result.get('error'):
            with backend.Reader(ledger=None) as reader:
                raw = reader.messages(int(target), limit=100, before_id=int(before) if before else None)
                identifiers = {str(m.id) for m in raw}
                attachments = reader.attachments(int(target), limit=100, before_id=int(before) if before else None)
                result['_attachments'] = [a.as_json() for a in attachments if str(a.message_id) in identifiers and a.kind in ('photo', 'video', 'file')]
                for message in raw:
                    if message.photo:
                        result['_attachments'] = [a for a in result['_attachments'] if a['messageId'] != str(message.id)]
                        result['_attachments'].extend({'messageId': str(message.id), 'kind': 'photo', 'url': item['url'], 'name': '사진'} for item in message.photo.as_json()['images'])
    else:
        raise ValueError('READ_ONLY_OPERATION_BLOCKED')
except Exception as error:
    allowed = {'INVALID_TARGET', 'INVALID_CURSOR', 'READ_ONLY_OPERATION_BLOCKED'}
    code = str(error) if isinstance(error, ValueError) and str(error) in allowed else type(error).__name__
    result = error.envelope() if hasattr(error, 'envelope') else {'error': code}
if 'backend' in locals():
    update = backend.cache_update()
    if update:
        result['_encrypted_key_cache_update'] = update
print(json.dumps(result, ensure_ascii=False), flush=True)
