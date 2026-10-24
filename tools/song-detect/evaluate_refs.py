"""정답 클립 위치(data/refs.json)와 탐지 결과를 비교한다. 사용: python evaluate_refs.py [segments 폴더=data/exp]"""
import json, sys
from pathlib import Path
D = Path(sys.argv[1] if len(sys.argv) > 1 else "data/exp")
refs = [r for r in json.load(open("data/refs.json", encoding="utf8")) if not r["title"].endswith("1절")]  # 1절만 부른 곡은 클립 대상 아님(사용자 확인)
hms = lambda t: f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}"
ov = lambda a, b, c, d: max(0, min(b, d) - max(a, c))
# 사용자가 추가로 라이브라고 확인한 클립(정답표 밖): 10-16 N12 N15 N10 N31, 10-06 N18 (시각 범위는 클립 파일명 기준)
H = lambda h, m: h * 3600 + m * 60
EXTRA = {"2026-10-16": [(H(6, 13), H(6, 17)), (H(6, 23), H(6, 27)), (H(6, 28), H(6, 32)), (H(6, 32), H(6, 36))], "2026-10-06": [(H(8, 3), H(8, 7))]}
for date in ("2026-10-06", "2026-10-16"):
    S = [s for s in json.load(open(D / f"{date}_나나.segments.json", encoding="utf8")) if s["keep"]]
    R = sorted([r for r in refs if r["date"] == date], key=lambda r: r["start"])
    print(f"== {date}: 정답 {len(R)}곡 / 탐지 KEEP {len(S)}")
    hit = set()
    for r in R:
        c = [(i, s) for i, s in enumerate(S) if ov(s["start"], s["end"], r["start"], r["end"]) > 0.3 * r["dur"]]
        if not c: print(f"  MISS {hms(r['start'])}-{hms(r['end'])} {r['dur']:.0f}s {r['title'][:30]}"); continue
        for i, s in c: hit.add(i)
        s = c[0][1]; many = f" (탐지 1개가 정답 {sum(1 for q in R if ov(s['start'], s['end'], q['start'], q['end']) > 0.3 * q['dur'])}곡 덮음)" if len(c) == 1 else ""
        print(f"  HIT  {hms(r['start'])} {r['dur']:4.0f}s  시작 {s['start'] - r['start']:+5.0f}s 끝 {s['end'] - r['end']:+5.0f}s {r['title'][:28]}{many}" if len(c) == 1 else f"  SPLIT {hms(r['start'])} {r['dur']:.0f}s 탐지 {len(c)}조각")
    for i, s in enumerate(S):
        if i in hit: continue
        ex = any(ov(s["start"], s["end"], a, b) > 0.5 * s["len"] for a, b in EXTRA.get(date, []))
        print(f"  {'EXTRA-LIVE' if ex else 'FP'} {hms(s['start'])}-{hms(s['end'])} {s['len']:.0f}s")
