"""Small offline self-checks; no real chat or model invocation."""
import json
import tempfile
from pathlib import Path
from datetime import datetime
from unittest.mock import patch
import app
import providers


def run():
    at = datetime(2026, 11, 9, 8, 0, tzinfo=app.KST)
    assert app.next_run('09:00', at) == '2026-11-09T09:00:00+09:00'
    assert app.next_run('07:00', at) == '2026-11-10T07:00:00+09:00'
    messages = [{'text': '내일 오후 3시에 회의합니다.'}, {'text': '감사합니다.'}, {'text': '13일까지 부탁합니다.'}]
    assert app.candidates(messages) == [messages[0], messages[2]]
    raw = {'summaries': [{'id': '123', 'text': '원문 기반 요약'}]}
    encoded = json.dumps(raw)
    for name, response in [('codex', encoded), ('claude', json.dumps({'result': encoded})), ('gemini', json.dumps({'response': encoded}))]:
        assert providers.parse_output(name, response) == {'123': {'text': '원문 기반 요약', 'tasks': []}}
    try:
        providers.parse_output('codex', json.dumps({'summaries': [{'id': '1', 'text': 'a'}, {'id': '1', 'text': 'b'}]}))
    except ValueError:
        pass
    else:
        raise AssertionError('duplicate room must fail')
    with tempfile.TemporaryDirectory(dir=app.BASE) as folder, patch.object(app, 'STATE', Path(folder) / 'state.dpapi'):
        state = app.load_state()
        state['selected'] = [{'id': '123', 'title': '가상 채팅방'}]
        app.save_state(state)
        assert app.load_state() == state
        assert '가상 채팅방'.encode() not in app.STATE.read_bytes()
        collection = {'checkedAt': app.now(), 'rooms': [{'id': '123', 'title': '가상 채팅방', 'messages': [], 'events': [], 'through': '999'}]}
        assert app.persist_report(collection)['reports']['123']['through'] is None
        assert app.persist_report(collection, {'123': '요약'}, advance=True)['reports']['123']['through'] == '999'
        assert app.persist_report(collection)['reports']['123']['through'] == '999'
        state = app.load_state()
        room = {'id': '123', 'title': '테스트', 'messages': [{'id': '1', 'text': '자료를 보내 주세요.'}]}
        task = {'title': '자료 보내기', 'evidenceId': '1', 'due': None, 'assignee': None}
        app.add_task(state, task, room)
        app.add_task(state, task, room)
        assert len(state['todos']) == 1 and state['todos'][0]['source']['id'] == '1'
        state['reports'] = {}
        app.save_state(state)
        stored = [{'id': '1', 'sentAt': '2026-11-08T12:00:00+09:00', 'text': '과거 대화'}, {'id': '2', 'sentAt': app.now(), 'text': '오늘 대화'}]
        with patch.object(app, 'read_local', return_value={'messages': stored, 'next_before_id': None, 'coverage': {}}):
            assert len(app.collect(scope='all')['rooms'][0]['messages']) == 2
            assert [m['id'] for m in app.collect(scope='today')['rooms'][0]['messages']] == ['2']
            state = app.load_state()
            state['scheduleSelected'] = [{'id': '456', 'title': '별도 예약 대상'}]
            state['enabled'] = True
            app.save_state(state)
            assert app.collect(scope='all')['rooms'][0]['id'] == '123'
            assert app.collect(respect_enabled=True)['rooms'][0]['id'] == '456'
            assert [m['id'] for m in app.collect(scope='range', start='2026-11-08', end='2026-11-08')['rooms'][0]['messages']] == ['1']
            try:
                app.collect(scope='range', start='2026-11-10', end='2026-11-08')
            except ValueError:
                pass
            else:
                raise AssertionError('reversed date range must fail')
        collection['scheduled'] = True
        app.persist_report(collection, {'123': {'text': '예약 요약', 'tasks': []}}, advance=True)
        history = app.load_state()['history']
        assert history[-1]['scheduled'] is True and history[-1]['summary'] == '예약 요약'
        before = len(history)
        app.persist_report(collection, {'123': {'text': '다음 예약 요약', 'tasks': []}}, advance=True)
        assert len(app.load_state()['history']) == before + 1
    import media
    assert media.allowed('https://talk.kakaocdn.net/file/test')
    assert not media.allowed('http://talk.kakaocdn.net/file/test')
    assert not media.allowed('https://talk.kakaocdn.net.evil.example/file')
    assert not media.allowed('https://127.0.0.1/private')
    assert all(not (app.BASE / 'vendor/reader/private').exists() for _ in [0])
    print('PASS: schedule, evidence candidates, provider JSON, duplicate rejection, DPAPI, successful cursor')


if __name__ == '__main__':
    run()
