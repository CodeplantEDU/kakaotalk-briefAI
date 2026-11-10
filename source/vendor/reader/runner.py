"""Start a one-shot read worker with Windows process and memory limits."""
import json
import os
import subprocess
import sys
import threading
import msvcrt
from pathlib import Path
import win32api
import win32con
import win32job

BASE=Path(__file__).resolve().parent
if str(BASE.parents[1]) not in sys.path:
    sys.path.append(str(BASE.parents[1]))
from runtime_paths import READER_PRIVATE
_lock=threading.Lock()


def run_request(request, worker_script=None, timeout=90):
    with _lock:
        if request.get('op')=='status':
            return _run_request(request, worker_script=worker_script, timeout=timeout)
        # Serialize cache load/read/save across separate Codex MCP processes.
        with (READER_PRIVATE/'cache.lock').open('a+b') as guard:
            guard.seek(0)
            try:
                msvcrt.locking(guard.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:
                return {'error':'BUSY','detail':'Another local read is active; try again.'}
            try:
                return _run_request(request, worker_script=worker_script, timeout=timeout)
            finally:
                guard.seek(0)
                msvcrt.locking(guard.fileno(),msvcrt.LK_UNLCK,1)


def worker_command(worker_script=None):
    script=Path(worker_script) if worker_script else BASE/'worker.py'
    if getattr(sys,'frozen',False):
        executable=Path(sys.executable).with_name('ChatBriefWorker.exe')
        if not executable.is_file():
            raise FileNotFoundError('WORKER_EXECUTABLE_MISSING')
        return [str(executable),'--catalog-worker' if script.name=='bridge_worker.py' else '--reader-worker']
    return [sys.executable,'-B','-X','utf8','-u',str(script)]


def _run_request(request, worker_script=None, timeout=90):
    environment={key:value for key,value in os.environ.items() if key.upper() in {
        'SYSTEMROOT','WINDIR','PATH','LOCALAPPDATA','APPDATA','USERPROFILE','TEMP','TMP','CHATBRIEF_DATA_DIR'}}
    environment['PYTHONDONTWRITEBYTECODE']='1'
    environment['PYTHONUTF8']='1'
    environment['PYTHONIOENCODING']='utf-8'
    try:
        command=worker_command(worker_script)
    except FileNotFoundError:
        return {'error':'WORKER_EXECUTABLE_MISSING','detail':'읽기 작업 실행 파일이 없습니다. 프로그램을 다시 설치해 주세요.'}
    child=subprocess.Popen(command,cwd=BASE,
        stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        env=environment,creationflags=0x08000000)
    job=None
    process_handle=None
    try:
        job=win32job.CreateJobObject(None,f'Local\\CodeplantKakaoRead-{child.pid}')
        limits=win32job.QueryInformationJobObject(job,win32job.JobObjectExtendedLimitInformation)
        limits['BasicLimitInformation']['LimitFlags']=(win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE|
            win32job.JOB_OBJECT_LIMIT_PROCESS_MEMORY|win32job.JOB_OBJECT_LIMIT_PROCESS_TIME|
            win32job.JOB_OBJECT_LIMIT_ACTIVE_PROCESS)
        limits['BasicLimitInformation']['PerProcessUserTimeLimit']=600_000_000
        # Windows venv launcher starts the actual Python process as its child.
        limits['BasicLimitInformation']['ActiveProcessLimit']=2
        limits['ProcessMemoryLimit']=1024*1024*1024
        win32job.SetInformationJobObject(job,win32job.JobObjectExtendedLimitInformation,limits)
        process_handle=win32api.OpenProcess(win32con.PROCESS_SET_QUOTA|win32con.PROCESS_TERMINATE,False,child.pid)
        win32job.AssignProcessToJobObject(job,process_handle)
        output,_errors=child.communicate((json.dumps(request,ensure_ascii=False)+'\n').encode('utf-8'),timeout=min(90,max(.1,timeout)))
        if child.returncode or len(output)>8_000_000:
            return {'error':'WORKER_FAILED_OR_RESOURCE_LIMIT','exit_code':child.returncode,
                    **({'diagnostic':_errors.decode('utf-8',errors='replace')[:2000]} if request.get('op')=='status' else {})}
        result=json.loads(output.decode('utf-8'))
        encrypted=result.pop('_encrypted_key_cache_update',None)
        if encrypted:
            from key_cache import save_encrypted
            save_encrypted(encrypted)
        return result
    except subprocess.TimeoutExpired:
        return {'error':'LOCAL_READ_TIMEOUT'}
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        if process_handle:
            process_handle.Close()
        if job:
            job.Close()


if __name__=='__main__':
    request=json.loads(sys.stdin.buffer.readline(20_001))
    print(json.dumps(run_request(request),ensure_ascii=False))
