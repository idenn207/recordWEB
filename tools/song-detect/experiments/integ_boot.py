"""스트리머 단위 부트스트랩(4000회): 규칙 D(hold-out) 대 D + n_visual(hold-out m=0.1) 의 blind9 N 노출 차이 구간. integ_holdout.evaluate 를 그대로 재현한 뒤 스트리머 재표집.
  python experiments/integ_boot.py          배포 경로 vis(4_scene)
  python experiments/integ_boot.py proto    프로토 프레임 vis(참고)
shortcut: blind9 N 55곡은 스트리머 6명(리제 29, 나나 14, 히요리 8, 랑 2, 토아 1, 메리 1)뿐이라 구간이 넓다. 스트리머 단위 표본이 더 모이면 다시 낸다."""
import sys, os, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments")); os.chdir(ROOT)
import numpy as np, pandas as pd
import integ_holdout as IH, logo_route as LR, n_signals, n_visual
from scene_multi import P as MP
V = pd.DataFrame(json.load(open(IH.TAB, encoding="utf8")))
V = pd.concat([V, IH.golden_rows()], ignore_index=True)
sig = LR.with_golden(LR.load())
G = IH.golden_rows().set_index("key").name
if sys.argv[1:] != ["proto"]:
    d = IH.deploy_vis(sig); assert len(d) == 104
    V["vis"] = [d.get(k, v) for k, v in zip(V.key, V.vis)]
sig["streamer"] = [G.get(k, n) for k, n in zip(sig.key, sig.name)]
D, _ = LR.holdout(sig, "streamer", "D", 0.1); sig["D"] = D
thr = n_visual.cal()["thr"]
fl = np.array([bool(n_signals.fire(dict(rel_db=r, bursts=b))) for r, b in zip(sig.rel_db.fillna(0), sig.bursts_per_min.fillna(0))])
sig["dep_ok"] = ~(((sig.struct_cls == "drop") | (sig.tstd > MP["motion"])).to_numpy() | fl)
X = sig.merge(V[["key", "vis"]], on="key", how="left")
Z = X[X.set == "blind9"].copy()
hit = IH.veto(V.vis.to_numpy(), V.live.to_numpy(), V.name.to_numpy(), 0.1)
H = dict(zip(V.key, hit))
Z["vh"] = Z.key.map(H).fillna(False).astype(bool)
N = Z[Z.live == 0]
print("blind9 N", len(N), "streamers", N.streamer.nunique(), dict(N.groupby("streamer").size()))
expD = (N.D == "ok").to_numpy(); expDV = expD & ~N.vh.to_numpy()
expA = N.dep_ok.to_numpy(); expAV = expA & (N.vis.fillna(-9) <= thr).to_numpy()
print("point: D", expD.sum(), "D+vis", expDV.sum(), "A", expA.sum(), "A+vis", expAV.sum())
g = N.streamer.to_numpy(); ug = np.unique(g); rng = np.random.default_rng(0)
rows = np.array([[(g == u).sum(), expD[g == u].sum(), expDV[g == u].sum(), expA[g == u].sum(), expAV[g == u].sum()] for u in ug])
est = []
for _ in range(4000):
    s = rows[rng.integers(0, len(ug), len(ug))].sum(0)
    est.append([s[1] / s[0], s[2] / s[0], (s[1] - s[2]) / s[0], s[3] / s[0], s[4] / s[0], (s[3] - s[4]) / s[0], s[1] - s[2], s[3] - s[4]])
q = np.percentile(np.array(est), [2.5, 97.5], axis=0)
names = ["D rate", "D+vis rate", "D - D+vis rate", "A rate", "A+vis rate", "A - A+vis rate", "D-D+vis count", "A-A+vis count"]
for i, n in enumerate(names): print(f"{n:16s} 95% [{q[0,i]:.3f}, {q[1,i]:.3f}]")
# which N songs does vis remove under D (hold-out)?
print("removed by vis under D:", list(N[expD & ~expDV].key))
print("removed by vis under A:", list(N[expA & ~expAV].key))
print("per-streamer gains D->D+vis:", {u: int(rows[i,1]-rows[i,2]) for i,u in enumerate(ug)})
