"""라이브 손실 위험의 상한(Clopper-Pearson)과 고정 순서 검정(Learn-then-Test 식, Angelopoulos 외 arXiv 2110.01052 초록을 읽고 아이디어만 차용; 논문의 전체 절차를 구현한 것은 아님).
1) 현재 설정의 라이브 손실 0건에 대한 95% 상한: 행 단위(독립 가정), 방송 그룹 단위, 스트리머 단위.
2) 고정 경로 검정: 현재 임계에서 공격적인 쪽(bursts 2.1 -> 0.8, rel_db -5.7 -> -1.0, motion 34.5 -> 28)으로 미리 정한 경로 t=0..1 을 따라, 각 점에서 H0: 라이브 행 손실률 >= alpha 를 이항 검정(p = P[X<=k | n, alpha])하고
   p > delta 가 처음 나오는 점에서 멈춘다(고정 순서 검정은 다중검정 보정 없이 유효). 경로는 데이터로 고르지 않았지만 임계 자체는 같은 표본에서 정해진 값이라 보장은 근사(shortcut)다.
  python experiments/sweep_route_ltt.py"""
import json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
os.chdir(ROOT)
import numpy as np, torch
from scipy.stats import beta, binom
import sweep_route as SR, sweep_route_run as RR


def cp_upper(k, n, conf=0.95):
    return float(beta.ppf(conf, k + 1, n - k)) if k < n else 1.0


def main():
    ctx = RR.Ctx()
    t = ctx.t
    live = t.live.to_numpy().astype(bool)
    m = ctx.metrics(RR.mk([SR.DEF]))
    k = int(m["L_loss"][0])
    ng = t[live].group.nunique(); ns = t[live].name.nunique()
    print(f"현재 설정: 라이브 손실 {k}/{live.sum()} 행 -> 95% 상한 {cp_upper(k, live.sum()):.1%} (행), {k}/{ng} 방송 그룹 -> {cp_upper(k, ng):.1%}, {k}/{ns} 스트리머 -> {cp_upper(k, ns):.1%}")
    ts = np.linspace(0, 1, 101)
    cfgs = [dict(SR.DEF, bursts=2.1 + t_ * (0.8 - 2.1), rel_db=-5.7 + t_ * (-1.0 + 5.7), motion=34.5 + t_ * (28 - 34.5)) for t_ in ts]
    mm = ctx.metrics(RR.mk(cfgs))
    L = mm["L_loss"].cpu().numpy(); N = mm["N_all"].cpu().numpy()
    n = int(live.sum())
    for alpha, delta in ((0.02, 0.1), (0.05, 0.1), (0.10, 0.1)):
        stop = None
        for i, (l, nn) in enumerate(zip(L, N)):
            p = binom.cdf(int(l), n, alpha)
            if p > delta:
                stop = i; break
        last = (stop - 1) if stop is not None else len(ts) - 1
        print(f"alpha={alpha:.0%} delta={delta}: 경로 t={ts[last]:.2f} 까지 H0 기각 -> 손실 {int(L[last])}/{n}, N 노출 {int(N[last])}/75 (t=0 에서 {int(N[0])})  [bursts {cfgs[last]['bursts']:.2f} rel_db {cfgs[last]['rel_db']:.2f} motion {cfgs[last]['motion']:.1f}]")
    json.dump(dict(t=ts.tolist(), L=L.tolist(), N=N.tolist()), open("cache/proto_sweep/route_ltt.json", "w"))


if __name__ == "__main__":
    main()
