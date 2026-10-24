"""치지직 다시보기(공개)를 Range 요청으로 병렬 다운로드한다 (연결당 ~0.7MB/s 라 8MB 조각으로 나눠 받는다).
결과: data/vod/<videoNo>.wav (오디오 전용 128kbps m4a -> 16kHz mono, 탐지용)와 data/vod/<videoNo>.mp4 (144p 영상, 장면 썸네일용).
64kbps 인 144p 영상의 오디오로는 탐지 결과가 달라져서(후보 12 -> 13) 오디오는 따로 받는다.
사용: python fetch_vod.py <videoNo> [병렬수=24]"""
import json, re, subprocess, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

vid = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 24
UA = {"User-Agent": "Mozilla/5.0"}
D = Path("data/vod")
D.mkdir(parents=True, exist_ok=True)
c = json.load(urllib.request.urlopen(urllib.request.Request(f"https://api.chzzk.naver.com/service/v3/videos/{vid}", headers=UA)))["content"]
mpd = urllib.request.urlopen(urllib.request.Request(
    f"https://apis.naver.com/neonplayer/vodplay/v2/playback/{c['videoId']}?key={c['inKey']}",
    headers={**UA, "Accept": "application/dash+xml"}), timeout=20).read().decode()
unesc = lambda u: u.replace("&amp;", "&")
video_url = unesc(re.search(r'<Representation id="PD_144P[^"]*".*?<BaseURL>([^<]+)</BaseURL>', mpd, re.S).group(1))
# 오디오 전용 Representation(mimeType audio/mp4) 중 비트레이트가 가장 높은 것
auds = [(int(m.group(2)), unesc(m.group(3))) for m in re.finditer(r'<Representation id="([^"]+)" bandwidth="(\d+)"[^>]*mimeType="audio/mp4".*?<BaseURL>([^<]+)</BaseURL>', mpd, re.S)]
audio_url = max(auds)[1]


def fetch(url, out):
    def get(a, b):
        for _ in range(5):                               # 일시적 끊김은 재시도
            try:
                return urllib.request.urlopen(urllib.request.Request(url, headers={**UA, "Range": f"bytes={a}-{b}"}), timeout=60).read()
            except Exception:
                pass
        raise RuntimeError(f"range {a}-{b} 실패")

    size = int(urllib.request.urlopen(urllib.request.Request(url, headers={**UA, "Range": "bytes=0-0"})).headers["Content-Range"].split("/")[1])
    CH = 8 << 20
    spans = [(a, min(a + CH, size) - 1) for a in range(0, size, CH)]
    with open(out, "wb") as f:
        f.truncate(size)

    def grab(s):
        data = get(*s)
        with open(out, "r+b") as f:                      # 조각마다 제 위치에 쓴다
            f.seek(s[0])
            f.write(data)

    with ThreadPoolExecutor(n) as ex:
        list(ex.map(grab, spans))
    return size


m4a = D / f"{vid}.m4a"
sz = fetch(audio_url, m4a) + fetch(video_url, D / f"{vid}.mp4")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(m4a), "-vn", "-ac", "1", "-ar", "16000", str(D / f"{vid}.wav")], check=True)
m4a.unlink()
print("done", vid, f"{sz / 1e6:.0f}MB", f"{c['duration'] / 3600:.2f}h")
