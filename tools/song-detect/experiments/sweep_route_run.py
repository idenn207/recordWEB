"""route/N 신호 임계 탐색 실행기 (GPU): OAT 곡선, 2D 격자, Sobol 랜덤 탐색, 파레토, 그룹 hold-out(중첩) 선택, 부트스트랩, 고원/봉우리 판정.
  python experiments/sweep_route_run.py oat|grid|random|holdout|all   -> cache/proto_sweep/route_*.json (+ PNG)
지표(후보 표 211행 = 라이브 136 + N 75, 등록부 없음): L_loss = 노출 안 된 라이브(drop/weak), N_b9 = 노출된 blind9 N(55 중), N_all = 노출된 N(75 중), N_auto = auto 로 나간 N, L_auto = auto 라이브.
shortcut: 라이브 평가 행은 대부분 이 표본에서 임계가 정해진 것이라 표본 내 수치는 낙관적. 일반화 수치는 holdout 에서만 읽는다."""
import json, os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
os.chdir(ROOT)
import numpy as np
import torch
import sweep_route as SR

OUT = ROOT / "cache/proto_sweep"
RANGE = dict(idle=(1, 12), black=(0.02, 0.3), black_max=(0.35, 0.8), motion=(20, 50), weak=(10, 35), scene_drop=(0.1, 0.4), scene_ok=(0.04, 0.15), scene_idle=(0.0, 0.06),
             wait_s=(0, 600), len_lo=(80, 170), len_hi=(300, 420), rel_db=(-12, 0), bursts=(0.5, 6), speech=(0.02, 0.3))
KEYS = list(SR.DEF)
ROB = 0.05                                               # 교란 반폭(범위 비율)
dev = "cuda"


class Ctx:
    def __init__(self):
        self.t = SR.load()
        self.T = SR.tensors(self.t, dev)
        self.live = self.T["live"]
        self.b9 = torch.tensor((self.t.set == "blind9").to_numpy(), device=dev)

    def metrics(self, P, mask=None):
        """P 의 모든 설정에 대한 지표 텐서 dict ([C])."""
        E, A, L = SR.outcomes(P, self.T)
        m = torch.ones_like(self.live) if mask is None else mask
        N, Lv = ~self.live & m, self.live & m
        f = lambda x: x.sum(1)
        return dict(L_loss=f(Lv[None] & ~E), N_b9=f(N[None] & self.b9[None] & E), N_all=f(N[None] & E), N_auto=f(N[None] & A), L_auto=f(Lv[None] & A), likely_L=f(Lv[None] & L), likely_N=f(N[None] & L), _E=E)


def mk(cfgs):
    return {k: torch.tensor(np.asarray([c[k] for c in cfgs], np.float32), device=dev) for k in KEYS}


def oat(ctx, n=241):
    res = {}
    for k in KEYS:
        lo, hi = RANGE[k]
        vals = np.linspace(lo, hi, n)
        vals = np.unique(np.r_[vals, SR.DEF[k]])
        cfgs = [dict(SR.DEF, **{k: v}) for v in vals]
        m = ctx.metrics(mk(cfgs))
        res[k] = dict(default=SR.DEF[k], v=vals.tolist(), **{a: m[a].cpu().tolist() for a in ("L_loss", "N_b9", "N_all", "N_auto", "L_auto", "likely_L", "likely_N")})
    json.dump(res, open(OUT / "route_oat.json", "w"))
    print("OAT 완료")
    return res


def summarize_oat(res):
    """OAT 요약: 기본값에서 L_loss=0 을 유지하는 연속 구간(고원 폭), N_b9 가 가장 낮은 값."""
    rows = []
    for k, r in res.items():
        v, Ll, Nb, Na = map(np.array, (r["v"], r["L_loss"], r["N_b9"], r["N_auto"]))
        i0 = int(np.argmin(abs(v - r["default"])))
        ok = (Ll == 0) & (Na == 0)
        a = b = i0
        while a > 0 and ok[a - 1]: a -= 1
        while b < len(v) - 1 and ok[b + 1]: b += 1
        feas = np.flatnonzero(ok)
        best = feas[np.argmin(Nb[feas])] if len(feas) else None
        same = np.flatnonzero((Nb == Nb[i0]) & ok)
        rows.append(dict(key=k, default=r["default"], safe_lo=float(v[a]) if ok[i0] else None, safe_hi=float(v[b]) if ok[i0] else None, N_b9_default=int(Nb[i0]),
                         N_b9_best=int(Nb[best]) if best is not None else None, best_v=float(v[best]) if best is not None else None,
                         flat_lo=float(v[same.min()]) if len(same) else None, flat_hi=float(v[same.max()]) if len(same) else None, range=RANGE[k]))
    return rows


