"""곡 끝 직후 멘트 시작 시각: Whisper 단어 기준(talk 단어 = Speech>Singing, 가사 아님) vs TAIL 가드의 YAMNet 기준(Speech>0.15 첫 프레임)을 같은 곡 끝 e 에서 비교한다.
  python experiments/asr_tail.py [--tx t_small_auto] [--lo -1 --hi 12]
e = 메모 감사 기준 곡 끝(base 끝, v3 시점). 창 [e+lo, e+hi] 안에서 각 방법의 첫 멘트 시작 시각을 e 기준 상대초로 출력하고 차이 분포를 낸다.
shortcut: 정답(사람이 들은 멘트 시작)이 없어 두 방법의 일치도만 본다. 불일치 곡은 end_view.py 그림으로 눈 검수(귀 아님)."""
import sys, os, argparse
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT); sys.path.insert(0, str(ROOT / "experiments"))
import numpy as np
import asr_bounds as B
from asr_run import groups

ap = argparse.ArgumentParser(); ap.add_argument("--tx", default="t_small_auto"); ap.add_argument("--lo", type=float, default=-1); ap.add_argument("--hi", type=float, default=12); a = ap.parse_args()
diffs, n_both, n_a, n_y = [], 0, 0, 0
rows = []
for g in groups():
    if g["lab"] == "N": continue
    d = B.load_tx(a.tx, g["gid"])
    if not d: continue
    S = B.scores(g["vno"]); e = g["base"][1]
    ws = B.words(d, S)
    ly = set(map(tuple, B.lyric(ws)))
    talk = [w for w in ws if tuple(w) not in ly and w[5] > w[4] and e + a.lo <= w[0] <= e + a.hi]
    ta = min((w[0] for w in talk), default=None)
    k0, k1 = int((e + a.lo) / .5), int((e + a.hi) / .5)
    fr = np.flatnonzero(S[k0:k1, 1] > .15)
    ty = (k0 + fr[0]) * .5 + .25 - e if len(fr) else None        # 점수 창 중심(TAIL 과 같은 정의)
    ta = ta - e if ta is not None else None
    rows.append((g["gid"], ta, ty))
    n_a += ta is not None; n_y += ty is not None
    if ta is not None and ty is not None:
        n_both += 1; diffs.append(ta - ty)
diffs = np.array(diffs)
print(f"라이브 {len(rows)}곡 | Whisper 멘트 있음 {n_a} / YAMNet 멘트 있음 {n_y} / 둘 다 {n_both}")
if len(diffs): print(f"둘 다 있는 곡 차이(Whisper - YAMNet 초): 중앙 {np.median(diffs):.2f} p10 {np.percentile(diffs,10):.2f} p90 {np.percentile(diffs,90):.2f}, |차| <= 0.5초 {int((abs(diffs)<=.5).sum())}/{len(diffs)}, |차| <= 1초 {int((abs(diffs)<=1).sum())}/{len(diffs)}")
only_a = [r[0] for r in rows if r[1] is not None and r[2] is None]; only_y = [r[0] for r in rows if r[2] is not None and r[1] is None]
print("Whisper 만:", only_a, "\nYAMNet 만:", only_y)
big = [(r[0], round(r[1], 1), round(r[2], 1)) for r in rows if r[1] is not None and r[2] is not None and abs(r[1] - r[2]) > 1.5]
print("불일치 > 1.5초 (gid, Whisper, YAMNet):", big)
D4 = [14, 36, 70, 105, 126, 130, 132, 138, 143]       # HANDOFF 26절: 곡 끝 0.3초~1초 안에 말이 시작하는 승인 L (6곡은 0.3초 안)
print("D4 곡 (Whisper, YAMNet) e 기준 초:", {g: (None if t[1] is None else round(t[1], 1), None if t[2] is None else round(t[2], 1)) for g in D4 for t in rows if t[0] == g})
print("D4 중 Whisper 가 1초 안 멘트를 잡은 곡:", sum(1 for g in D4 for t in rows if t[0] == g and t[1] is not None and t[1] <= 1.0), "/ YAMNet:", sum(1 for g in D4 for t in rows if t[0] == g and t[2] is not None and t[2] <= 1.0))
