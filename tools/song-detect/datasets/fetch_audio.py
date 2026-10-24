"""NAS 파일 API로 영상을 읽어 16kHz mono wav만 data/vod/legacy/ 에 뽑는다 (프로토타입 전용, 읽기만 한다)."""
import json, re, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path

API = "http://192.168.0.10:5080/api/files"
OUT = Path("data/vod/legacy")
q = lambda p: urllib.parse.quote(p, safe="")

items = json.load(urllib.request.urlopen(f"{API}/ls?path={q('/app/chzzk')}"))["items"]
wants = sys.argv[1:] or ["토키노 메리"]
for it in sorted(items, key=lambda i: i["name"]):
    want = next((w for w in wants if w in it["name"]), None)
    if not want or it["locked"]:
        continue
    date = re.search(r"\d{4}-\d\d-\d\d", it["name"]).group()
    # 토키노 메리는 기존 이름(날짜만)을 유지하고, 다른 스트리머는 날짜_이름 으로 구분한다
    wav = OUT / (date + ".wav" if want == "토키노 메리" else f"{date}_{want.split()[-1]}.wav")
    if wav.exists():
        continue
    print("extract", it["name"], flush=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f"{API}/download?path={q(it['path'])}",
                    "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)
