"""Retrieve only attachment URLs obtained from the selected room's local DB."""
import urllib.request
import urllib.error
from urllib.parse import urlsplit

HOSTS = {'talk.kakaocdn.net', 'dn-talk.kakaocdn.net', 'dn.talk.kakao.com', 'k.kakaocdn.net'}
MAX_BYTES = 50 * 1024 * 1024


def allowed(url):
    try:
        parsed = urlsplit(url)
        return parsed.scheme == 'https' and parsed.hostname in HOSTS and parsed.port in (None, 443) and not parsed.username and not parsed.password
    except ValueError:
        return False


class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, new_url):
        if not allowed(new_url):
            raise ValueError('허용된 카카오 첨부파일 주소가 아닙니다.')
        return super().redirect_request(request, file, code, message, headers, new_url)


def fetch(attachment):
    if not allowed(attachment.get('url', '')):
        raise ValueError('허용된 카카오 첨부파일 주소가 아닙니다.')
    try:
        opener = urllib.request.build_opener(Redirect())
        with opener.open(urllib.request.Request(attachment['url'], headers={'User-Agent': 'KakaoBriefLocal/1.0'}), timeout=25) as response:
            declared = response.headers.get('Content-Length')
            if declared and int(declared) > MAX_BYTES:
                raise ValueError('50MB를 초과하는 첨부파일은 카카오톡에서 열어 주세요.')
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError('50MB를 초과하는 첨부파일은 카카오톡에서 열어 주세요.')
        mime = 'application/octet-stream'
        if attachment.get('kind') == 'photo':
            if body.startswith(b'\xff\xd8\xff'):
                mime = 'image/jpeg'
            elif body.startswith(b'\x89PNG\r\n\x1a\n'):
                mime = 'image/png'
            elif body[:6] in (b'GIF87a', b'GIF89a'):
                mime = 'image/gif'
            elif body.startswith(b'RIFF') and body[8:12] == b'WEBP':
                mime = 'image/webp'
            else:
                raise ValueError('이 이미지 형식은 미리보기를 지원하지 않습니다.')
        return body, mime
    except urllib.error.HTTPError:
        raise ValueError('첨부파일의 다운로드 기간이 만료되었거나 접근할 수 없습니다.') from None
    except (OSError, TimeoutError):
        raise ValueError('첨부파일을 가져오지 못했습니다. 네트워크 상태를 확인해 주세요.') from None
