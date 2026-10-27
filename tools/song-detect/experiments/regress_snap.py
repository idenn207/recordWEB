"""snap 규칙(E1 E1b E2 E3 S1 S2) 회귀 점검: out/<방송>/2_refine.json 의 keep 구간 전체에 규칙을 하나씩만 켜서 예전 snap(모두 끔)과 경계가 얼마나 달라지는지 센다.
사용: python experiments/regress_snap.py [-c] [-rE1b ...]   [방송id...]
  -c = 다른 규칙을 다 켠 상태에서 그 규칙을 끈 결과와 비교, 방송id 기본 = out 의 전부, wav 와 cache/detect 점수가 있는 것)
출력: 규칙별 이동 구간 수(1초 초과)와 목록(방송:시작초 시작이동/끝이동). 정답이 없는 방송은 '움직인 곳이 의도한 유형인가'를 사람이 훑는다.
shortcut: 정답 없는 방송은 이동량만 본다. 정답 대조는 blind9_bounds.py / snap.py evaltable / evalnana."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import snap
from snap import pcm_of
from paths import cache_of
from blind9_bounds import patched

ALL = ["E1", "E1b", "E2", "E3", "S1", "S2"]


def run(ids, rules=None, ctx=False):
    D = {}
    for v in ids:
        f = Path("out") / v / "2_refine.json"
        w = next((p for p in (Path(f"data/vod/{v}.wav"), Path(f"data/vod/nas/{v}.wav")) if p.exists()), None)
        if not (f.exists() and w and Path(cache_of(w, ".scores.npy")).exists()):
            continue
        D[v] = (pcm_of(w), np.load(cache_of(w, ".scores.npy")), snap.voc_of(w), [g for g in json.load(open(f, encoding="utf8")) if g["keep"]])
    R = [x for x in ALL if not rules or x in rules]
    res = {}
    for r in [None] + R:
        undo = patched(set(ALL) - ({r} if r else set()) if not ctx else ({r} if r else set()))      # ctx 가 아니면 규칙 하나만 켠 결과를 모두 끈 것(None)과 비교, ctx 면 전부 켠 것(None)과 r 만 끈 것을 비교(다른 규칙과의 상호작용 포함)
        res[r] = {(v, g["start"]): snap.snap(pcm, a, g["start"], g["end"], voc) for v, (pcm, a, voc, S) in D.items() for g in S}
        undo()
    M = {}                                                  # 장면 판정(live/watch/idle/unknown): 4_scene.json 은 keep 순서가 2_refine 과 같다
    for v, (_, _, _, S) in D.items():
        f = Path("out") / v / "4_scene.json"
        if f.exists():
            C = [json.load(open(c, encoding="utf8")) for c in (Path("out") / v / "cards").glob("*.json")]      # 카드 등급(auto/review/drop): 현재 산출물 기준, refine 후보와 겹치는 카드
            for g, x in zip(S, json.load(open(f, encoding="utf8"))["segs"]):
                c = max(C, key=lambda c: min(c["end"], g["end"]) - max(c["start"], g["start"]), default=None)
                M[(v, g["start"])] = x.get("multi", "?")[:2] + "/" + (c["tier"][:2] if c and min(c["end"], g["end"]) > max(c["start"], g["start"]) else "--")
    L = {(v, g["start"]): g["end"] - g["start"] for v, (_, _, _, S) in D.items() for g in S}      # 곡 길이(refine 후보): 끝 이동의 비율 표시용
    print(f"방송 {len(D)}개, keep 구간 {len(res[None])}개")
    sg = -1 if ctx else 1
    for r in R:
        mv = [(k, sg * (res[r][k][0] - res[None][k][0]), sg * (res[r][k][1] - res[None][k][1])) for k in res[None] if max(abs(res[r][k][0] - res[None][k][0]), abs(res[r][k][1] - res[None][k][1])) > 1]
        print(f"{r}: 이동 {len(mv)}개  " + " ".join(f"{k[0]}:{k[1]:.0f}{M.get(k, '')}({a:+.0f},{b:+.0f}" + (f",{b / L[k]:+.0%}" if b and L.get(k) else "") + ")" for k, a, b in mv))
    return res


if __name__ == "__main__":
    a = sys.argv[1:]
    rules = {x[2:] for x in a if x.startswith("-r")}        # -rE1b 처럼 규칙을 골라 그 규칙만 점검(없으면 전부)
    run([x for x in a if not x.startswith("-")] or sorted(p.name for p in Path("out").iterdir() if (p / "2_refine.json").exists()), rules or None, "-c" in a)
    snap_ok = "regress ok"
    print(snap_ok)
