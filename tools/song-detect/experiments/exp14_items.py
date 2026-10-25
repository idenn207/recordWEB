"""끝 규칙 평가용 표본 모음: (이름, wav, 탐지전 s, e, 정답 s, 정답 e). 정답 없으면 None. snap.py evaltable/evalnana 와 같은 출처."""
import json
from snap import USER, START6
J = lambda f: json.load(open(f, encoding="utf8"))
ov = lambda a, b, c, d: max(0, min(b, d) - max(a, c))


def items():
    R = []
    for sname, tab in (("blind5", {v: (a, b) for v, (a, b) in USER.items()}), ("blind6", {v: (a, None) for v, a in START6.items()})):
        k = J("data/review/%s/key.json" % sname)
        for v, (a, b) in tab.items():
            c = k[v]["clip_start"]
            R.append((sname + v, "data/vod/%s.wav" % k[v]["videoNo"], k[v]["start"], k[v]["end"], c + a, c + b if b else None))
    refs = [r for r in J("data/refs.json") if not r["title"].endswith("1절")]
    for date in ("2026-10-06", "2026-10-16"):
        S = [g for g in J("cache/exp7b/%s_나나.segments.json" % date) if g["keep"]]
        rs = [r for r in refs if r["date"] == date]
        for r in rs:
            c = [g for g in S if ov(g["start"], g["end"], r["start"], r["end"]) > 0.3 * r["dur"]]
            if len(c) == 1 and sum(ov(c[0]["start"], c[0]["end"], q["start"], q["end"]) > 0.3 * q["dur"] for q in rs) == 1:
                R.append(("나나" + date[5:] + r["title"][-8:], "data/vod/legacy/%s_나나.wav" % date, c[0]["start"], c[0]["end"], r["start"], r["end"]))
    Q = {2443: (2440.0, 2651.0), 4342: (4341.0, 4630.0), 3403: (3402.0, 3608.0)}   # 사용자 확인(파일 시각 + 후보시작-60)
    for g in J("out/15837908/3_final.json"):
        if g["keep"]:
            q = Q.get(round(g["start1"]), Q.get(round(g["start"])))
            R.append(("토아%d" % g["start1"], "data/vod/15837908.wav", g["start1"], g["end1"], q[0] if q else None, q[1] if q else None))
    for name, vid, rf in (("마시로", 15827672, "data/refs_마시로.json"), ("후야", 15761307, "data/refs_후야.json")):
        S = [g for g in J("out/%d/3_final.json" % vid) if g["keep"]]
        for r in J(rf):
            c = [g for g in S if ov(g["start1"], g["end1"], r["start"], r["end"]) > 0.3 * (r["end"] - r["start"])]
            if len(c) == 1:
                R.append((name + str(int(r["start"])), "data/vod/%d.wav" % vid, c[0]["start1"], c[0]["end1"], r["start"], r["end"]))
    return R
