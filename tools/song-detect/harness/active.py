"""축 (d) 사람 후보 선택(active learning) 재생: 지금까지의 판정을 시간순으로 다시 돌린다 (PLAN_NEXT P7).
시드 = blind5/6/78 판정(59행). blind9 104행은 방송일 순으로 라운드(ROUNDS)에 나눠 도착하고, 라운드마다 전략이 아직 판정 안 된 도착 행 중 K 개를 '사람에게 묻는다'.
묻기 직전 모델(LR, 지금까지 판정 행으로 학습, 구조 veto 포함)이 틀린 행이 '정보 있는 후보'다. 지표: (1) P@K = 고른 K 개 중 모델이 틀린 비율(무작위의 몇 배인지),
(2) 마지막에 묻지 않은 blind9 행에 대한 모델 AUC/오류율(학습 곡선), (3) 고른 N 의 유형(tag) 수(새 유형 포착).
전략: random(200 시드 평균) / uncertainty(p 가 0.5 에 가까운 순) / likely_first(p 높은 순 = 지금 사람이 위에서부터 보는 방식) / kcenter(특징 공간 먼저 가장 먼 점, GPU 거리) /
 unc_div(불확실 상위 3K 중 kcenter K) / cluster_rep(KMeans K 군집 대표) / committee(LR, LGB, 규칙 배포 임계의 불일치) / density_unc(불확실도 x 밀도).
한계: 표본이 작다(라운드 6, 라벨 104). 무작위 외 전략은 결정적이라 반복이 없다. 경계 문제(B)용 규칙 변형 위원회는 평가하지 않았다(라벨이 L/N 이진).
사용: C:/_tools/wt/venv/Scripts/python.exe harness/active.py -> cache/proto_harness/active.json"""
import json, os, sys, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.lib import *
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import logo_route as LR
from harness.ranker import mk, FULL
from sklearn.metrics import roc_auc_score
from sklearn.cluster import KMeans
import torch

DEV = "cuda" if torch.cuda.is_available() else "cpu"
ROUNDS = 6


def dist_gpu(A, B):
    return torch.cdist(torch.tensor(A, dtype=torch.float32, device=DEV), torch.tensor(B, dtype=torch.float32, device=DEV)).cpu().numpy()


def decide(df, lab_idx, pred_idx, model="lr"):
    """lab_idx 로 학습 -> pred_idx 의 p. veto(구조 drop 또는 tstd > 34.5) 행은 p=0."""
    X, y = df[FULL].to_numpy(float), df.live.to_numpy()
    veto = ((df.struct_cls == "drop") | (df.tstd > 34.5)).to_numpy()
    tr = [i for i in lab_idx if not veto[i]]
    m = mk(model).fit(X[tr], y[tr])
    p = m.predict_proba(X[pred_idx])[:, 1]
    return np.where(veto[pred_idx], 0.0, p)


def pick(strategy, df, Z, lab, pool, K, rng):
    """pool(인덱스 배열)에서 K 개 선택. Z = 표준화된 특징(거리용)."""
    if len(pool) <= K:
        return list(pool)
    p = decide(df, lab, pool)
    if strategy == "random":
        return list(rng.choice(pool, K, replace=False))
    unc = -np.abs(p - 0.5)
    if strategy == "uncertainty":
        return list(pool[np.argsort(-unc)[:K]])
    if strategy == "likely_first":
        return list(pool[np.argsort(-p)[:K]])
    D = dist_gpu(Z[pool], Z[pool])
    if strategy == "density_unc":
        dens = np.exp(-D / (np.median(D) + 1e-9)).mean(1)
        return list(pool[np.argsort(-(unc + 1) * dens)[:K]])
    if strategy == "cluster_rep":
        km = KMeans(K, n_init=5, random_state=0).fit(Z[pool])
        C = dist_gpu(km.cluster_centers_, Z[pool])
        return list(dict.fromkeys(pool[C.argmin(1)]))[:K]
    if strategy == "committee":
        p2 = decide(df, lab, pool, "lgb")
        import n_signals
        rule = np.array([0.0 if n_signals.fire(dict(rel_db=r, bursts=b)) else 1.0 for r, b in zip(df.rel_db.iloc[pool], df.bursts_per_min.iloc[pool])])
        v = np.var(np.c_[p, p2, rule], axis=1)
        return list(pool[np.argsort(-v)[:K]])
    if strategy in ("kcenter", "unc_div"):
        cand = np.arange(len(pool)) if strategy == "kcenter" else np.argsort(-unc)[:3 * K]
        chosen = [int(cand[np.argmax(unc[cand])])] if strategy == "unc_div" else [int(np.argmax(D.sum(1)))]       # kcenter 시작점: 가장 외딴 점
        while len(chosen) < K:
            dm = D[np.ix_(cand, chosen)].min(1)
            dm[np.isin(cand, chosen)] = -1
            chosen.append(int(cand[np.argmax(dm)]))
        return list(pool[chosen])
    raise KeyError(strategy)


