"""Non-personal browser fixture: no Kakao access, shell, account, or AI calls.

Run with Python and open http://127.0.0.1:8855. Installation only changes an
in-memory fixture; it never installs a package. Do not include this in a release.
"""
import json
import secrets
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

BASE = Path(__file__).resolve().parent
NOW = datetime.now(timezone(timedelta(hours=9))).isoformat()
ROOMS = [{'id': str(i), 'title': f'테스트 채팅방 {i:03}', 'memberCount': 3,
          'readable': True} for i in range(1, 301)]
STATE = {'selected': [], 'scheduleSelected': [], 'enabled': False, 'time': '09:00',
         'provider': 'codex', 'reports': {}, 'lastRun': None, 'nextRun': None,
         'job': None, 'todos': [], 'autoTodos': False, 'drafts': {}, 'history': [],
         'tutorialVersion': '2', 'tutorialSeen': True, 'token': 'fixture-only-no-real-account'}
PROVIDERS = [{'id': key, 'name': label, 'installed': False, 'status': 'missing',
              'message': '브라우저 검수용 가상 설치 상태입니다.', 'installable': True}
             for key, label in [('codex', 'Codex'), ('claude', 'Claude'), ('gemini', 'Gemini')]]
PROVIDERS.append({'id': 'node', 'name': 'Node.js', 'installed': False, 'status': 'missing',
                  'message': '브라우저 검수용 가상 상태입니다.', 'installable': False})
