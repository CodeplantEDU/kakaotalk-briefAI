"""User-triggered official CLI installation, with fixed commands and safe statuses."""
import json
import os
import secrets
import shutil
import subprocess
import threading
from pathlib import Path
import win32api
import win32con
import win32job
import providers
from runtime_paths import VERSION, DATA_ROOT, BUNDLE_ROOT

PACKAGES = {'codex': '@openai/codex', 'claude': '@anthropic-ai/claude-code', 'gemini': '@google/gemini-cli'}
JOBS = {}
LOCK = threading.Lock()


def login_command(provider):
    prefix = providers.executable(provider)
    if not prefix:
        return None
    arguments = prefix + {'codex': ['login'], 'claude': ['auth', 'login'], 'gemini': []}[provider]
    return '& ' + ' '.join("'" + str(argument).replace("'", "''") + "'" for argument in arguments)


def _run_quiet(command, timeout):
    child = subprocess.Popen(command, cwd=DATA_ROOT, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
    job = handle = None
    try:
        job = win32job.CreateJobObject(None, f'Local\\ChatBriefSetup-{child.pid}')
        limits = win32job.QueryInformationJobObject(job, win32job.JobObjectExtendedLimitInformation)
        limits['BasicLimitInformation']['LimitFlags'] = win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        win32job.SetInformationJobObject(job, win32job.JobObjectExtendedLimitInformation, limits)
        handle = win32api.OpenProcess(win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, child.pid)
        win32job.AssignProcessToJobObject(job, handle)
        return child.wait(timeout=timeout)
    finally:
        if job:
            job.Close()
        if child.poll() is None:
            child.kill()
        child.wait(timeout=10)
        if handle:
            handle.Close()


def npm_command(provider):
    if provider not in PACKAGES:
        raise ValueError('지원하지 않는 설치 항목입니다.')
    node = providers.node_executable()
    shim = shutil.which('npm.cmd')
    candidates = []
    candidates.append(BUNDLE_ROOT / 'runtime/node/node_modules/npm/bin/npm-cli.js')
    if shim:
        candidates.append(Path(shim).parent / 'node_modules/npm/bin/npm-cli.js')
    if node:
        candidates.append(Path(node).parent / 'node_modules/npm/bin/npm-cli.js')
    script = next((path for path in candidates if path.is_file()), None)
    if not node or script is None:
        raise ValueError('Node.js 런타임을 찾지 못했습니다. 프로그램을 다시 설치하거나 Node.js LTS를 설치해 주세요.')
    return [node, str(script), 'install', '--global', '--prefix', str(providers.CLI_ROOT), '--ignore-scripts', '--no-audit', '--no-fund', '--registry=https://registry.npmjs.org', PACKAGES[provider]]


def status():
    rows = []
    for item in providers.installed():
        try:
            npm_command(item['id'])
            installable = not item['installed']
        except ValueError:
            installable = False
        message = '설치됨. 연결 테스트에서 본인 로그인과 응답을 확인해 주세요.' if item['installed'] else '공식 CLI를 설치한 뒤 본인 계정으로 로그인해 주세요.'
        state = 'installed' if item['installed'] else 'missing'
        if item['id'] == 'gemini':
            message += ' 기존 개인용 Gemini CLI는 지원 종료 응답이 확인됐으며 설치만으로 개인 계정 연결이 보장되지 않습니다.'
        rows.append({**item, 'status': state, 'message': message, 'installable': installable,
            'loginCommand': login_command(item['id'])})
    node = providers.node_executable()
    rows.insert(0, {'id': 'node', 'name': 'Node.js LTS', 'installed': bool(node),
        'status': 'installed' if node else 'missing', 'message': '앱에 포함된 Node.js 런타임을 사용합니다.' if node and Path(node).is_relative_to(BUNDLE_ROOT) else 'Node.js LTS 런타임을 찾았습니다.' if node else 'Node.js 런타임을 찾지 못했습니다.',
        'installable': False, 'downloadUrl': 'https://nodejs.org/en/download'})
    with LOCK:
        jobs = [dict(job) for job in JOBS.values()]
    return {'version': VERSION, 'desktop': bool(getattr(__import__('sys'), 'frozen', False)), 'providers': rows, 'jobs': jobs}


def _install(job_id, command):
    with LOCK:
        JOBS[job_id].update(status='running', message='공식 패키지를 설치하고 있습니다.')
    try:
        if _run_quiet(command, timeout=300):
            raise ValueError('설치를 완료하지 못했습니다. 네트워크와 설치 권한을 확인해 주세요.')
        provider = JOBS[job_id]['provider']
        if not providers.executable(provider):
            raise ValueError('패키지 설치 후 실행 파일을 찾지 못했습니다. 프로그램을 다시 실행해 주세요.')
        if _run_quiet(providers.executable(provider) + ['--version'], timeout=20):
            raise ValueError('CLI 실행을 확인하지 못했습니다.')
        with LOCK:
            JOBS[job_id].update(status='succeeded', message='설치했습니다. 본인 계정으로 로그인한 뒤 연결 테스트를 실행해 주세요.')
    except Exception:
        with LOCK:
            JOBS[job_id].update(status='failed', message='설치를 완료하지 못했습니다. 공식 CLI 설치 안내와 네트워크·권한을 확인해 주세요.')


def install(provider):
    command = npm_command(provider)
    if providers.executable(provider):
        raise ValueError('이미 설치된 AI입니다. 연결 테스트를 실행해 주세요.')
    with LOCK:
        if any(job['status'] in ('queued', 'running') for job in JOBS.values()):
            raise ValueError('다른 설치가 진행 중입니다. 완료 후 다시 시도해 주세요.')
        job_id = secrets.token_hex(12)
        job = {'id': job_id, 'jobId': job_id, 'provider': provider, 'status': 'queued', 'message': '설치를 준비하고 있습니다.'}
        JOBS[job_id] = job
    threading.Thread(target=_install, args=(job_id, command), daemon=True).start()
    return dict(job)


def get_job(job_id):
    with LOCK:
        job = JOBS.get(job_id)
        if job is None:
            raise ValueError('설치 작업을 찾을 수 없습니다.')
        return dict(job)
