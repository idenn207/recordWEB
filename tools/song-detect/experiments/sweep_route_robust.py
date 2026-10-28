"""route 후보 설정들의 고원/봉우리 판정과 부트스트랩: 현재 설정, CMA-ES/TPE 최적, 파레토 설정, 전체 표본 robust 선택.
  - 이웃 안정성: 각 설정을 범위의 +-d(1/2/5/10%) 만큼 무작위 교란한 4096개 중 (라이브 손실 0 & N auto 0)인 비율, 평균 N 노출, N<=현재(15) 비율. 높을수록 평평한 고원, 낮을수록 좁은 봉우리.
  - 그룹 부트스트랩(스트리머 x 방송일 복원추출 2000회): N 노출률, 라이브 손실률 95% 구간(점추정만 쓰지 않는다).
shortcut: 교란은 축별 독립 균등이라 상관된 이동(예: rel_db 와 bursts 가 같이 움직임)은 보지 않는다."""
import json, os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
os.chdir(ROOT)
import numpy as np, torch, optuna
import sweep_route as SR, sweep_route_run as RR

optuna.logging.set_verbosity(optuna.logging.WARNING)
O = ROOT / "cache/proto_sweep"
lo = np.array([RR.RANGE[k][0] for k in RR.KEYS]); hi = np.array([RR.RANGE[k][1] for k in RR.KEYS])


def vec(c):
    return np.array([c[k] for k in RR.KEYS], np.float64)


def evalv(ctx, X):
    P = {k: torch.tensor(X[:, i], device="cuda", dtype=torch.float32) for i, k in enumerate(RR.KEYS)}
    m = ctx.metrics(P)
    return {k: v.cpu().numpy() for k, v in m.items() if k != "_E"}


def cma_best(ctx, seed, n=6000, sampler="cmaes"):
    sp = optuna.samplers.CmaEsSampler(seed=seed) if sampler == "cmaes" else optuna.samplers.TPESampler(seed=seed, multivariate=True)
    st = optuna.create_study(sampler=sp)
    best = (10 ** 9, None)
    for _ in range(n):
        tr = st.ask()
        x = np.array([tr.suggest_float(k, *RR.RANGE[k]) for k in RR.KEYS])
        m = evalv(ctx, x[None])
        pen = 50 * int(m["L_loss"][0] + m["N_auto"][0])
        st.tell(tr, int(m["N_all"][0]) + pen - 0.01 * int(m["L_auto"][0]))
        if pen == 0 and (int(m["N_all"][0]), -int(m["L_auto"][0])) < (best[0], 0) or (pen == 0 and int(m["N_all"][0]) == best[0] and best[1] is not None and m["L_auto"][0] > best[1][1]):
            best = (int(m["N_all"][0]), (x, int(m["L_auto"][0])))
    return best


def neighborhood(ctx, x, d, n=4096, seed=0):
    rng = np.random.default_rng(seed)
    X = np.clip(x + (rng.random((n, len(x))) - .5) * 2 * d * (hi - lo), lo, hi)
    m = evalv(ctx, X)
    feas = (m["L_loss"] == 0) & (m["N_auto"] == 0)
    return dict(d=d, feas=float(feas.mean()), N_mean=float(m["N_all"][feas].mean()) if feas.any() else None, N_le15=float((feas & (m["N_all"] <= 15)).mean()), L_auto_mean=float(m["L_auto"][feas].mean()) if feas.any() else None)


def boot(ctx, x, B=2000, seed=0):
    P = {k: torch.tensor([x[i]], device="cuda", dtype=torch.float32) for i, k in enumerate(RR.KEYS)}
    E, A, L = SR.outcomes(P, ctx.T)
    E = E[0].cpu().numpy(); live = ctx.live.cpu().numpy(); g = ctx.t.group.to_numpy()
    ug = np.unique(g)
    rows = np.array([[((g == u) & ~live).sum(), ((g == u) & ~live & E).sum(), ((g == u) & live).sum(), ((g == u) & live & ~E).sum()] for u in ug])
    rng = np.random.default_rng(seed)
    est = []
    for _ in range(B):
        s = rows[rng.integers(0, len(ug), len(ug))].sum(0)
        est.append([s[1] / s[0] if s[0] else np.nan, s[3] / s[2] if s[2] else np.nan])
    q = np.nanpercentile(np.array(est), [2.5, 97.5], axis=0)
    return dict(N_rate=[round(float(E[~live].mean()), 3), q[:, 0].round(3).tolist()], L_loss_rate=[round(float((~E[live]).mean()), 3), q[:, 1].round(3).tolist()], n_groups=int(len(ug)))


def main():
    ctx = RR.Ctx()
    t0 = time.time()
    C = {"현재(DEF)": vec(SR.DEF)}
    for sd in (0, 1):
        b = cma_best(ctx, sd)
        C[f"CMA-ES s{sd}"] = b[1][0]; print("cma", sd, b[0], b[1][1], f"{time.time() - t0:.0f}s", flush=True)
    b = cma_best(ctx, 0, 4000, "tpe"); C["TPE s0"] = b[1][0]; print("tpe", b[0], b[1][1], flush=True)
    z = np.load(O / "route_random.npz")
    X = np.stack([z[f"x_{k}"] for k in RR.KEYS], 1)
    for n, la in json.load(open(O / "route_pareto_front.json")):
        i = np.flatnonzero((z["m_N_all"] == n) & (z["m_L_auto"] == la) & (z["m_L_loss"] == 0) & (z["m_N_auto"] == 0))[0]
        C[f"Sobol 파레토 N{n}/auto{la}"] = X[i].astype(np.float64)
    # 전체 표본 robust 선택: N<=15 인 가능 설정 중 +-5% 교란 가능률 최대
    feas = np.flatnonzero((z["m_L_loss"] == 0) & (z["m_N_auto"] == 0) & (z["m_N_all"] <= 15))
    rng = np.random.default_rng(0)
    best, bx = -1, None
    for i in rng.permutation(feas)[:400]:
        f = neighborhood(ctx, X[i].astype(np.float64), 0.05, 512)["feas"]
        if f > best:
            best, bx = f, X[i].astype(np.float64)
    C["robust(N<=15, +-5%)"] = bx
    out = {}
    for name, x in C.items():
        m = evalv(ctx, x[None])
        out[name] = dict(params={k: round(float(x[i]), 4) for i, k in enumerate(RR.KEYS)}, N_all=int(m["N_all"][0]), N_b9=int(m["N_b9"][0]), L_loss=int(m["L_loss"][0]), N_auto=int(m["N_auto"][0]), L_auto=int(m["L_auto"][0]),
                         nbhd=[neighborhood(ctx, x, d) for d in (0.01, 0.02, 0.05, 0.10)], boot=boot(ctx, x))
        r = out[name]
        print(f"{name:24} N {r['N_all']} (b9 {r['N_b9']}) 손실 {r['L_loss']} auto N {r['N_auto']} auto L {r['L_auto']} | 이웃 가능률 " + " ".join(f"{n['d']:.0%}:{n['feas']:.2f}" for n in r["nbhd"]) + f" | N률 {r['boot']['N_rate']} 손실률 {r['boot']['L_loss_rate']}", flush=True)
    json.dump(out, open(O / "route_robust.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