def grid2(ctx, a, b, na=81, nb=81):
    va = np.linspace(*RANGE[a], na); vb = np.linspace(*RANGE[b], nb)
    cfgs = [dict(SR.DEF, **{a: x, b: y}) for x in va for y in vb]
    m = ctx.metrics(mk(cfgs))
    sh = (na, nb)
    return dict(a=a, b=b, va=va.tolist(), vb=vb.tolist(), **{q: m[q].cpu().numpy().reshape(sh).tolist() for q in ("L_loss", "N_b9", "N_all", "N_auto", "L_auto")})


def sobol(n, seed=0):
    from scipy.stats import qmc
    u = qmc.Sobol(len(KEYS), scramble=True, seed=seed).random(n)
    lo = np.array([RANGE[k][0] for k in KEYS]); hi = np.array([RANGE[k][1] for k in KEYS])
    x = lo + u * (hi - lo)
    return {k: x[:, i].astype(np.float32) for i, k in enumerate(KEYS)}


def rand_search(ctx, n=1 << 20, chunk=1 << 14):
    X = sobol(n)
    M = {q: [] for q in ("L_loss", "N_b9", "N_all", "N_auto", "L_auto", "likely_L", "likely_N")}
    for i in range(0, n, chunk):
        P = {k: torch.tensor(v[i:i + chunk], device=dev) for k, v in X.items()}
        m = ctx.metrics(P)
        for q in M:
            M[q].append(m[q].cpu().numpy())
    M = {q: np.concatenate(v) for q, v in M.items()}
    return X, M


def pareto(M, idx):
    """(L_loss, N_all, N_auto 최소, L_auto 최대) 비지배 설정 중 idx 부분집합. 간단한 O(n^2) 대신 정렬 후 누적 최소."""
    pts = np.stack([M["L_loss"][idx], M["N_all"][idx], M["N_auto"][idx], -M["L_auto"][idx]], 1)
    u, first = np.unique(pts, axis=0, return_index=True)
    keep = []
    for i in range(len(u)):
        dom = ((u <= u[i]).all(1) & (u < u[i]).any(1)).any()
        if not dom:
            keep.append(i)
    return idx[first[keep]], u[keep]


def compute_EA(ctx, X, chunk=1 << 14):
    n = len(X[KEYS[0]])
    Ef = torch.empty((n, len(ctx.t)), dtype=torch.float16, device=dev)
    Af = torch.empty_like(Ef)
    for i in range(0, n, chunk):
        P = {k: torch.tensor(v[i:i + chunk], device=dev) for k, v in X.items()}
        E, A, _ = SR.outcomes(P, ctx.T)
        Ef[i:i + chunk], Af[i:i + chunk] = E.half(), A.half()
    return Ef, Af


