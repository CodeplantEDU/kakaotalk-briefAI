"""Native Windows entry point; no Python installation is needed in frozen builds."""
import argparse
import ctypes
import json
import os
import runpy
import sys
import threading
from pathlib import Path


def dispatch_worker():
    flags = {'--reader-worker': 'vendor/reader/worker.py', '--catalog-worker': 'bridge_worker.py'}
    if len(sys.argv) > 1 and sys.argv[1] in flags:
        from runtime_paths import BUNDLE_ROOT, prepare_worker_streams
        prepare_worker_streams()
        sys.path.insert(0, str(BUNDLE_ROOT / 'vendor/reader'))
        runpy.run_path(str(BUNDLE_ROOT / flags[sys.argv[1]]), run_name='__main__')
        return True
    return False


def show_error(message):
    ctypes.windll.user32.MessageBoxW(None, message, '대화 브리핑', 0x10)


def smoke_test(port):
    """Exercise only synthetic local HTTP state; never read Kakao or invoke an AI."""
    import urllib.request
    import tempfile
    if not os.environ.get('CHATBRIEF_DATA_DIR'):
        raise ValueError('스모크 테스트에는 별도 CHATBRIEF_DATA_DIR가 필요합니다.')
    import app
    server = app.create_server(port, start_scheduler=False)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f'http://127.0.0.1:{server.server_port}'
        with urllib.request.urlopen(base + '/api/state', timeout=10) as response:
            state = json.load(response)
        with urllib.request.urlopen(base + '/api/setup', timeout=10) as response:
            setup = json.load(response)
        result = {'http': True, 'freshProfile': not state['selected'], 'providersDetected': len(setup['providers']),
                  'frozen': bool(getattr(sys, 'frozen', False)), 'version': setup['version'], 'realChatRead': False}
        from runtime_paths import DATA_ROOT
        (DATA_ROOT / 'smoke-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        if sys.stdout:
            print(json.dumps(result, ensure_ascii=False))
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main():
    if dispatch_worker():
        return 0
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8791)
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--ui-smoke-test', action='store_true')
    parser.add_argument('--browser', action='store_true', help='브라우저 창으로 실행')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        raise ValueError('포트 번호를 확인해 주세요.')
    if args.smoke_test:
        return smoke_test(args.port)
    if args.ui_smoke_test and not os.environ.get('CHATBRIEF_DATA_DIR'):
        raise ValueError('UI 시험에는 별도 테스트 프로필이 필요합니다.')
    import app
    from runtime_paths import DATA_ROOT
    try:
        server = app.create_server(args.port, start_scheduler=not args.ui_smoke_test)
    except OSError:
        show_error('대화 브리핑이 이미 실행 중이거나 연결 포트를 사용 중입니다. 기존 프로그램을 종료한 뒤 다시 실행해 주세요.')
        return 1
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = f'http://127.0.0.1:{server.server_port}/'
    try:
        if args.browser:
            import webbrowser
            webbrowser.open(address)
            thread.join()
        else:
            import webview
            from version import APP_VERSION
            webview.settings['ALLOW_FILE_URLS'] = False
            webview.settings['ALLOW_DOWNLOADS'] = True
            webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True
            webview.settings['OPEN_DEVTOOLS_IN_DEBUG'] = False
            window = webview.create_window(f'대화 브리핑 · {APP_VERSION} 테스트', address, width=1440, height=960,
                                           min_size=(940, 660), background_color='#f5f7fa')
            watchdog = None
            if args.ui_smoke_test:
                result = {'nativeWindow': False, 'realChatRead': False}
                def loaded(*_args):
                    import time
                    for _ in range(80):
                        try:
                            evidence = window.evaluate_js("({home:!!document.getElementById('home-page'),settings:!!document.getElementById('settings-page'),menu:!!document.querySelector('.custom-select'),stats:document.getElementById('home-stats').children.length})")
                            if evidence and evidence.get('home') and evidence.get('settings') and evidence.get('menu') and evidence.get('stats') == 4:
                                result.update(nativeWindow=True, dom=evidence)
                                break
                        except Exception:
                            pass
                        time.sleep(.1)
                    (DATA_ROOT / 'ui-smoke-result.json').write_text(json.dumps(result), encoding='utf-8')
                    window.destroy()
                window.events.loaded += loaded
                watchdog = threading.Timer(20, window.destroy)
                watchdog.daemon = True
                watchdog.start()
            try:
                webview.start(gui='edgechromium', private_mode=False, storage_path=str(DATA_ROOT / 'webview'), debug=False)
            finally:
                if watchdog:
                    watchdog.cancel()
            if args.ui_smoke_test and not result['nativeWindow']:
                return 1
    except Exception:
        show_error('프로그램 창을 열지 못했습니다. Microsoft Edge WebView2 런타임이 설치되어 있는지 확인해 주세요. 오류가 계속되면 브라우저 실행 옵션을 사용해 주세요.')
        return 1
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == '__main__':
    try:
        code = main()
    except Exception:
        # Never persist a traceback that may contain chat data or access-bearing URLs.
        if '--smoke-test' in sys.argv or '--reader-worker' in sys.argv or '--catalog-worker' in sys.argv:
            code = 1
        else:
            show_error('대화 브리핑을 시작하지 못했습니다. 앱 데이터 폴더 권한과 설치 상태를 확인해 주세요.')
            code = 1
    raise SystemExit(code)
