"""정답 클립 위치(data/refs.json, 나나)와 비교한 경계 오차 통계. 곡 하나가 탐지 하나로 일대일 대응한 경우만 센다.
사용: python boundary_stats.py <segments 폴더> [...]   (폴더 안에 <날짜>_나나.segments.json)"""
import json, sys
from pathlib import Path
import numpy as np

ov = lambda a, b, c, d: max(0, min(b, d) - max(a, c))
refs = [r for r in json.load(open("data/refs.json", encoding="utf8")) if not r["title"].endswith("1절")]


def stats(d, date):
    S = [s for s in json.load(open(Path(d) / f"{date}_나나.segments.json", encoding="utf8")) if s["keep"]]
    R = [r for r in refs if r["date"] == date]
    es, ee = [], []
    for r in R:
        c = [s for s in S if ov(s["start"], s["end"], r["start"], r["end"]) > 0.3 * r["dur"]]
        if len(c) == 1 and sum(1 for q in R if ov(c[0]["start"], c[0]["end"], q["start"], q["end"]) > 0.3 * q["dur"]) == 1:
            es.append(c[0]["start"] - r["start"])
            ee.append(c[0]["end"] - r["end"])
    return np.array(es), np.array(ee)


def line(name, x):
    return f"{name}: 중앙값 {np.median(x):+.1f}s  |오차|<=1s {np.mean(abs(x) <= 1) * 100:3.0f}%  <=3s {np.mean(abs(x) <= 3) * 100:3.0f}%  <=10s {np.mean(abs(x) <= 10) * 100:3.0f}%"


for d in sys.argv[1:]:
    for date in ("2026-10-06", "2026-10-16"):
        es, ee = stats(d, date)
        print(f"[{d}] {date} 곡 {len(es)}개  ", line("시작", es), "|", line("끝", ee))
