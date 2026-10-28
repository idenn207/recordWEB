"""경계 규칙 상수 전체의 Morris 스크리닝(SALib.sample.morris / analyze.morris): 상수를 기본값 +-30%(정수형은 +-1~2, 확률형은 1.0 상한)로 동시에 움직여
기본 효과(elementary effect)의 평균 절댓값 mu_star(영향 크기)와 표준편차 sigma(상호작용/비선형)를 응답별로 낸다. 응답: gold_dev(golden 이탈), moved2(전 방송 840구간 중 2초 넘게 움직인 곡), hit3(메모 정답 hit@3), dir_pass.
  python experiments/sweep_morris.py [--r 8] [--out cache/proto_sweep/morris.json]
shortcut: Morris 는 단조 가정 없이 영향 순위만 준다(분산 분해 아님). 정수/선택형 상수는 반올림해 연속 근사."""
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import sweep_core as S
from sweep_oat import KEYS, INT


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--r", type=int, default=8)
    ap.add_argument("--out", default="cache/proto_sweep/morris.json")
    ap.add_argument("--span", type=float, default=0.3)
    a = ap.parse_args()
    import tune
    from SALib.sample import morris as ms
    from SALib.analyze import morris as ma
    cur = tune.listing()
    keys = [k for k in KEYS]
    bounds = []
    for k in keys:
        d = cur[k]
        if k in INT:
            bounds.append([max(1, d - 1), d + 2])
        else:
            hi = d * (1 + a.span)
            bounds.append([d * (1 - a.span), min(hi, 1.0) if d < 1.0 else hi])
    prob = dict(num_vars=len(keys), names=keys, bounds=bounds)
    X = ms.sample(prob, a.r, num_levels=4, seed=1)
    print(f"{len(X)}개 설정 평가", flush=True)
    ev = S.Evaluator(8, wide=True)
    ev.evaluate({})
    Y = {k: [] for k in ("gold_dev", "moved2", "hit3", "dir_pass")}
    t0 = time.time()
    for i, x in enumerate(X):
        cfg = {k: (int(round(v)) if k in INT else float(v)) for k, v in zip(keys, x)}
        r = ev.evaluate(cfg)
        for k in Y:
            Y[k].append(r[k])
        if i % 40 == 0:
            print(i, f"{time.time() - t0:.0f}s", flush=True)
    ev.close()
    out = {}
    for k, y in Y.items():
        res = ma.analyze(prob, X, np.array(y, float), num_levels=4, print_to_console=False)
        out[k] = dict(names=keys, mu_star=[float(v) for v in res["mu_star"]], sigma=[float(v) for v in res["sigma"]], mu_star_conf=[float(v) for v in res["mu_star_conf"]])
    json.dump(dict(Y={k: [float(v) for v in y] for k, y in Y.items()}, out=out, bounds=bounds), open(a.out, "w"), ensure_ascii=False)
    for k in out:
        o = sorted(zip(keys, out[k]["mu_star"], out[k]["sigma"]), key=lambda t: -t[1])
        print(k, [(n, round(m, 2), round(s, 2)) for n, m, s in o[:12]])


if __name__ == "__main__":
    main()
