"""최적 임계의 부트스트랩 분포: 그룹(방송 x 날짜)을 복원추출한 표본마다 Sobol 100만 설정 중 (손실 0, N auto 0)에서 N 노출 최소인 설정들의 임계 중앙값을 기록 -> 임계별 분포(25/50/75%)와 기본값 위치.
좁은 분포 = 표본이 정하는 임계가 안정, 넓은 분포 = 표본 구성에 따라 최적이 흔들리는(과적합 위험이 큰) 임계. 
  python experiments/sweep_route_bootopt.py [--B 300] -> cache/proto_sweep/route_bootopt.json"""
import argparse, json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
os.chdir(ROOT)
import numpy as np, torch
import sweep_route as SR, sweep_route_run as RR

ap = argparse.ArgumentParser(); ap.add_argument("--B", type=int, default=300); a = ap.parse_args()
ctx = RR.Ctx()
z = np.load(RR.OUT / "route_random.npz")
X = {k: z[f"x_{k}"] for k in RR.KEYS}
Ef, Af = RR.compute_EA(ctx, X)
live = ctx.live
g = ctx.t.group.to_numpy(); ug = np.unique(g)
cnt = np.stack([(g == u) for u in ug], 1).astype(np.float32)           # [N, G]
rng = np.random.default_rng(0)
Xs = np.stack([X[k] for k in RR.KEYS], 1)
res, nfeas, best = [], [], []
for b in range(a.B):
    w = cnt @ np.bincount(rng.integers(0, len(ug), len(ug)), minlength=len(ug)).astype(np.float32)       # 행 가중치(그룹 복원추출 횟수)
    wt = torch.tensor(w, device="cuda", dtype=torch.float16)
    Ll = ((1 - Ef) @ (live.half() * wt)[:, None]).float()[:, 0]
    Na = (Af @ ((~live).half() * wt)[:, None]).float()[:, 0]
    Ne = (Ef @ ((~live).half() * wt)[:, None]).float()[:, 0]
    ok = (Ll == 0) & (Na == 0)
    if not ok.any():
        continue
    m = Ne.masked_fill(~ok, 1e9); bn = float(m.min())
    idx = torch.nonzero(m == bn).flatten().cpu().numpy()
    res.append(np.median(Xs[idx], 0)); best.append(bn); nfeas.append(int(ok.sum()))
res = np.array(res)
out = {k: dict(default=SR.DEF[k], q25=float(np.percentile(res[:, i], 25)), q50=float(np.percentile(res[:, i], 50)), q75=float(np.percentile(res[:, i], 75)), range=RR.RANGE[k]) for i, k in enumerate(RR.KEYS)}
json.dump(dict(params=out, best_N=best, n_feasible=nfeas), open(RR.OUT / "route_bootopt.json", "w"), ensure_ascii=False, indent=1)
print(f"부트스트랩 {len(res)}회, 최적 가중 N 노출 중앙 {np.median(best):.1f}, 제약 만족 설정 수 중앙 {int(np.median(nfeas))}")
for k, v in out.items():
    w = (v["q75"] - v["q25"]) / (v["range"][1] - v["range"][0])
    print(f"{k:11} 기본 {v['default']:<7g} 최적 분포 25/50/75% = {v['q25']:.4g} / {v['q50']:.4g} / {v['q75']:.4g}  (IQR/범위 {w:.2f})")
