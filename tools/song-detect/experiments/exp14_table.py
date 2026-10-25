"""끝 이음(snap.bridge) 전후 오차표. 전 = B_DB 를 -1e9 로 두어 bridge 를 끈 것. 정답 위치 있는 표본만, 어느 쪽이든 |오차|>20초는 매칭/분할 문제라 제외하고 개수만 적는다.
사용: PYTHONPATH=. python experiments/exp14_table.py [-v]"""
import sys, numpy as np
import snap
from exp14_items import items
from paths import cache_of
rows, P = [], {}
for n, w, s, e, ts, te in items():
    if w not in P: P[w] = (snap.pcm_of(w), np.load(cache_of(w, ".scores.npy")))
    old, snap.B_DB = snap.B_DB, -1e9
    s0, e0 = snap.snap(*P[w], s, e)
    snap.B_DB = old
    s1, e1 = snap.snap(*P[w], s, e)
    rows.append((n, s0, e0, s1, e1, ts, te))
keep = [r for r in rows if r[6] and abs(r[2] - r[6]) <= 20 and abs(r[4] - r[6]) <= 20]
print("끝 정답 표본 %d (이탈 제외 %d)" % (len(keep), sum(1 for r in rows if r[6]) - len(keep)))
for lab, k in (("전", 2), ("후", 4)):
    x = np.array([r[k] - r[6] for r in keep])
    print(lab, "일찍(<-2) %d, 늦음(>+2) %d, |오차|<=2 %d, 평균|오차| %.2f, 최악 일찍 %.1f" % ((x < -2).sum(), (x > 2).sum(), (abs(x) <= 2).sum(), abs(x).mean(), x.min()))
for r in rows:
    if r[2] != r[4] or "-v" in sys.argv:
        print("변경 %-22s 끝 %s -> %s" % (r[0], "%+.1f" % (r[2] - r[6]) if r[6] else "-", "%+.1f" % (r[4] - r[6]) if r[6] else "-"), "(+%.1fs)" % (r[4] - r[2]))
