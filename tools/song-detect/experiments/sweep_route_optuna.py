"""route 임계 탐색기 비교: 같은 목적(라이브 손실 0, N auto 0 제약 + N 노출 최소)을 무작위 / Sobol / TPE / CMA-ES / NSGA-II 가 시험 횟수별로 얼마나 빨리 찾는지.
Optuna(Akiba 외 2019, KDD) 샘플러를 쓴다. 목적 함수는 후보 표 위의 sweep_route.outcomes 한 설정(GPU) - 한 번에 수 ms.
  python experiments/sweep_route_optuna.py [--trials 3000] [--seeds 3]   -> cache/proto_sweep/route_optuna.json
shortcut: 표본이 211행이라 목적이 계단 함수다(그래디언트/모델 기반 탐색의 이점이 작음). 비교 결과는 이 표본에서만 의미가 있다."""
import argparse, json, sys, os, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
os.chdir(ROOT)
import numpy as np
import optuna
import torch
import sweep_route as SR, sweep_route_run as RR

optuna.logging.set_verbosity(optuna.logging.WARNING)


def make_obj(ctx):
    def score(x):
        P = {k: torch.tensor([x[k]], device="cuda", dtype=torch.float32) for k in RR.KEYS}
        m = ctx.metrics(P)
        return int(m["L_loss"]), int(m["N_auto"]), int(m["N_all"]), int(m["N_b9"]), int(m["L_auto"])
    return score


def run(ctx, name, trials, seed):
    score = make_obj(ctx)
    best, curve = 10 ** 9, []
    if name == "sobol":
        X = RR.sobol(trials, seed)
        for i in range(trials):
            l, a, n, nb, la = score({k: float(X[k][i]) for k in RR.KEYS})
            if l == 0 and a == 0:
                best = min(best, n)
            curve.append(best)
        return curve
    sampler = {"random": optuna.samplers.RandomSampler(seed=seed), "tpe": optuna.samplers.TPESampler(seed=seed, multivariate=True), "cmaes": optuna.samplers.CmaEsSampler(seed=seed),
               "nsga2": optuna.samplers.NSGAIISampler(seed=seed)}[name]
    multi = name == "nsga2"
    st = optuna.create_study(sampler=sampler, directions=["minimize"] * 3 if multi else ["minimize"])

    def obj(tr):
        x = {k: tr.suggest_float(k, *RR.RANGE[k]) for k in RR.KEYS}
        l, a, n, nb, la = score(x)
        tr.set_user_attr("feas", l == 0 and a == 0)
        tr.set_user_attr("n", n)
        return (l + a, n, -la) if multi else n + 50 * (l + a)
    for i in range(trials):
        tr = st.ask()
        v = obj(tr)
        st.tell(tr, v)
        if tr.user_attrs["feas"]:
            best = min(best, tr.user_attrs["n"])
        curve.append(best)
    return curve


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=3000)
    ap.add_argument("--seeds", type=int, default=3)
    a = ap.parse_args()
    ctx = RR.Ctx()
    res = {}
    for name in ("random", "sobol", "tpe", "cmaes", "nsga2"):
        t0 = time.time()
        cs = [run(ctx, name, a.trials, s) for s in range(a.seeds)]
        res[name] = cs
        marks = [100, 300, 1000, a.trials]
        print(f"{name:7} " + "  ".join(f"@{m}: " + "/".join(str(c[m - 1]) if c[m - 1] < 10 ** 9 else "-" for c in cs) for m in marks) + f"  ({time.time() - t0:.0f}s)", flush=True)
    json.dump(res, open(ROOT / "cache/proto_sweep/route_optuna.json", "w"))


if __name__ == "__main__":
    main()
