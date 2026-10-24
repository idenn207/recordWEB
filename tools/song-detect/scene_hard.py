"""어려운 표본(data/vods11.json 전체: 게임/노래/잡담 방송)의 장면 게이트 + 라우팅. 탐지 입력은 방송마다 exp11r > exp10r > exp8r 중 처음 있는 것(읽기만, 덮어쓰지 않음).
scene_new.py 와 같은 기준(blind5 승인 클립 + scene_multi 풀)을 쓰되 장면 특징(tstd, 검은 띠)도 남겨 hard_report.py 가 쓴다. exp9/exp10s 와 달리 방송 앞 5분 규칙이 항상 적용된다.
사용: python scene_hard.py <출력 폴더(exp11s)>"""
import json, sys
from pathlib import Path
import numpy as np
from scene import thumbs, dist
from route import tier, known_neg
from vod import url144
from scene_multi import classify, pools, feats

APPROVED = {"V11": (24, 245), "V12": (20, 245), "V13": (20, 230), "V14": (20, 187), "V15": (19, 256), "V16": (23, 267), "V21": (97, 313), "V22": (18, 150)}
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
key = json.load(open("data/review/blind5/key.json", encoding="utf8"))
by_name = {}
for b, (a, e) in APPROVED.items():
    k = key[b]
    f = thumbs(url144(k["videoNo"]), k["clip_start"] + a, k["clip_start"] + e)
    if len(f):
        by_name.setdefault(k["name"], []).append(f[np.linspace(0, len(f) - 1, min(60, len(f))).astype(int)])
refs = {n: np.concatenate(r) for n, r in by_name.items()}
KF = dict(np.load("cache/blind5_kf.npz"))
LIVEP, NEGP = pools(KF, {v: "live" if v in APPROVED else "neg" for v in KF}, {v: "" for v in KF}, None)
for v in json.load(open("data/vods11.json", encoding="utf8")):
    f = next((Path(f"cache/{d}/{v['videoNo']}.segments.json") for d in ("exp11r", "exp10r", "exp8r") if Path(f"cache/{d}/{v['videoNo']}.segments.json").exists()), None)
    if f is None or (OUT / f"{v['videoNo']}.segments.json").exists():   # 이미 처리한 방송은 건너뜀(지우고 다시 돌리면 재계산)
        continue
    R, out = refs.get(v["name"]), []
    for s in json.load(open(f, encoding="utf8")):
        if not s["keep"]:
            continue
        fr = thumbs(url144(v["videoNo"]), s["start"], s["end"])
        s["multi"], s["multi_why"] = classify(fr, LIVEP, NEGP)
        s["tstd"], s["blk"] = feats(fr) if len(fr) >= 3 else (None, None)
        if R is not None:
            s["scene"] = dist(fr, R)
        s["tier"], s["tier_why"] = tier(s, R is not None)
        known_neg(v["videoNo"], s)
        s["src"] = f.parent.name
        out.append(s)
    json.dump(out, open(OUT / f"{v['videoNo']}.segments.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print(v["date"], v["name"], v["videoNo"], v["kind"], {t: sum(s["tier"] == t for s in out) for t in ("auto", "review", "drop")}, flush=True)
