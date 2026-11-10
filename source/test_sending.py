"""Synthetic send guard tests. No real window, process, account or message is touched."""
import ctypes
import io
import json
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch
import app
import sending
import send_win32
from send_win32 import Win32SendBackend, SendValidationError


CATALOG = {'rooms': [{'id': '1', 'title': 'Fixture room'}]}


class FakeBackend:
    def __init__(self, initial='', result='submitted'):
        self.initial = initial
        self.result = result
        self.calls = []
        self.changed = False

    def snapshot(self, title):
        if self.initial not in ('', '메시지 입력'):
            raise SendValidationError('existing draft')
        return {'pid': 123, 'created': 'fixture', 'window': 456, 'control': 789,
                'title': title, 'initialText': self.initial}

    def validate(self, expected):
        if self.changed:
            raise SendValidationError('window changed')

    def submit(self, expected, text, replace_hint=False):
        self.calls.append((expected, text, replace_hint))
        if self.result == 'raise':
            raise RuntimeError('synthetic failure after unknown effect')
        return {'submitted': self.result == 'submitted', 'delivery': self.result, 'message': 'fixture'}


class MemoryInput(Win32SendBackend):
    def __init__(self, text='', fail_enter=False, mutate_after_write=False):
        self.current = text
        self.fail_enter = fail_enter
        self.mutate_after_write = mutate_after_write
        self.selection = (0, 0)
        self.writes = []
        self.posts = []
        self.user = self

    def snapshot(self, title, allow_hint=True):
        initial = self.empty(789, allow_hint)
        return {'pid': 123, 'created': 'fixture', 'window': 456, 'control': 789,
                'title': title, 'initialText': initial}

    def validate(self, expected):
        pass

    def text(self, _control):
        return self.current

    def _message(self, _control, code, wp=0, lp=0):
        if code == 0x00B1:
            self.selection = (wp, lp)
        elif code == 0x00B0:
            return self.selection[0] | self.selection[1] << 16
        elif code == 0x00C2:
            value = ctypes.wstring_at(lp)
            self.writes.append(value)
            start, end = self.selection
            self.current = self.current[:start] + value + self.current[end:]
            if self.mutate_after_write:
                self.current += 'concurrent edit'
        return 1

    def PostMessageW(self, _control, code, _wp, _lp):
        self.posts.append(code)
        if self.fail_enter:
            return False
        if code == 0x0101:
            self.current = ''
        return True


