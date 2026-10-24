"""<날짜>.segments.json 의 KEEP 구간을 NAS 원본에서 재인코딩 없이(-c copy) data/clips/ 로 자른다. 원본은 읽기만 한다.
사용: python cut_clips.py 2026-10-18 [pad초=10]"""
import json, re, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path

API = "http://192.168.0.10:5080/api/files"
D = Path(__file__).parent / "data"
q = lambda p: urllib.parse.quote(p, safe="")

date = sys.argv[1]
pad = float(sys.argv[2]) if len(sys.argv) > 2 else 10
items = json.load(urllib.request.urlopen(f"{API}/ls?path={q('/app/chzzk')}"))["items"]
src = next(i for i in items if date in i["name"] and "토키노 메리" in i["name"] and not i["locked"])
segs = [s for s in json.loads((D / f"{date}.segments.json").read_text(encoding="utf8")) if s["keep"]]
(D / "clips").mkdir(exist_ok=True)
for n, s in enumerate(segs, 1):
    a, b = max(0, s["start"] - pad), s["end"] + pad
    out = D / "clips" / f"{date}_{n}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-i", f"{API}/download?path={q(src['path'])}",
                    "-t", str(b - a), "-c", "copy", str(out)], check=True)
    print(out.name, f"{a:.0f}-{b:.0f}s", f"{out.stat().st_size / 1e6:.0f}MB", flush=True)
