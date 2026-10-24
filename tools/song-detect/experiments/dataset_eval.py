"""다시보기 데이터셋 약한 라벨 평가: 재생목록 클립 길이(data/vods.json 의 clips)와 탐지 구간 길이를 +-15% 로 일대일 매칭한다.
위치가 아니라 길이로만 맞추므로 근거가 약하다(오매칭 가능). 재생목록은 라이브의 일부(하한)라서 '매칭 안 된 탐지'는 오탐이 아니라 '검토 필요'다.
사용: python dataset_eval.py <segments 폴더>   (파일명 <videoNo>.segments.json, route.py 를 거쳤으면 등급도 센다)"""
import json, sys
from collections import defaultdict
from pathlib import Path

D = Path(sys.argv[1])
groups = defaultdict(lambda: dict(clips=[], segs=[], vods=[]))
for v in json.load(open("data/vods.json", encoding="utf8")):
    f = D / f"{v['videoNo']}.segments.json"
    g = groups[(v["date"], v["name"])]
    g["vods"].append(v["videoNo"])
    if f.exists():
        g["segs"] += [s for s in json.load(open(f, encoding="utf8")) if s["keep"] or s.get("tier") in ("auto", "review")]
    g["clips"] = v["clips"]                              # 같은 날짜의 클립 목록은 VOD 마다 같다
tot = defaultdict(int)
print(f"{'날짜':10} {'스트리머':8} {'클립':>3} {'탐지':>4} {'매칭':>4} {'매칭안됨':>6} | 등급별 매칭/전체 (auto, review)")
for (date, name), g in sorted(groups.items()):
    S = [s for s in g["segs"] if s.get("tier", "auto") != "drop"]
    used, match = set(), []
    for c in sorted(g["clips"]):
        b = min(((abs(s["len"] - c) / c, i) for i, s in enumerate(S) if i not in used), default=None)
        if b and b[0] <= 0.15:
            used.add(b[1])
            match.append(c)
    t = defaultdict(lambda: [0, 0])
    for i, s in enumerate(S):
        k = s.get("tier", "auto")
        t[k][1] += 1
        t[k][0] += i in used
    print(f"{date} {name:8} {len(g['clips']):3} {len(S):4} {len(match):4} {len(S) - len(match):6} | " + ", ".join(f"{k} {a}/{b}" for k, (a, b) in sorted(t.items())))
    tot["clips"] += len(g["clips"]); tot["det"] += len(S); tot["match"] += len(match)
    for k, (a, b) in t.items():
        tot[k + "_m"] += a; tot[k + "_n"] += b
print(f"합계: 클립 {tot['clips']}, 탐지 {tot['det']}, 매칭 {tot['match']}(재생목록 재현율 {tot['match'] / max(1, tot['clips']) * 100:.0f}%), "
      f"auto {tot['auto_m']}/{tot['auto_n']} 매칭, review {tot['review_m']}/{tot['review_n']} 매칭")
