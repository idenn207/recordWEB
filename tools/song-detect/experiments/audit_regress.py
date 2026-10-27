"""회귀 감사 2단계(읽기 전용): cache/audit/master.json 에서 기준 집합(사용자가 승인/교정한 곡)을 골라 v3 -> v4 변화표와 이탈 판정을 만든다.
출력: data/review/blind9/audit/regression.json, 표는 stdout(마크다운). 이탈 기준: 시작/끝 이동 > 2초, 클립 길이 변화 > 3초, 곡 사라짐, 등급 하락, 병합/분할(이웃과 겹침)."""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
M = json.load(open(ROOT / "cache/audit/master.json", encoding="utf8"))
RANK = {"auto": 3, "review": 2, "optional": 1, "drop": 0, None: -1}
by = {}
for r in M: by.setdefault(r["vid"], []).append(r)

def ovl(a0, a1, b0, b1): return max(0.0, min(a1, b1) - max(a0, b0))

def find(vid, s, e, key="v3", thr=0.5):
    best, bo = None, thr
    for r in by.get(vid, []):
        o = ovl(r[key]["song_s"], r[key]["song_e"], s, e) / max(1e-9, min(e - s, r[key]["song_e"] - r[key]["song_s"]))
        if o > bo: best, bo = r, o
    return best

import copy, os
os.chdir(ROOT)
import route
from scene_multi import P as MP
_SC = {}
def _scene(r, old):
    k = (r["vid"], old)
    if k not in _SC:
        f = ROOT / ("cache/pre_v4" if old and r["nas"] else "out") / r["vid"] / "4_scene.json"
        _SC[k] = json.load(open(f, encoding="utf8")) if f.exists() else None
    return _SC[k]

def sim3(r):
    """v3 코드 재현: v3 경계 + 영상 움직임 임계 40 + 예전 4_scene + 현재 승인 목록(known_pos/known_neg). 승인 곡은 v3 경계 = 승인 경계라 auto 가 기준 상태."""
    sc = _scene(r, True)
    if not sc or r["k"] >= len(sc["segs"]): return None
    g = copy.deepcopy(sc["segs"][r["k"]]); v3 = r["v3"]
    g["start"], g["end"], g["len"] = v3["song_s"], v3["song_e"], v3["song_e"] - v3["song_s"]
    old = MP["motion"]; MP["motion"] = 40
    try:
        g["tier"], g["tier_why"] = route.tier(g, sc["has_refs"])
    finally:
        MP["motion"] = old
    route.known_pos(r["vid"], g); route.known_neg(r["vid"], g)
    return g["tier"], g["tier_why"]

def tier3(r):
    t = sim3(r)
    return t[0] if t else (r.get("tier3") or [None])[0]
def tier4(r):
    t = r.get("tier4") or r.get("tier4_sim")
    return t[0] if t else None

def cause(r):
    """원인 규칙: v3->v4 시작/끝 이동에 대해 only(그 규칙만 켬) 이 이동의 절반 이상을 설명하는 규칙들."""
    out = []
    d = [r["v4"]["song_s"] - r["v3"]["song_s"], r["v4"]["song_e"] - r["v3"]["song_e"]]
    for side, nm in ((0, "시작"), (1, "끝")):
        if abs(d[side]) <= 0.05: continue
        rs = [k for k, v in r.get("only", {}).items() if abs(v[side]) > 0.05 and abs(v[side]) >= 0.5 * abs(d[side]) and v[side] * d[side] > 0]
        rs2 = [k for k, v in r.get("loo", {}).items() if abs(v[side]) > 0.05]    # 끄면 달라지는 규칙(상호작용 포함)
        out.append(f"{nm}{d[side]:+.1f}:" + ("+".join(rs) if rs else "상호작용") + ("(loo " + "+".join(rs2) + ")" if rs2 and set(rs2) != set(rs) else ""))
    return " ".join(out)

