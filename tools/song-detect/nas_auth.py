"""NAS 파일 API 로그인 세션(쿠키 rw_session). 비밀번호는 저장하지 않고 환경변수 NAS_USER/NAS_PASS 로만 받아 로그인하고, 받은 세션 토큰만 cache/nas_session.txt 에 둔다(gitignore).
세션이 만료되면(401) 이 파일을 지우고 NAS_USER/NAS_PASS 를 설정해 다시 실행한다. 사용: ffargs(url) 을 ffmpeg 의 -i 앞에, urlopen(url) 을 urllib.request.urlopen 대신."""
import json, os, urllib.request
from pathlib import Path

HOST, F = "http://192.168.0.10:5080", Path(__file__).parent / "cache" / "nas_session.txt"


def cookie():
    if not F.exists():
        r = urllib.request.urlopen(urllib.request.Request(f"{HOST}/api/auth/login", json.dumps({"username": os.environ["NAS_USER"], "password": os.environ["NAS_PASS"]}).encode(), {"Content-Type": "application/json"}), timeout=20)
        F.parent.mkdir(exist_ok=True)
        F.write_text(r.headers.get_all("Set-Cookie")[0].split(";")[0])
    return F.read_text().strip()


def ffargs(url):
    """ffmpeg/ffprobe 입력 앞에 붙일 인자: NAS 주소면 세션 쿠키 헤더, 아니면 빈 목록."""
    return ["-headers", f"Cookie: {cookie()}\r\n"] if str(url).startswith(HOST) else []


def urlopen(url, **kw):
    return urllib.request.urlopen(urllib.request.Request(url, headers={"Cookie": cookie()}), **kw)
