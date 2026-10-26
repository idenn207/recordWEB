"""snap 규칙(E1 E2 E3 S1 S2) 회귀 점검: out/<방송>/2_refine.json 의 keep 구간 전체에 규칙을 하나씩만 켜서 예전 snap(모두 끔)과 경계가 얼마나 달라지는지 센다.
사용: python experiments/regress_snap.py [방송id...]   (기본 = out 의 전부, wav 와 cache/detect 점수가 있는 것)
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

ALL = ["E1", "E2", "E3", "S1", "S2"]


def run(ids):
    D = {}
    for v in ids:
        f = Path("out") / v / "2_refine.json"
        w = next((p for p in (Path(f"data/vod/{v}.wav"), Path(f"data/vod/nas/{v}.wav")) if p.exists()), None)
        if not (f.exists() and w and Path(cache_of(w, ".scores.npy")).exists()):
            continue
        D[v] = (pcm_of(w), np.load(cache_of(w, ".scores.npy")), snap.voc_of(w), [g for g in json.load(open(f, encoding="utf8")) if g["keep"]])
    res = {}
    for r in [None] + ALL:
        undo = patched(set(ALL) - ({r} if r else set()))
        res[r] = {(v, g["start"]): snap.snap(pcm, a, g["start"], g["end"], voc) for v, (pcm, a, voc, S) in D.items() for g in S}
        undo()
    print(f"방송 {len(D)}개, keep 구간 {len(res[None])}개")
    for r in ALL:
        mv = [(k, res[r][k][0] - res[None][k][0], res[r][k][1] - res[None][k][1]) for k in res[None] if max(abs(res[r][k][0] - res[None][k][0]), abs(res[r][k][1] - res[None][k][1])) > 1]
        print(f"{r}: 이동 {len(mv)}개  " + " ".join(f"{k[0]}:{k[1]:.0f}({a:+.0f},{b:+.0f})" for k, a, b in mv))
    return res


if __name__ == "__main__":
    run(sys.argv[1:] or sorted(p.name for p in Path("out").iterdir() if (p / "2_refine.json").exists()))
    snap_ok = "regress ok"
    print(snap_ok)
