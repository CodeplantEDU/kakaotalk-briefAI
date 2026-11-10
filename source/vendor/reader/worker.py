"""One bounded read. Only a DPAPI key-cache update may leave as a private field."""
import json
import os
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))


def read_only_audit(event,args):
    if event.startswith('socket.') or event in {'subprocess.Popen','os.system','os.startfile','os.remove','os.rename','os.mkdir','os.rmdir'}:
        raise PermissionError('LOCAL_READ_ONLY_BOUNDARY')
    if event=='open':
        mode=args[1]
        flags=args[2]
        if (isinstance(mode,str) and any(char in mode for char in 'wax+')) or (isinstance(flags,int) and flags & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND)):
            raise PermissionError('FILE_WRITES_DISABLED')
    if event=='sqlite3.connect' and args[0]!=':memory:':
        raise PermissionError('PLAINTEXT_SQLITE_FILE_DISABLED')
    if event=='ctypes.dlopen' and isinstance(args[0],str) and any(name in args[0].lower() for name in ('user32','uiautomation','ole32')):
        raise PermissionError('UI_APIS_DISABLED')


if __name__=='__main__':
    sys.addaudithook(read_only_audit)
    try:
        import backend
        request=json.loads(sys.stdin.buffer.readline(20_001))
        result=backend.perform(request)
    except Exception as error:
        if hasattr(error,'envelope'):
            result=error.envelope()
        else:
            result={'error':str(error) if isinstance(error,(ValueError,PermissionError)) else type(error).__name__}
    if 'backend' in locals():
        update=backend.cache_update()
        if update:
            result['_encrypted_key_cache_update']=update
    print(json.dumps(result,ensure_ascii=False),flush=True)
