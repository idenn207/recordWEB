"""끝 early / 시작 late 검증기의 (k, gap) 를 방송(vno) 단위 hold-out 으로 고르는 시험. 학습 방송에서 (tp - 3 x fp) 최대인 (k,gap) 을 고르고 빠진 방송에서 평가해 합산한다.
  python experiments/asr_logo.py [--tx t_small_auto]   (표본 내 최적 값과 나란히 보여 과적합 폭을 본다)"""
import sys, itertools, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import asr_eval as A

ap = argparse.ArgumentParser(); ap.add_argument("--tx", default="t_small_auto"); a = ap.parse_args()
D = A.prep(a.tx)
grid = list(itertools.product((2, 3, 5, 8), (4, 5, 8, 15)))
vnos = sorted({g["vno"] for g, _, _ in D.values()})
def score(sub, k, gap):
    R = A.verifier(sub, 20.0, gap, k)
    return {s: (R[s]["tp"], R[s]["pos"], R[s]["fp"], R[s]["neg"]) for s in R}
for side in ("end", "start"):
    tot = np.zeros(4, int); picks = []
    for v in vnos:
        tr = {k: x for k, x in D.items() if x[0]["vno"] != v}; te = {k: x for k, x in D.items() if x[0]["vno"] == v}
        best = max(grid, key=lambda kg: score(tr, *kg)[side][0] - 3 * score(tr, *kg)[side][2])
        tot += score(te, *best)[side]; picks.append(best)
    ins = max(grid, key=lambda kg: score(D, *kg)[side][0] - 3 * score(D, *kg)[side][2])
    print(f"[{side}] 방송 hold-out 합산 tp {tot[0]}/{tot[1]} fp {tot[2]}/{tot[3]} | 표본 내 최적 {ins} -> tp/fp {score(D, *ins)[side]} | 폴드별 선택 분포 {dict(zip(*np.unique([f'{k},{g}' for k, g in picks], return_counts=True)))}")
