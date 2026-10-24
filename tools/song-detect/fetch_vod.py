"""치지직 다시보기(공개)의 720p 프로그레시브 MP4 를 Range 요청으로 병렬 다운로드한다 (연결당 ~0.7MB/s 라 나눠 받는다).
결과: data/_vod/<날짜>_<이름>.mp4 와 data/<날짜>_<이름>.wav(16kHz mono).
사용: python fetch_vod.py <videoNo> <날짜> <이름> [병렬수=24]"""
import json, re, subprocess, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

vid, date, name = sys.argv[1:4]
n = int(sys.argv[4]) if len(sys.argv) > 4 else 24
UA = {"User-Agent": "Mozilla/5.0"}
D = Path("data/_vod")
D.mkdir(exist_ok=True)
c = json.load(urllib.request.urlopen(urllib.request.Request(f"https://api.chzzk.naver.com/service/v3/videos/{vid}", headers=UA)))["content"]
mpd = urllib.request.urlopen(urllib.request.Request(
    f"https://apis.naver.com/neonplayer/vodplay/v2/playback/{c['videoId']}?key={c['inKey']}",
    headers={**UA, "Accept": "application/dash+xml"}), timeout=20).read().decode()
url = re.search(r'<Representation id="PD_720P[^"]*".*?<BaseURL>([^<]+)</BaseURL>', mpd, re.S).group(1).replace("&amp;", "&")


def get(a, b):
    for _ in range(5):                                   # 일시적 끊김은 재시도
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers={**UA, "Range": f"bytes={a}-{b}"}), timeout=60).read()
        except Exception:
            pass
    raise RuntimeError(f"range {a}-{b} 실패")


size = int(urllib.request.urlopen(urllib.request.Request(url, headers={**UA, "Range": "bytes=0-0"})).headers["Content-Range"].split("/")[1])
out = D / f"{date}_{name}.mp4"
CH = 8 << 20
spans = [(a, min(a + CH, size) - 1) for a in range(0, size, CH)]
with open(out, "wb") as f:
    f.truncate(size)


def grab(s):
    data = get(*s)
    with open(out, "r+b") as f:                          # 조각마다 제 위치에 쓴다
        f.seek(s[0])
        f.write(data)


with ThreadPoolExecutor(n) as ex:
    for i, _ in enumerate(ex.map(grab, spans)):
        if i % 50 == 0:
            print(f"{i}/{len(spans)}", flush=True)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(out), "-vn", "-ac", "1", "-ar", "16000", f"data/{date}_{name}.wav"], check=True)
print("done", out, f"{size / 1e9:.2f}GB", f"{c['duration'] / 3600:.2f}h")
