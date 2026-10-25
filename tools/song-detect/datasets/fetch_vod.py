"""치지직 다시보기(공개)의 오디오 전용 스트림(128kbps m4a)을 Range 요청으로 받아 data/vod/<videoNo>.wav (16kHz mono) 로 만든다.
네트워크를 나눠 쓰도록 전체 전송 속도를 제한한다(기본 45MB/s ~ 360Mbps(사용자 회선 500Mbps, 다른 네트워크 작업이 없을 때 한도 해제 허용), 연결 24개(연결당 속도가 낮아 연결 수가 처리량을 정함)). 영상은 받지 않는다 - 장면 확인은 scene.py 가 필요한 구간만 읽는다.
64kbps 인 144p 영상의 오디오로는 탐지 결과가 달라져서(후보 12 -> 13) 오디오 전용 스트림을 쓴다.
사용: python fetch_vod.py <videoNo> [속도 MB/s=45] [연결수=24]"""
import json, re, subprocess, sys, threading, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

vid = sys.argv[1]
RATE = float(sys.argv[2]) * 1e6 if len(sys.argv) > 2 else 45e6      # 바이트/초, 모든 연결의 합
n = int(sys.argv[3]) if len(sys.argv) > 3 else 24
UA = {"User-Agent": "Mozilla/5.0"}
D = Path("data/vod")
D.mkdir(parents=True, exist_ok=True)
c = json.load(urllib.request.urlopen(urllib.request.Request(f"https://api.chzzk.naver.com/service/v3/videos/{vid}", headers=UA)))["content"]
mpd = urllib.request.urlopen(urllib.request.Request(
    f"https://apis.naver.com/neonplayer/vodplay/v2/playback/{c['videoId']}?key={c['inKey']}",
    headers={**UA, "Accept": "application/dash+xml"}), timeout=20).read().decode()
# 오디오 전용 Representation(mimeType audio/mp4) 중 비트레이트가 가장 높은 것
auds = [(int(m.group(2)), m.group(3).replace("&amp;", "&")) for m in re.finditer(
    r'<Representation id="([^"]+)" bandwidth="(\d+)"[^>]*mimeType="audio/mp4".*?<BaseURL>([^<]+)</BaseURL>', mpd, re.S)]
if auds:
    url = max(auds)[1]
else:                                                    # 2026-07 이전 방송은 오디오 전용이 없어 144p 영상(오디오 64kbps)을 받아 오디오만 쓴다 - 기준 128kbps 와 음질이 다르다
    url = re.search(r'<Representation id="PD_144P[^"]*".*?<BaseURL>([^<]+)</BaseURL>', mpd, re.S).group(1).replace("&amp;", "&")
    print("오디오 전용 없음 -> 144p 영상에서 추출", vid, flush=True)

_lock, _next = threading.Lock(), [0.0]


def throttle(nbytes):
    """모든 스레드가 공유하는 속도 제한. 읽기 *전에* 시간표를 예약해서(받고 나서 쉬면 조각마다 순간 최고 속도로 몰린다) 64KB 단위로 고르게 받는다."""
    with _lock:
        now = time.monotonic()
        wait = max(0.0, _next[0] - now)
        _next[0] = max(now, _next[0]) + nbytes / RATE
    time.sleep(wait)


def get(a, b):
    for _ in range(5):                                   # 일시적 끊김은 재시도
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, headers={**UA, "Range": f"bytes={a}-{b}"}), timeout=60)
            buf = bytearray()
            while True:
                throttle(64 << 10)
                piece = r.read(64 << 10)
                if not piece:
                    return bytes(buf)
                buf += piece
        except Exception:
            pass
    raise RuntimeError(f"range {a}-{b} 실패")


size = int(urllib.request.urlopen(urllib.request.Request(url, headers={**UA, "Range": "bytes=0-0"})).headers["Content-Range"].split("/")[1])
m4a = D / f"{vid}.m4a"
CH = 4 << 20
spans = [(a, min(a + CH, size) - 1) for a in range(0, size, CH)]
with open(m4a, "wb") as f:
    f.truncate(size)


def grab(s):
    data = get(*s)
    with open(m4a, "r+b") as f:                          # 조각마다 제 위치에 쓴다
        f.seek(s[0])
        f.write(data)


with ThreadPoolExecutor(n) as ex:
    list(ex.map(grab, spans))
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(m4a), "-vn", "-ac", "1", "-ar", "16000", str(D / f"{vid}.wav")], check=True)
m4a.unlink()
print("done", vid, f"{size / 1e6:.0f}MB", f"{c['duration'] / 3600:.2f}h", flush=True)