class SendingTests(unittest.TestCase):
    def setUp(self):
        sending.TOKENS.clear()
        sending.RECENT.clear()
        self.read = lambda: CATALOG
        self.backend = FakeBackend()

    def preview(self, text='fixture reply', backend=None):
        return sending.preview('1', text, self.read, backend or self.backend)

    def confirm(self, token, backend=None, **kwargs):
        return sending.confirm(token, self.read, backend or self.backend, gate=nullcontext, **kwargs)

    def test_preview_freezes_target_text_and_requires_one_time_token(self):
        preview = self.preview()
        self.assertEqual(preview['roomId'], '1')
        self.assertEqual(preview['text'], 'fixture reply')
        self.assertFalse(preview['requiresHintReplacement'])
        self.assertEqual(self.confirm(preview['token'])['delivery'], 'submitted')
        self.assertEqual(self.confirm(preview['token'])['delivery'], 'not_delivered')
        self.assertEqual(len(self.backend.calls), 1)

    def test_preview_expiration_prevents_backend_submit(self):
        preview = self.preview()
        sending.TOKENS[preview['token']]['until'] = 0
        self.assertEqual(self.confirm(preview['token'])['delivery'], 'not_delivered')
        self.assertFalse(self.backend.calls)

    def test_catalog_missing_id_or_duplicate_title_is_blocked(self):
        for catalog in ({'rooms': []}, {'rooms': CATALOG['rooms'] + [{'id': '2', 'title': 'fixture ROOM'}]}):
            with self.assertRaises(SendValidationError):
                sending.preview('1', 'fixture', lambda: catalog, self.backend)

    def test_account_or_catalog_change_after_preview_is_blocked(self):
        preview = self.preview()
        result = sending.confirm(preview['token'], lambda: {'rooms': []}, self.backend, gate=nullcontext)
        self.assertEqual(result['delivery'], 'not_delivered')
        self.assertFalse(self.backend.calls)

    def test_window_change_after_preview_is_blocked(self):
        preview = self.preview()
        self.backend.changed = True
        self.assertEqual(self.confirm(preview['token'])['delivery'], 'not_delivered')
        self.assertFalse(self.backend.calls)

    def test_inflight_token_cannot_replay_same_content(self):
        first, second = self.preview(), self.preview()
        self.assertEqual(self.confirm(first['token'])['delivery'], 'submitted')
        self.assertEqual(self.confirm(second['token'])['delivery'], 'not_delivered')
        self.assertEqual(len(self.backend.calls), 1)
        with self.assertRaises(SendValidationError):
            self.preview()

    def test_unknown_outcome_or_exception_prevents_new_identical_preview(self):
        for outcome in ('unknown', 'raise'):
            sending.TOKENS.clear()
            sending.RECENT.clear()
            backend = FakeBackend(result=outcome)
            preview = self.preview(backend=backend)
            self.assertEqual(self.confirm(preview['token'], backend)['delivery'], 'unknown')
            with self.assertRaises(SendValidationError):
                self.preview(backend=backend)

    def test_explicit_not_delivered_allows_new_preview_after_fix(self):
        backend = FakeBackend(result='not_delivered')
        preview = self.preview(backend=backend)
        self.assertEqual(self.confirm(preview['token'], backend)['delivery'], 'not_delivered')
        self.assertIn('token', self.preview(backend=backend))

    def test_hint_requires_explicit_boolean_consent(self):
        backend = FakeBackend(initial='메시지 입력')
        preview = self.preview(backend=backend)
        self.assertTrue(preview['requiresHintReplacement'])
        self.assertEqual(self.confirm(preview['token'], backend)['delivery'], 'not_delivered')
        self.assertFalse(backend.calls)
        preview = self.preview(backend=backend)
        self.assertEqual(self.confirm(preview['token'], backend, replace_hint=True)['delivery'], 'submitted')
        self.assertTrue(backend.calls[0][2])

    def test_other_existing_drafts_are_never_overwritten(self):
        backend = MemoryInput('unfinished draft')
        result = backend.submit({'title': 'Fixture room'}, 'new text', replace_hint=True)
        self.assertEqual(result['delivery'], 'not_delivered')
        self.assertEqual(backend.current, 'unfinished draft')
        self.assertFalse(backend.writes)
        self.assertFalse(backend.posts)

    def test_empty_input_inserts_without_selecting_existing_text(self):
        backend = MemoryInput()
        snapshot = backend.snapshot('Fixture room')
        result = backend.submit(snapshot, 'new text')
        self.assertEqual(result['delivery'], 'submitted')
        self.assertEqual(backend.selection, (0, 0))
        self.assertEqual(backend.posts, [0x0100, 0x0101])

    def test_only_exact_previewed_hint_is_replaced_after_consent(self):
        backend = MemoryInput('메시지 입력')
        snapshot = backend.snapshot('Fixture room')
        result = backend.submit(snapshot, 'new text', replace_hint=True)
        self.assertEqual(result['delivery'], 'submitted')
        self.assertEqual(backend.selection, (0, len('메시지 입력')))
        backend = MemoryInput('changed draft')
        result = backend.submit(snapshot, 'new text', replace_hint=True)
        self.assertEqual(result['delivery'], 'not_delivered')
        self.assertFalse(backend.writes)

    def test_changed_body_does_not_post_enter(self):
        backend = MemoryInput(mutate_after_write=True)
        result = backend.submit(backend.snapshot('Fixture room'), 'new text')
        self.assertEqual(result['delivery'], 'not_delivered')
        self.assertFalse(backend.posts)
        self.assertIn('concurrent edit', backend.current)

    def test_enter_queue_failure_is_unknown_without_retry(self):
        backend = MemoryInput(fail_enter=True)
        result = backend.submit(backend.snapshot('Fixture room'), 'new text')
        self.assertEqual(result['delivery'], 'unknown')
        self.assertEqual(backend.posts, [0x0100])

    def test_exact_hint_body_is_not_mistaken_for_a_cleared_input(self):
        class UnclearedHint(MemoryInput):
            def PostMessageW(self, _control, code, _wp, _lp):
                self.posts.append(code)
                return True
        backend = UnclearedHint()
        snapshot = backend.snapshot('Fixture room')
        with patch.object(send_win32.time, 'monotonic', side_effect=[0, 1, 4]), patch.object(send_win32.time, 'sleep'):
            result = backend.submit(snapshot, '메시지 입력')
        self.assertEqual(result['delivery'], 'unknown')
        self.assertEqual(backend.current, '메시지 입력')
        self.assertEqual(backend.posts, [0x0100, 0x0101])

    def test_token_expiring_during_catalog_validation_does_not_write(self):
        preview = self.preview()
        record = sending.TOKENS[preview['token']]
        def catalog():
            record['until'] = 0
            return CATALOG
        result = sending.confirm(preview['token'], catalog, self.backend, gate=nullcontext)
        self.assertEqual(result['delivery'], 'not_delivered')
        self.assertFalse(self.backend.calls)

    def test_shared_gate_refuses_concurrent_sender_and_does_not_wait(self):
        with tempfile.TemporaryDirectory(dir=app.BASE) as directory:
            with sending.send_gate(Path(directory)):
                with self.assertRaises(SendValidationError):
                    with sending.send_gate(Path(directory)):
                        self.fail('overlapping sender was allowed')

    def test_send_api_requires_local_token_and_forwards_only_confirmed_token(self):
        handler = object.__new__(app.Handler)
        handler.path = '/api/send'
        body = json.dumps({'token': 'fixture-token', 'roomId': 'tampered', 'text': 'tampered', 'replaceHint': True}).encode()
        handler.rfile = io.BytesIO(body)
        handler.headers = {'Host': f'127.0.0.1:{app.PORT}', 'Content-Length': str(len(body))}
        with patch.object(handler, 'respond') as respond, patch.object(sending, 'confirm') as confirm:
            handler.do_POST()
            self.assertEqual(respond.call_args.args[0], 403)
            confirm.assert_not_called()
            handler.headers['X-Local-Token'] = app.TOKEN
            confirm.return_value = {'submitted': False, 'delivery': 'not_delivered', 'message': 'fixture'}
            handler.do_POST()
            self.assertEqual(confirm.call_args.args[0], 'fixture-token')
            self.assertTrue(confirm.call_args.kwargs['replace_hint'])
            self.assertEqual(respond.call_args.args[0], 200)


if __name__ == '__main__':
    unittest.main()
