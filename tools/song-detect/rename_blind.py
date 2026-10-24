"""블라인드 클립을 원본에서 찾기 쉬운 이름으로 바꾼다: YYMMDD_HHMMSS-HHMMSS__<ID>.mp4  (시각은 녹화 파일 기준, 클립 파일 전체 범위)"""
import csv, json, sys
from pathlib import Path

D = Path(sys.argv[1] if len(sys.argv) > 1 else "data/blind2")
K = json.loads((D / "key.json").read_text(encoding="utf8"))
hm = lambda t: f"{int(t // 3600):02d}{int(t % 3600 // 60):02d}{int(t % 60):02d}"
rows = []
for bid, c in K.items():
    new = f"{c['date'][2:].replace('-', '')}_{hm(c['clip_start'])}-{hm(c['clip_end'])}__{bid}.mp4"
    old = next((p for p in D.glob("*.mp4") if p.stem == bid or p.stem.endswith("__" + bid)), None)
    if old and old.name != new:
        old.rename(D / new)
    rows.append((c["date"], hm(c["clip_start"]), hm(c["clip_end"]), bid, new))
rows.sort()
print(*(r[4] for r in rows), sep="\n")
