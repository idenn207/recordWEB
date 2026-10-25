"""블라인드 검토용 클립 생성. KEEP 구간(1차 가공: 앞뒤 pad초)을 섞어 B01.. 로 저장하고, 정답 키는 key.json 에 따로 둔다.
검토자는 data/review/blind/B*.mp4 만 보고 data/review/blind/review.csv 의 verdict 칸을 채운다. (live / not_song / boundary)
사용: python blind.py 2026-10-19 2026-10-20 ... [--pad=10]"""
import csv, json, random, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 핵심 모듈(scene, vod...)은 상위 폴더
from scene import url_of

API = "http://192.168.0.10:5080/api/files"
D = Path("data/review")
q = lambda p: urllib.parse.quote(p, safe="")
pad = next((float(a[6:]) for a in sys.argv if a.startswith("--pad=")), 10.0)
# 인자: "날짜|파일명에 들어갈 이름|segments.json 경로" (여러 개). 예: "2026-10-06|하나코 나나|cache/exp/2026-10-06_나나.segments.json"
specs = [a.split("|") for a in sys.argv[1:] if not a.startswith("--")]
outdir = next((a[6:] for a in sys.argv if a.startswith("--out=")), "blind")

pool = []
for d, who, segf in specs:
    url = url_of(d, who)                                  # 로컬 다시보기(data/vod/legacy) 우선, 없으면 NAS
    for s in json.loads(Path(segf).read_text(encoding="utf8")):
        if s["keep"]:
            pool.append(dict(date=d, url=url, **s))
random.Random(7).shuffle(pool)

out = D / outdir
out.mkdir(exist_ok=True)
key = {}
for n, c in enumerate(pool, 1):
    bid = f"N{n:02d}"
    a, b = max(0, c["start"] - pad), c["end"] + pad
    key[bid] = dict(date=c["date"], start=c["start"], end=c["end"], clip_start=a, clip_end=b, cover=c["cover"], vocal=c["vocal"])
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-i", c["url"], "-t", str(b - a),
                    "-vf", "scale=-2:360", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
                    "-c:a", "aac", "-b:a", "128k", "-map_metadata", "-1", str(out / f"{bid}.mp4")], check=True)
    print(bid, f"{b - a:.0f}s", flush=True)
(out / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf8")
with open(out / "review.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["id", "verdict(live/not_song/boundary)", "memo"])
    for bid in key:
        w.writerow([bid, "", ""])