def holdout(ctx, X, EA, by="group", rule="plateau"):
    """중첩 hold-out: 그룹 g 를 뺀 표본으로 설정을 고르고(라이브 손실 0 & N auto 0 중 N_all 최소; 동률은 plateau=정규화 공간 무게중심 설정 / first=첫 설정) g 의 행에서 평가.
    plateau 중심점은 동률 집합이 퍼져 있으면 오히려 위험해질 수 있어 그 결과를 그대로 보고한다."""
    Ef, Af = EA
    t = ctx.t
    col = t.group if by == "group" else t.name
    gs = sorted(col.unique())
    Te = torch.tensor(np.stack([(col == g).to_numpy() for g in gs], 1), device=dev)          # [N, G]
    live, lo = ctx.live, np.array([RANGE[k][0] for k in KEYS]); hi = np.array([RANGE[k][1] for k in KEYS])
    Lm, Nm = live.half()[:, None], (~live).half()[:, None]
    trm = (~Te).half()
    Ll = ((1 - Ef) @ (Lm * trm)).float()                              # [C, G] 학습 표본의 라이브 손실
    Na = (Af @ (Nm * trm)).float()
    Ne = (Ef @ (Nm * trm)).float()
    tot = dict(L_hold=0, N_hold=0, nL=0, nN=0)
    per = []
    for j, g in enumerate(gs):
        ok = (Ll[:, j] == 0) & (Na[:, j] == 0)
        m = Ne[:, j].masked_fill(~ok, 1e9)
        bestN = float(m.min())
        idx = torch.nonzero(m == bestN).flatten().cpu().numpy()
        C = np.stack([X[k][idx] for k in KEYS], 1)
        if rule == "robust":                                  # 평평한 곳 선택(sharpness-aware 식): N <= 최소+1 인 학습 가능 설정 중 +-delta 교란 64개가 여전히 가능(손실 0, auto 0, N <= 최소+1)한 비율이 최대인 것
            cand = torch.nonzero(ok & (Ne[:, j] <= bestN + 1)).flatten()
            cand = cand[torch.randperm(len(cand), device=dev)[:300]].cpu().numpy()
            rg = torch.Generator(device="cpu").manual_seed(j)
            best_sc, cfg = -1, None
            for i in cand:
                base = np.array([X[k][i] for k in KEYS])
                pert = base + (torch.rand(64, len(KEYS), generator=rg).numpy() - 0.5) * 2 * ROB * (hi - lo)
                pert = np.clip(pert, lo, hi)
                P = {k: torch.tensor(pert[:, q], device=dev, dtype=torch.float32) for q, k in enumerate(KEYS)}
                E, A, _ = SR.outcomes(P, ctx.T)
                trj = ~Te[:, j]
                sc = float((((live & trj)[None] & ~E).sum(1) == 0).logical_and(((~live & trj)[None] & A).sum(1) == 0).logical_and(((~live & trj)[None] & E).sum(1) <= bestN + 1).float().mean())
                if sc > best_sc:
                    best_sc, cfg = sc, base
        else:
            cfg = C[0] if rule == "first" else (((C - lo) / (hi - lo)).mean(0) * (hi - lo) + lo)
        P = {k: torch.tensor([cfg[q]], device=dev, dtype=torch.float32) for q, k in enumerate(KEYS)}
        E, A, L = SR.outcomes(P, ctx.T)
        te = Te[:, j]
        lh, nh = int((live & te)[None].logical_and(~E).sum()), int((~live & te)[None].logical_and(E).sum())
        per.append(dict(group=g, train_bestN=bestN, n_tied=int(len(C)), L_hold=lh, N_hold=nh, nL=int((live & te).sum()), nN=int((~live & te).sum())))
        tot["L_hold"] += lh; tot["N_hold"] += nh; tot["nL"] += per[-1]["nL"]; tot["nN"] += per[-1]["nN"]
    return tot, per


def main():
    ctx = Ctx()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    t0 = time.time()
    if cmd in ("oat", "all"):
        res = oat(ctx)
        S = summarize_oat(res)
        json.dump(S, open(OUT / "route_oat_summary.json", "w"), ensure_ascii=False, indent=1)
        for r in S:
            print(r)
    if cmd in ("grid", "all"):
        G = {f"{a}x{b}": grid2(ctx, a, b) for a, b in (("rel_db", "bursts"), ("motion", "weak"), ("scene_ok", "scene_drop"), ("idle", "black"), ("len_lo", "len_hi"), ("wait_s", "motion"))}
        json.dump(G, open(OUT / "route_grid.json", "w"))
        print("격자 완료", time.time() - t0)
    if cmd in ("random", "all"):
        X, M = rand_search(ctx)
        np.savez(OUT / "route_random.npz", **{f"x_{k}": v for k, v in X.items()}, **{f"m_{k}": v for k, v in M.items()})
        feas = np.flatnonzero((M["L_loss"] == 0) & (M["N_auto"] == 0))
        print(f"Sobol {len(M['L_loss'])}개 중 라이브 손실 0 & N auto 0 = {len(feas)} ({len(feas) / len(M['L_loss']):.1%}), 그 중 N_b9 최소 {M['N_b9'][feas].min()} N_all 최소 {M['N_all'][feas].min()}")
        print(f"  기본 설정(DEF) N_b9=14 N_all=?  ({time.time() - t0:.0f}s)")
    if cmd in ("holdout", "all"):
        z = np.load(OUT / "route_random.npz")
        X = {k: z[f"x_{k}"] for k in KEYS}
        EA = compute_EA(ctx, X)
        out = {}
        for by in ("group", "streamer"):
            for rule in ("plateau", "first", "robust"):
                tot, per = holdout(ctx, X, EA, by, rule)
                out[f"{by}/{rule}"] = dict(total=tot, per=per)
                print(f"{by}/{rule}: hold-out N 노출 {tot['N_hold']}/{tot['nN']}, 라이브 손실 {tot['L_hold']}/{tot['nL']}  ({time.time() - t0:.0f}s)", flush=True)
        json.dump(out, open(OUT / "route_holdout.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
