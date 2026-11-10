"""Reply-style prompt checks using fabricated chat messages only."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import providers


class ReplyStyleTests(unittest.TestCase):
    def test_only_same_room_from_me_samples_are_extracted(self):
        messages = [
            {'fromMe': True, 'text': '네, 확인해 볼게요.'},
            {'fromMe': False, 'text': '상대 말투가 style 샘플로 들어가면 안 됨'},
            {'fromMe': True, 'text': '자료 보내 주셔서 감사합니다!'},
            {'fromMe': True, 'text': '내일 오전에 다시 말씀드릴게요.'},
            {'text': 'fromMe 누락 메시지는 제외'},
        ]
        samples, meta = providers.reply_style(messages)
        self.assertEqual(samples, [messages[0]['text'], messages[2]['text'], messages[3]['text']])
        self.assertEqual(meta, {'styleUsed': True, 'styleSampleCount': 3})

    def test_insufficient_samples_are_reported_without_claiming_style(self):
        samples, meta = providers.reply_style([
            {'fromMe': True, 'text': '짧은 메시지'},
            {'fromMe': False, 'text': '다른 사람의 긴 메시지' * 5},
        ])
        self.assertEqual(samples, [])
        self.assertEqual(meta, {'styleUsed': False, 'styleSampleCount': 1})

    def test_reply_route_passes_separate_self_samples_and_returns_metadata(self):
        with tempfile.TemporaryDirectory(dir=app.BASE) as folder, patch.object(app, 'STATE', Path(folder) / 'state.dpapi'):
            state = app.load_state()
            state['provider'] = 'codex'
            app.save_state(state)
            messages = [
                {'id': '1', 'fromMe': True, 'text': '네, 확인해 볼게요.'},
                {'id': '2', 'fromMe': False, 'text': '상대 참여자 말투 샘플 제외'},
                {'id': '3', 'fromMe': True, 'text': '자료 보내 주셔서 감사합니다!'},
                {'id': '4', 'fromMe': True, 'text': '내일 오전에 다시 말씀드릴게요.'},
            ]
            def reader(request, **_kwargs):
                return {'rooms': [{'id': '42', 'title': '가상 방'}]} if request['op'] == 'rooms' else {'messages': messages}
            handler = object.__new__(app.Handler)
            handler.path = '/api/reply'
            body = json.dumps({'roomId': '42', 'tone': '친근하게', 'context': ''}).encode()
            handler.rfile = io.BytesIO(body)
            handler.headers = {'Host': f'127.0.0.1:{app.PORT}', 'Content-Length': str(len(body)), 'X-Local-Token': app.TOKEN}
            with patch.object(app, 'read_local', side_effect=reader), \
                 patch.object(providers, 'summarize', return_value={'42': {'text': '가상 답장', 'tasks': []}}) as generate, \
                 patch.object(handler, 'respond') as respond:
                handler.do_POST()
            room = generate.call_args.args[1][0]
            self.assertEqual(room['styleSamples'], [messages[0]['text'], messages[2]['text'], messages[3]['text']])
            self.assertIn('다른 참여자의 말투는 따라 하지 않는다', generate.call_args.kwargs['instruction'])
            self.assertIn('사용자가 말하지 않은 사실, 경험, 약속, 날짜, 결정, 의향을 만들지 않는다', generate.call_args.kwargs['instruction'])
            self.assertEqual(respond.call_args.args[1], {'text': '가상 답장', 'styleUsed': True, 'styleSampleCount': 3})


if __name__ == '__main__':
    unittest.main()