def row(ref, r, truth=None):
    """ref: 기준 항목 dict(id, kind, ...), r: master 행 또는 None, truth: (시작정답, 끝정답) 절대초 또는 None"""
    if r is None:
        return dict(**ref, found=False, flags=["매칭 실패"])
    v3, v4 = r["v3"], r["v4"]
    d = dict(s=v4["song_s"] - v3["song_s"], e=v4["song_e"] - v3["song_e"],
             clip=(v4["clip_e"] - v4["clip_s"]) - (v3["clip_e"] - v3["clip_s"]), song=(v4["song_e"] - v4["song_s"]) - (v3["song_e"] - v3["song_s"]))
    t3, t4 = tier3(r), tier4(r)
    fl = []
    if abs(d["s"]) > 2: fl.append("시작이동")
    if abs(d["e"]) > 2: fl.append("끝이동")
    if abs(d["clip"]) > 3: fl.append("클립길이")
    if t4 == "drop" and t3 != "drop": fl.append("곡사라짐")
    elif RANK[t4] < RANK[t3]: fl.append("등급하락")
    # 병합/분할: v4 곡이 이웃 후보와 겹치는가(v3 에는 없던 겹침)
    for q in by[r["vid"]]:
        if q is r: continue
        if ovl(v4["song_s"], v4["song_e"], q["v4"]["song_s"], q["v4"]["song_e"]) > 1 and ovl(v3["song_s"], v3["song_e"], q["v3"]["song_s"], q["v3"]["song_e"]) <= 1:
            fl.append(f"병합/겹침:{q['v4']['song_s']:.0f}"); break
    out = dict(**ref, found=True, vid=r["vid"], v3=dict(s=v3["song_s"], e=v3["song_e"], clip=v3["clip_e"] - v3["clip_s"], tier=t3, why=(sim3(r) or [0,""])[1], card_tier=(r.get("tier3") or [None])[0]),
               v4=dict(s=v4["song_s"], e=v4["song_e"], clip=v4["clip_e"] - v4["clip_s"], tier=t4, why=(r.get("tier4") or r.get("tier4_sim"))[1]), d=d, cause=cause(r), flags=fl, refine=r["refine"])
    if truth:
        ts, te = truth
        if ts is not None: out["err_s"] = [v3["song_s"] - ts, v4["song_s"] - ts]
        if te is not None: out["err_e"] = [v3["song_e"] - te, v4["song_e"] - te]
        for k in ("err_s", "err_e"):
            if k in out and abs(out[k][1]) > abs(out[k][0]) + 0.5: out["flags"].append("정답에서 멀어짐" + k[-1])
    return out

def sets():
    R = []
    # R1 blind9 (L 기준, B 참고)
    T = json.load(open(ROOT / "data/review/blind9/boundary_truth.json", encoding="utf8"))
    seen = set()
    for x in T:
        if x["lab"] not in ("L", "B"): continue
        vid = x["slug"].split("_", 2)[2]
        r = find(vid, x["base_start"], x["base_end"], "v3")
        key = (vid, round(x["base_start"] / 8))
        if (vid, r["k"] if r else None) in seen: continue
        seen.add((vid, r["k"] if r else None))
        ts = x.get("start_true_abs"); te = x.get("end_true_abs")
        R.append((dict(set="blind9-" + x["lab"], id=f"#{x['idx']} {vid}", memo=x["memo"], start_issue=x["start_issue"], end_issue=x["end_issue"], approx=x["approx"]), r, (ts, te) if (ts or te) else None))
    # R2 blind5 USER (VOD)
    from snap import USER, START6
    k5 = json.load(open(ROOT / "data/review/blind5/key.json", encoding="utf8"))
    for v, (a, b) in USER.items():
        k = k5[v]; vid = str(k["videoNo"]); c = k["clip_start"]
        R.append((dict(set="blind5-user", id=f"{v} {vid}"), find(vid, k["start"], k["end"], "v3"), (c + a, c + b)))
    k6 = json.load(open(ROOT / "data/review/blind6/key.json", encoding="utf8"))
    for v, a in START6.items():
        k = k6[v]; vid = str(k["videoNo"])
        R.append((dict(set="blind6-start", id=f"{v} {vid}"), find(vid, k["start"], k["end"], "v3"), (k["clip_start"] + a, None)))
    # blind8 Q2~Q4
    for q, vid, c0, a, b in (("Q2", "15837908", 2443, 57, 268), ("Q3", "15837908", 4342, 59, 288), ("Q4", "15837908", 3403, 59, 265)):
        ts, te = c0 - 60 + a, c0 - 60 + b
        R.append((dict(set="blind8-user", id=f"{q} {vid}"), find(vid, ts, te, "v3"), (ts, te)))
    # 나나 refs / 재생목록 위치 정답 (approved)
    A = json.load(open(ROOT / "data/approved.json", encoding="utf8"))
    for x in A:
        src = x["src"]
        if x.get("boundary_ok") is False: continue
        vid = str(x["videoNo"])
        if src.startswith("재생목록 위치 정답"):
            R.append((dict(set="playlist-" + ("nas" if "NAS" in src else "vod"), id=f"{vid}@{x['start']:.0f}"), find(vid, x["start"], x["end"], "v3"), (x["start"], x["end"])))
        else:
            R.append((dict(set="approved-" + src.split()[0] + ("-L" if x.get("boundary_ok") else ""), id=f"{vid}@{x['start']:.0f}"), find(vid, x["start"], x["end"], "v3"), None))
    return R

def main():
    rows = [row(ref, r, t) for ref, r, t in sets()]
    json.dump(rows, open(ROOT / "data/review/blind9/audit/regression.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
    from collections import Counter
    print(Counter((x["set"], bool(x["flags"])) for x in rows))
    return rows

if __name__ == "__main__":
    main()