JOBS = {}
SEND_PREVIEWS = {}
SEND_COUNT = 0
SENT_FIXTURE_MESSAGES = {}
HISTORY_CALLS = {}
SUMMARY_FAILURES = 0


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def result(self, value, status=200, mime='application/json; charset=utf-8'):
        content = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path == '/api/state':
            return self.result({**STATE, 'tutorialCurrentVersion': '2', 'providers': deepcopy(PROVIDERS)})
        if parsed.path == '/api/setup':
            return self.result({'version': '0.1.0-fixture', 'desktop': False,
                                'providers': deepcopy(PROVIDERS), 'jobs': list(JOBS.values())})
        if parsed.path == '/api/setup/job':
            identity = parse_qs(parsed.query).get('id', [''])[0]
            job = JOBS.get(identity)
            if not job:
                return self.result({'error': '가상 작업을 찾을 수 없습니다.'}, 404)
            job['status'] = 'succeeded'
            job['message'] = '검수용 가상 설치를 완료했습니다. 실제 패키지는 설치하지 않았습니다.'
            for provider in PROVIDERS:
                if provider['id'] == job['provider']:
                    provider.update(installed=True, status='installed')
                    provider['loginCommand'] = "& 'C:/Fixture Node/node.exe' 'C:/Fixture CLI/entry.js' 'login'"
            return self.result(job)
        files = {'/': ('index.html', 'text/html; charset=utf-8'),
                 '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                 '/style.css': ('style.css', 'text/css; charset=utf-8'),
                 '/fonts/PretendardVariable.woff2': ('fonts/PretendardVariable.woff2', 'font/woff2')}
        if parsed.path in files:
            name, mime = files[parsed.path]
            return self.result((BASE / name).read_bytes(), mime=mime)
        self.result({'error': '가상 페이지가 없습니다.'}, 404)

    def do_POST(self):
        global SEND_COUNT
        payload = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
        if self.path == '/api/rooms':
            return self.result({'rooms': ROOMS})
        if self.path == '/api/tutorial':
            if set(payload) != {'action'} or payload['action'] not in ('finish', 'dismiss'):
                return self.result({'error': '튜토리얼 상태를 확인해 주세요.'}, 400)
            STATE['tutorialVersion'] = '2'
            STATE['tutorialSeen'] = True
            return self.result({'tutorialVersion': '2', 'tutorialSeen': True})
        if self.path == '/api/tutorial-fixture/reset':
            STATE['tutorialVersion'] = '1'
            STATE['tutorialSeen'] = True
            return self.result({'ok': True})
        if self.path == '/api/tutorial-fixture/summary-failures':
            global SUMMARY_FAILURES
            count = payload.get('count')
            if type(count) is not int or not 0 <= count <= 10:
                return self.result({'error': '가상 실패 횟수는 0에서 10 사이 정수여야 합니다.'}, 400)
            SUMMARY_FAILURES = count
            return self.result({'summaryFailures': count})
        if self.path == '/api/settings':
            STATE.update({key: payload[key] for key in ('selected', 'scheduleSelected', 'enabled', 'time', 'provider', 'autoTodos') if key in payload})
            return self.result(STATE)
        if self.path == '/api/setup/install':
            key = payload['provider']
            identity = 'fixture-' + key
            JOBS[identity] = {'id': identity, 'jobId': identity, 'provider': key,
                              'status': 'running', 'message': '가상 설치 진행 중'}
            return self.result({'jobId': identity})
        if self.path == '/api/test-provider':
            return self.result({'ok': True, 'provider': payload['provider']})
        if self.path == '/api/history':
            room = next((r for r in ROOMS if r['id'] == payload.get('roomId')), ROOMS[0])
            if room['id'] == '300':
                calls = HISTORY_CALLS.get(room['id'], 0) + 1
                HISTORY_CALLS[room['id']] = calls
                if payload.get('beforeId'):
                    messages = [{'id': '30008', 'sender': '가상 참여자', 'text': '이전 페이지의 첫 대화입니다.', 'sentAt': NOW, 'fromMe': False, 'kind': 'text'},
                                {'id': '30009', 'sender': '나', 'text': '이전 페이지의 답장입니다.', 'sentAt': NOW, 'fromMe': True, 'kind': 'text'}]
                    next_before_id = None
                else:
                    messages = [{'id': '30011', 'sender': '가상 참여자', 'text': '최근 대화입니다.', 'sentAt': NOW, 'fromMe': False, 'kind': 'text'},
                                {'id': '30012', 'sender': '나', 'text': '최근 답장입니다.', 'sentAt': NOW, 'fromMe': True, 'kind': 'text'}]
                    if calls >= 3:
                        messages.append({'id': '30013', 'sender': '가상 참여자', 'text': '자동 새로고침으로 도착한 가상 메시지입니다.', 'sentAt': NOW, 'fromMe': False, 'kind': 'text'})
                    next_before_id = '30010'
            else:
                messages = [{'id': '11', 'sender': '가상 참여자', 'text': '내일 오전에 자료를 함께 확인해 주세요.',
                             'sentAt': NOW, 'fromMe': False, 'kind': 'text'},
                            {'id': '12', 'sender': '나', 'text': '확인한 뒤 의견을 정리하겠습니다.',
                             'sentAt': NOW, 'fromMe': True, 'kind': 'text'}]
                next_before_id = None
            messages.extend(SENT_FIXTURE_MESSAGES.get(room['id'], []))
            return self.result({'room': room, 'messages': messages, 'attachments': [],
                                'next_before_id': next_before_id, 'coverage': {'storedLocally': len(messages)}})
        if self.path == '/api/check':
            selected = [r for r in ROOMS if r['id'] in payload['roomIds']] if 'roomIds' in payload else STATE['selected']
            if payload.get('roomId'):
                selected = [room for room in ROOMS if room['id'] == payload['roomId']]
            failed = SUMMARY_FAILURES > 0
            if failed:
                SUMMARY_FAILURES -= 1
            for room in selected:
                if failed:
                    report = {**STATE['reports'].get(room['id'], {}), 'id': room['id'], 'title': room['title'],
                              'error': 'FIXTURE_SUMMARY_ERROR', 'checkedAt': NOW, 'scope': payload.get('scope', 'all')}
                    STATE['reports'][room['id']] = report
                    continue
                summary = '가상 대화 요약입니다. 내일 자료 확인 후 의견을 정리하기로 했습니다.'
                report = {'id': room['id'], 'title': room['title'], 'summary': summary,
                          'messages': [], 'events': [], 'suggestedTasks': [],
                          'checkedAt': NOW, 'scope': payload.get('scope', 'all'),
                          'dateRange': {'start': payload.get('start'), 'end': payload.get('end')}
                          if payload.get('scope') == 'range' else None}
                STATE['reports'][room['id']] = report
                STATE['history'].append({'id': room['id'] + '-test', 'roomId': room['id'],
                    'title': room['title'], 'summary': summary, 'checkedAt': NOW,
                    'scope': report['scope'], 'messageCount': 2, 'scheduled': False})
            STATE['lastRun'] = NOW
            return self.result(STATE)
        if self.path == '/api/reply':
            return self.result({'text': '검토 후 의견을 정리해 드리겠습니다. (검수용 가상 초안)',
                                'styleUsed': False, 'styleSampleCount': 1})
        if self.path == '/api/save-draft':
            STATE['drafts'][payload['roomId']] = payload['text']
            return self.result({'ok': True})
        if self.path == '/api/send-preview':
            room = next((r for r in ROOMS if r['id'] == payload.get('roomId')), None)
            body = payload.get('text')
            if room is None or not isinstance(body, str) or not body.strip() or len(body) > 2000 or '\0' in body:
                return self.result({'error': '가상 전송 대상과 본문을 확인해 주세요.'}, 400)
            identity = secrets.token_hex(16)
            preview = {'token': identity, 'roomId': room['id'], 'title': room['title'], 'text': body,
                'expiresAt': (datetime.now(timezone(timedelta(hours=9))) + timedelta(seconds=60)).isoformat(),
                'requiresHintReplacement': '[hint]' in body}
            SEND_PREVIEWS[identity] = preview
            return self.result(preview)
        if self.path == '/api/send':
            preview = SEND_PREVIEWS.pop(payload.get('token'), None)
            if not preview:
                return self.result({'submitted': False, 'delivery': 'not_delivered', 'message': '가상 확인 정보가 없거나 이미 사용됐습니다.'}, 409)
            if preview.get('requiresHintReplacement') and payload.get('replaceHint') is not True:
                return self.result({'submitted': False, 'delivery': 'not_delivered', 'message': '가상 안내 문구 대체에 동의하지 않았습니다.'}, 409)
            SEND_COUNT += 1
            if '[transport]' in preview['text']:
                return self.result(b'fixture acknowledgement lost', mime='text/plain; charset=utf-8')
            if '[unknown]' in preview['text']:
                return self.result({'submitted': False, 'delivery': 'unknown', 'message': '가상 결과 불확실. 실제 전송하지 않았습니다.'})
            if '[not_delivered]' in preview['text']:
                return self.result({'submitted': False, 'delivery': 'not_delivered', 'message': '가상 전송 거부. 실제 전송하지 않았습니다.'})
            SENT_FIXTURE_MESSAGES.setdefault(preview['roomId'], []).append({'id': 'fixture-sent-' + str(SEND_COUNT),
                'sender': '나', 'text': preview['text'], 'sentAt': NOW, 'fromMe': True, 'kind': 'text'})
            return self.result({'submitted': True, 'delivery': 'submitted', 'message': f'가상 제출 {SEND_COUNT}회. 실제 카카오톡 전송은 수행하지 않았습니다.'})
        if self.path == '/api/tasks':
            if payload['action'] == 'add':
                STATE['todos'].append({'id': 'fixture-task-' + str(len(STATE['todos']) + 1),
                    'title': payload['title'], 'due': payload.get('due'), 'assignee': None,
                    'done': False, 'archived': False, 'createdAt': NOW, 'roomTitle': None})
            elif payload['action'] in ('done', 'archive'):
                task = next(t for t in STATE['todos'] if t['id'] == payload['id'])
                task['done' if payload['action'] == 'done' else 'archived'] = payload['value']
            return self.result(STATE)
        self.result({'error': '검수 fixture가 지원하지 않는 요청입니다.'}, 404)


if __name__ == '__main__':
    print('가상 데이터 UI 검수: http://127.0.0.1:8855', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 8855), Handler).serve_forever()
