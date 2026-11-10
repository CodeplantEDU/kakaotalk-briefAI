"""Minimal text-only Win32 input adapter derived from nichirin/kanao (MIT).

Source: sanguneo/nichirin 6e7838c86064f88695d8b0b24b16b2c6a7a55b1e,
windows/kanao/winauto.py. Original notices remain in THIRD_PARTY_LICENSE.txt.
No window opener, clipboard, mouse, or foreground change. Only the fixed hint
may be replaced by an explicit send action; other drafts are blocked.
"""
import ctypes
from ctypes import wintypes
import time
import win32api
import win32process
import backend


class SendValidationError(ValueError):
    pass


class Win32SendBackend:
    def __init__(self):
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user = self.user
        user.EnumWindows.argtypes = (self.callback, wintypes.LPARAM)
        user.EnumChildWindows.argtypes = (wintypes.HWND, self.callback, wintypes.LPARAM)
        user.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        user.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
        user.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        user.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
        for name in ('IsWindow', 'IsWindowVisible', 'IsWindowEnabled'):
            getattr(user, name).argtypes = (wintypes.HWND,)
        user.IsChild.argtypes = (wintypes.HWND, wintypes.HWND)
        user.GetForegroundWindow.restype = wintypes.HWND
        user.SendMessageTimeoutW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
            wintypes.LPARAM, wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t))
        user.SendMessageTimeoutW.restype = ctypes.c_ssize_t
        user.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
        user.PostMessageW.restype = wintypes.BOOL

    def identity(self):
        pid = backend.owned_pid()
        if pid is None:
            raise SendValidationError('카카오톡을 실행하고 해당 채팅방을 별도 창으로 열어 주세요.')
        handle = win32api.OpenProcess(0x0410, False, pid)
        try:
            created = win32process.GetProcessTimes(handle)['CreationTime'].isoformat()
        except ImportError:
            raise SendValidationError('전송 도구의 구성 파일이 누락됐습니다. 최신 설치 파일로 다시 설치해 주세요.') from None
        finally:
            handle.Close()
        return {'pid': pid, 'created': created}

    def _pid(self, handle):
        pid = wintypes.DWORD()
        self.user.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        return pid.value

    def _title(self, handle):
        count = self.user.GetWindowTextLengthW(handle)
        if not 0 <= count <= 300:
            raise SendValidationError('채팅방 창 제목을 안전하게 확인하지 못했습니다.')
        value = ctypes.create_unicode_buffer(count + 1)
        self.user.GetWindowTextW(handle, value, count + 1)
        return value.value

    def _class(self, handle):
        value = ctypes.create_unicode_buffer(256)
        self.user.GetClassNameW(handle, value, 256)
        return value.value

    def _message(self, handle, code, wp=0, lp=0):
        result = ctypes.c_size_t()
        if not self.user.SendMessageTimeoutW(handle, code, wp, lp, 3, 500, ctypes.byref(result)):
            raise OSError('KakaoTalk input did not answer within the deadline')
        return result.value

    def text(self, control):
        count = self._message(control, 0x000E)
        if count > 20_000:
            raise SendValidationError('카카오톡 입력창의 기존 초안을 먼저 확인해 주세요.')
        value = ctypes.create_unicode_buffer(count + 1)
        self._message(control, 0x000D, count + 1, ctypes.addressof(value))
        return value.value

    def empty(self, control, allow_hint=False):
        existing = self.text(control)
        if existing == '메시지 입력':
            if allow_hint:
                return existing
            raise SendValidationError('카카오톡 입력창이 안내 문구를 실제 텍스트로 반환합니다. 기존 초안과 구분할 수 없어 전송을 차단했습니다. 카카오톡에서 입력창을 직접 확인해 주세요.')
        if existing:
            raise SendValidationError('카카오톡 입력창에 기존 초안이 있어 전송을 차단했습니다. 기존 초안을 지우거나 보내고 다시 전송을 눌러 주세요.')
        return existing

    def snapshot(self, title, allow_hint=True):
        identity = self.identity()
        matches = []
        def visit(handle, _parameter):
            if self._pid(handle) == identity['pid'] and self.user.IsWindowVisible(handle) and self._title(handle).casefold() == title.casefold():
                matches.append(int(handle))
            return True
        self.user.EnumWindows(self.callback(visit), 0)
        if len(matches) != 1:
            raise SendValidationError('제목이 정확히 일치하는 열린 채팅방 창이 하나여야 합니다. 해당 방을 별도 창으로 열고 중복 창을 닫아 주세요.')
        window = matches[0]
        inputs = []
        def child(handle, _parameter):
            if self._pid(handle) == identity['pid'] and self._class(handle) == 'RICHEDIT50W':
                inputs.append(int(handle))
            return True
        self.user.EnumChildWindows(window, self.callback(child), 0)
        if len(inputs) != 1:
            raise SendValidationError('채팅방의 메시지 입력창을 하나로 확인하지 못했습니다.')
        result = {**identity, 'window': window, 'control': inputs[0], 'title': self._title(window)}
        self.validate(result)
        result['initialText'] = self.empty(result['control'], allow_hint=allow_hint)
        return result

    def validate(self, expected):
        if self.identity() != {'pid': expected['pid'], 'created': expected['created']}:
            raise SendValidationError('카카오톡 실행 상태가 바뀌었습니다. 다시 전송을 눌러 주세요.')
        window, control = expected['window'], expected['control']
        if not (self.user.IsWindow(window) and self.user.IsWindow(control)
                and self.user.IsWindowVisible(window) and self.user.IsWindowEnabled(window)
                and self.user.IsWindowEnabled(control) and self.user.IsChild(window, control)
                and self._pid(window) == expected['pid'] and self._pid(control) == expected['pid']
                and self._title(window) == expected['title'] and self._class(control) == 'RICHEDIT50W'):
            raise SendValidationError('대상 채팅방이나 입력창이 바뀌었습니다. 다시 전송을 눌러 주세요.')
        if self.user.GetForegroundWindow() == window:
            raise SendValidationError('카카오톡 창에서 직접 입력 중일 수 있어 차단했습니다. 이 프로그램에서 다시 확인해 주세요.')

    def submit(self, expected, text, replace_hint=False):
        attempting_enter = False
        wrote = False
        try:
            current = self.snapshot(expected['title'], allow_hint=replace_hint)
            if current != expected:
                raise SendValidationError('미리보기 이후 대상 창이 바뀌었습니다. 다시 전송을 눌러 주세요.')
            self.validate(expected)
            initial = self.empty(expected['control'], allow_hint=replace_hint)
            if initial != expected.get('initialText', ''):
                raise SendValidationError('미리보기 이후 입력창 내용이 바뀌어 전송을 차단했습니다.')
            replace_length = len(initial) if initial == '메시지 입력' and replace_hint else 0
            # Replace only the previewed fixed hint after explicit consent; never any other draft.
            self._message(expected['control'], 0x00B1, 0, replace_length)
            self.validate(expected)
            if self.text(expected['control']) != initial or self._message(expected['control'], 0x00B0) != (replace_length << 16):
                raise SendValidationError('입력창 내용이나 선택 영역이 바뀌어 전송을 차단했습니다.')
            buffer = ctypes.create_unicode_buffer(text)
            wrote = True
            self._message(expected['control'], 0x00C2, 1, ctypes.addressof(buffer))
            self.validate(expected)
            actual = self.text(expected['control']).replace('\r\n', '\n').replace('\r', '\n')
            if actual != text.replace('\r\n', '\n').replace('\r', '\n'):
                raise SendValidationError('입력 내용이 확인한 본문과 달라 전송하지 않았습니다. 카카오톡 입력창을 직접 확인해 주세요.')
            attempting_enter = True
            if not self.user.PostMessageW(expected['control'], 0x0100, 0x0D, 0x001C0001):
                raise OSError('Enter keydown could not be queued')
            if not self.user.PostMessageW(expected['control'], 0x0101, 0x0D, 0xC01C0001):
                raise OSError('Enter keyup could not be queued')
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                self.validate(expected)
                remaining = self.text(expected['control'])
                if remaining == '' or (remaining == '메시지 입력' and text.replace('\r\n', '\n').replace('\r', '\n') != '메시지 입력'):
                    return {'submitted': True, 'delivery': 'submitted', 'message': '카카오톡이 입력을 접수했습니다. 상대방 도착 여부는 대화에서 확인해 주세요.'}
                time.sleep(.1)
            raise OSError('Input did not clear after Enter')
        except Exception as error:
            if attempting_enter:
                return {'submitted': False, 'delivery': 'unknown', 'message': '전송 여부를 확정하지 못했습니다. 자동으로 다시 보내지 않습니다. 카카오톡 대화를 직접 확인해 주세요.'}
            message = str(error) if isinstance(error, SendValidationError) else '전송하지 않았습니다. 카카오톡 실행 상태와 대상 입력창을 확인해 주세요.'
            if wrote:
                message += ' 입력창에는 작성한 내용이 남아 있을 수 있습니다.'
            return {'submitted': False, 'delivery': 'not_delivered', 'message': message}