def simulate(df, strategy, K, seed=0):
    rng = np.random.default_rng(seed)
    b9 = df[df.set == "blind9"].copy()
    b9["date"] = b9.group.str.split("|").str[1]
    order = b9.sort_values(["date", "start"]).index.to_numpy()
    chunks = np.array_split(order, ROUNDS)
    seed_idx = df.index[df.set != "blind9"].to_numpy()
    Z = ((df[FULL] - df[FULL].median()) / (df[FULL].std() + 1e-9)).fillna(0).to_numpy(float)
    lab, asked, prec, tags = list(seed_idx), [], [], set()
    arrived = []
    for ch in chunks:
        arrived += list(ch)
        pool = np.array([i for i in arrived if i not in set(lab)])
        if len(pool) == 0:
            continue
        pr = decide(df, lab, pool)
        err = ((pr >= 0.5) != (df.live.to_numpy()[pool] == 1))
        got = pick(strategy, df, Z, lab, pool, K, rng)
        e = {int(i): bool(x) for i, x in zip(pool, err)}
        prec.append(np.mean([e[int(i)] for i in got]))
        base = float(err.mean())
        asked += got
        lab += got
        tags |= {df.tag[i] for i in got if df.live[i] == 0 and df.tag[i]}
        prec[-1] = (prec[-1], base)
    rest = np.array([i for i in order if i not in set(asked)])
    p = decide(df, lab, rest)
    y = df.live.to_numpy()[rest]
    return dict(p_at_k=float(np.mean([a for a, _ in prec])), base_rate=float(np.mean([b for _, b in prec])), auc=float(roc_auc_score(y, p)) if len(set(y)) > 1 else None,
                err_rest=float(((p >= 0.5) != (y == 1)).mean()), n_tags=len(tags), n_asked=len(asked))


def main():
    df = LR.load().reset_index(drop=True)
    out = {}
    for K in (3, 5, 10):
        out[K] = {}
        for st in ("random", "uncertainty", "likely_first", "kcenter", "unc_div", "cluster_rep", "committee", "density_unc"):
            if st == "random":
                rs = [simulate(df, st, K, s) for s in range(200)]
                r = {k: float(np.mean([x[k] for x in rs])) for k in rs[0] if rs[0][k] is not None}
                r["p_at_k_sd"] = float(np.std([x["p_at_k"] for x in rs]))
            else:
                r = simulate(df, st, K)
            out[K][st] = r
            print(f"K={K:2} {st:13} P@K {r['p_at_k']:.2f} (라운드 평균 기저 오류율 {r['base_rate']:.2f}, 배율 {r['p_at_k'] / max(r['base_rate'], 1e-9):.2f}x) | 나머지 AUC {r['auc']:.3f} 오류율 {r['err_rest']:.2f} | 고른 N 유형 {r['n_tags']:.1f}종 (물은 수 {r['n_asked']:.0f})")
    json.dump(out, open(PH / "active.json", "w"), indent=1)


if __name__ == "__main__":
    main()
