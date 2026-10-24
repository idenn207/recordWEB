"""신규 표본(data/vods10.json)의 장면 게이트 + 라우팅. scene_dataset.py 와 달리 기준 프레임을 '사용자가 라이브로 승인한 구간'(data/scene_pool.npz: blind5+blind6 라벨 클립)에서만 만든다
(재생목록 길이 짝짓기는 대기 화면이 섞여 오염됨 - HANDOFF 5번). 승인 구간이 없는 채널(히나 등)은 route.tier 가 review 로 보낸다.
사용: python scene_new.py <입력 segments 폴더(exp10r)> <출력 폴더(exp10s)>"""
import json, sys
from pathlib import Path
import numpy as np
from scene import thumbs, dist
import scene_pool
from route import tier
from vod import url144
from scene_multi import classify

IN, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
vods = json.load(open("data/vods10.json", encoding="utf8"))
meta, F = scene_pool.pool()   # 기준 풀(data/scene_pool.npz): 승인 라이브 + 오탐 키프레임. 새 승인 클립은 `python scene_pool.py build` 로 추가
LIVEP, NEGP = (scene_pool.cat(meta, F, lambda m: True)[g] for g in ("live", "neg"))
refs = {n: scene_pool.cat(meta, F, lambda m, n=n: m["name"] == n)["live"] for n in {m["name"] for m in meta if m["live"]}}
print({n: len(r) for n, r in refs.items()}, flush=True)
for v in vods:
    f = IN / f"{v['videoNo']}.segments.json"
    if not f.exists():
        continue
    R, out = refs.get(v["name"]), []
    for s in json.load(open(f, encoding="utf8")):
        if not s["keep"]:
            continue
        fr = thumbs(url144(v["videoNo"]), s["start"], s["end"])
        s["multi"], s["multi_why"] = classify(fr, LIVEP, NEGP)   # 채널 기준 없이도 같이 보기/대기 화면은 drop
        if R is not None:
            s["scene"] = dist(fr, R)
        s["tier"], s["tier_why"] = tier(s, R is not None)
        out.append(s)
    json.dump(out, open(OUT / f"{v['videoNo']}.segments.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print(v["date"], v["name"], v["videoNo"], "기준" if R is not None else "기준 없음", {t: sum(s["tier"] == t for s in out) for t in ("auto", "review", "drop")}, flush=True)
