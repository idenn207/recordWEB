"""신규 표본(data/vods10.json)의 장면 게이트 + 라우팅. scene_dataset.py 와 달리 기준 프레임을 '사용자가 라이브로 승인한 구간'(blind5 V11~V16 V21 V22)에서만 만든다
(재생목록 길이 짝짓기는 대기 화면이 섞여 오염됨 - HANDOFF 5번). 승인 구간이 없는 채널(히나 등)은 route.tier 가 review 로 보낸다.
사용: python scene_new.py <입력 segments 폴더(exp10r)> <출력 폴더(exp10s)>"""
import json, sys
from pathlib import Path
import numpy as np
from scene import thumbs, dist
from route import tier
from vod import url144
from scene_multi import classify, pools

# 사용자 라벨: blind5 id -> (클립 내 상대초 시작, 끝). 절대 시각 = key.json 의 clip_start + 상대초
APPROVED = {"V11": (24, 245), "V12": (20, 245), "V13": (20, 230), "V14": (20, 187), "V15": (19, 256), "V16": (23, 267), "V21": (97, 313), "V22": (18, 150)}
IN, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
key = json.load(open("data/blind5/key.json", encoding="utf8"))
vods = json.load(open("data/vods10.json", encoding="utf8"))
by_name = {}
for b, (a, e) in APPROVED.items():
    k = key[b]
    f = thumbs(url144(k["videoNo"]), k["clip_start"] + a, k["clip_start"] + e)
    if len(f):
        by_name.setdefault(k["name"], []).append(f[np.linspace(0, len(f) - 1, min(60, len(f))).astype(int)])
KF = dict(np.load("data/blind5/_kf.npz"))   # blind5 키프레임(승인=live, 나머지=neg). V07/V21 은 읽히지 않아 빠짐
LIVEP, NEGP = pools(KF, {v: "live" if v in APPROVED else "neg" for v in KF}, {v: "" for v in KF}, None)
refs = {n: np.concatenate(r) for n, r in by_name.items()}
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
