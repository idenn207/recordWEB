"""축 (c) 학습형 랭커: 후보 신호(오디오/화면/길이) -> 라이브 확률 p, 하드 규칙 veto(구조 규칙 drop, tstd 임계)와 혼합. 현행 규칙 route(신호 선택 hold-out, 배포 임계 표본 내)와
같은 표(cache/audit/signals.csv: 163행 = 라이브 94 + N 69)에서 그룹 hold-out(스트리머 x 방송일 LOGO 50그룹, 스트리머 단위 11그룹)으로 비교한다.
  노출 = veto 안 걸리고 p >= 임계. 임계 방식: p05(고정 0.5) / q0(학습 라이브의 안쪽 교차검증 p 최솟값 = 학습 라이브 손실 0) / q5(5% 분위).
  veto: 구조 규칙(struct_cls==drop) 또는 tstd > 학습 라이브 최댓값+0.01 (logo_route 변형 C 와 같은 hold-out 방식, 현행 34.5 고정이 아님).
  보정: OOF 확률의 Brier, ECE(10구간). 임계 안정성: 폴드별 선택된 임계의 표준편차.
사용: C:/_tools/wt/venv/Scripts/python.exe harness/ranker.py [--by group|streamer] [--boot 1000] -> cache/proto_harness/ranker.json"""
import argparse, json, os, sys, time, warnings
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.lib import *
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
import logo_route as LR
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier, ExtraTreesClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.model_selection import GroupKFold

FULL = ["speech", "bursts_per_min", "sing_std", "moving_frac", "bright_px", "rel_db", "diff_med", "speech_frac", "tstd", "blk", "len", "sing", "music", "sp_mid_frac", "nospeech_max_frac", "ctx_speech", "static_frac", "cut_frac"]
TWO = ["rel_db", "bursts_per_min"]


def mk(name, gpu=False):
    imp = SimpleImputer(strategy="median")
    if name == "lr":
        return make_pipeline(imp, StandardScaler(), LogisticRegression(C=0.3, max_iter=2000, class_weight="balanced"))
    if name == "hgb":
        return HistGradientBoostingClassifier(max_depth=3, learning_rate=0.08, max_iter=120, min_samples_leaf=5, l2_regularization=1.0, random_state=0)
    if name == "rf":
        return make_pipeline(imp, RandomForestClassifier(300, min_samples_leaf=3, max_features="sqrt", class_weight="balanced", random_state=0, n_jobs=4))
    if name == "et":
        return make_pipeline(imp, ExtraTreesClassifier(300, min_samples_leaf=3, class_weight="balanced", random_state=0, n_jobs=4))
    if name == "xgb":
        import xgboost as xgb
        return make_pipeline(imp, xgb.XGBClassifier(n_estimators=120, max_depth=3, learning_rate=0.08, subsample=0.8, colsample_bytree=0.8, reg_lambda=1.0, min_child_weight=2, tree_method="hist", device="cuda" if gpu else "cpu", random_state=0, verbosity=0))
    if name == "lgb":
        import lightgbm as lgb
        return make_pipeline(imp, lgb.LGBMClassifier(n_estimators=120, max_depth=3, learning_rate=0.08, num_leaves=7, min_child_samples=5, subsample=0.8, subsample_freq=1, colsample_bytree=0.8, reg_lambda=1.0, random_state=0, verbose=-1, n_jobs=4))
    raise KeyError(name)


def p_of(m, X):
    return m.predict_proba(X)[:, 1]


def holdout_rank(df, by, model, feats, gpu=False, q=(0.0, 0.05), veto_mode="holdout"):
    """그룹 hold-out. 반환: dict(p=OOF 확률, veto, thr={방식: 행별 임계}, thr_fold={방식: [폴드별 임계]})"""
    n = len(df)
    p, veto = np.zeros(n), np.zeros(n, bool)
    thr = {f"q{int(x * 100)}": np.zeros(n) for x in q}
    thr_fold = {k: [] for k in thr}
    lvs = {}          # 폴드(그룹)별 학습 라이브의 안쪽 교차검증 p (conformal 임계용)
    X, y, g = df[feats].to_numpy(float), df.live.to_numpy(), df[by].to_numpy()
    for grp in np.unique(g):
        te, tr = g == grp, g != grp
        T = df.tstd[tr & (y == 1)].max() + 0.01 if veto_mode == "holdout" else 34.5
        v_all = ((df.struct_cls == "drop") | (df.tstd > T)).to_numpy()
        trm = tr & ~v_all
        m = mk(model, gpu).fit(X[trm], y[trm])
        p[te] = p_of(m, X[te])
        veto[te] = v_all[te]
        # 안쪽 교차검증(학습 그룹 5겹)으로 학습 라이브의 보지 않은 p 분포를 얻어 임계를 정한다
        gi = g[trm]
        ug = np.unique(gi)
        k = min(5, len(ug))
        inner = np.zeros(trm.sum())
        for a, b in GroupKFold(k).split(X[trm], y[trm], gi):
            inner[b] = p_of(mk(model, gpu).fit(X[trm][a], y[trm][a]), X[trm][b])
        lv = inner[y[trm] == 1]
        lvs[grp] = lv
        for kk, qq in zip(thr, q):
            t = float(np.quantile(lv, qq))
            thr[kk][te] = t
            thr_fold[kk].append(t)
    return dict(p=p, veto=veto, thr=thr, thr_fold=thr_fold, lvs=lvs)


def ece(p, y, bins=10):
    e, n = 0.0, len(p)
    for lo in np.linspace(0, 1, bins, endpoint=False):
        m = (p >= lo) & (p < lo + 1 / bins + (1e-9 if lo + 1 / bins >= 1 else 0))
        if m.any():
            e += m.sum() / n * abs(p[m].mean() - y[m].mean())
    return float(e)


def score(df, by, vis, B=1000):
    res = np.where(vis, "ok", "drop")
    out = {}
    for s, mk_ in {"blind9": (df.set == "blind9").to_numpy(), "전체": np.ones(len(df), bool)}.items():
        t = LR.tally(df, res, mk_)
        out[s] = dict(N_expose=t["N_ok"], n_N=t["n_N"], L_loss=t["L_weak"] + t["L_drop"], n_L=t["n_L"], ci=LR.boot(df, res, by, mk_, B))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--by", default="group", choices=["group", "streamer"])
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--gpu", action="store_true")
    a = ap.parse_args()
    df = LR.load()
    df["streamer"] = df.name
    by = a.by
    y = df.live.to_numpy()
    out = dict(by=by, n=len(df), n_live=int(y.sum()), groups=int(df[by].nunique()))
    # 현행 규칙 비교선: 신호 선택 hold-out(D, m=0.1), tstd 재추정(C), 배포 규칙 표본 내
    R = {}
    for v, m in (("C", 0.0), ("D", 0.0), ("D", 0.1)):
        res, folds = LR.holdout(df, by, v, m)
        for s, mk_ in {"blind9": (df.set == "blind9").to_numpy(), "전체": np.ones(len(df), bool)}.items():
            t = LR.tally(df, res, mk_)
            R.setdefault(f"규칙 {v} m={m}", {})[s] = dict(N_expose=t["N_ok"], n_N=t["n_N"], L_loss=t["L_weak"] + t["L_drop"], n_L=t["n_L"], ci=LR.boot(df, res, by, mk_, a.boot))
    dep, _ = LR.deployed(df)
    R["규칙 배포 임계(표본 내, 과적합)"] = {s: dict(N_expose=t["N_ok"], n_N=t["n_N"], L_loss=t["L_drop"], n_L=t["n_L"]) for s, t in dep.items()}
    out["rules"] = R
    for k, v in R.items():
        print(f"{k:32}", " | ".join(f"{s}: N노출 {x['N_expose']}/{x['n_N']} 라이브손실 {x['L_loss']}/{x['n_L']}" + (f" [N {x['ci']['N_ok'][0]:.0%}-{x['ci']['N_ok'][1]:.0%}]" if 'ci' in x else "") for s, x in v.items()))
    models = [("lr", FULL), ("lr", TWO), ("hgb", FULL), ("rf", FULL), ("et", FULL), ("xgb", FULL), ("lgb", FULL)]
    M = {}
    for name, feats in models:
        key = f"{name}{'-2' if feats is TWO else ''}"
        t = time.perf_counter()
        H = holdout_rank(df, by, name, feats, gpu=a.gpu and name == "xgb")
        dt = time.perf_counter() - t
        score_p = np.where(H["veto"], 0.0, H["p"])
        ok = ~H["veto"]
        info = dict(sec=round(dt, 1), auc_all=round(float(roc_auc_score(y, score_p)), 3), auc_nonveto=round(float(roc_auc_score(y[ok], H["p"][ok])), 3),
                    brier=round(float(brier_score_loss(y[ok], H["p"][ok])), 3), ece=round(ece(H["p"][ok], y[ok]), 3), veto_N=int((H["veto"] & (y == 0)).sum()), veto_L=int((H["veto"] & (y == 1)).sum()))
        info["p05"] = score(df, by, ~H["veto"] & (H["p"] >= 0.5), a.boot)
        for k in H["thr"]:
            info[k] = score(df, by, ~H["veto"] & (H["p"] >= H["thr"][k]), a.boot)
            tf = np.array(H["thr_fold"][k])
            info[k]["thr_std"], info[k]["thr_mean"] = round(float(tf.std()), 3), round(float(tf.mean()), 3)
        M[key] = info
        print(f"{key:7} {dt:5.1f}s AUC {info['auc_all']} (veto 제외 {info['auc_nonveto']}) Brier {info['brier']} ECE {info['ece']} veto N {info['veto_N']} L {info['veto_L']}")
        for k in ("p05", "q0", "q5"):
            x = info[k]
            print(f"   {k:3}", " | ".join(f"{s}: N노출 {v['N_expose']}/{v['n_N']} 라이브손실 {v['L_loss']}/{v['n_L']}" for s, v in x.items() if s in ("blind9", "전체")), f"임계 평균 {x.get('thr_mean')} 표준편차 {x.get('thr_std')}" if k != "p05" else "")
        # 혼합: 규칙(D m=0.1 hold-out)이 노출시키고 모델도 노출(AND) / 둘 중 하나(OR), q0 임계
        rres, _ = LR.holdout(df, by, "D", 0.1)
        rule_vis = rres == "ok"
        mv = ~H["veto"] & (H["p"] >= H["thr"]["q0"])
        info["AND(q0)"] = score(df, by, rule_vis & mv, a.boot)
        info["OR(q0)"] = score(df, by, rule_vis | mv, a.boot)
        for k in ("AND(q0)", "OR(q0)"):
            x = info[k]
            print(f"   {k:7}", " | ".join(f"{s}: N노출 {v['N_expose']}/{v['n_N']} 라이브손실 {v['L_loss']}/{v['n_L']}" for s, v in x.items() if s in ("blind9", "전체")))
        np.save(PH / f"ranker_oof_{by}_{key}.npy", np.c_[H["p"], H["veto"]])
    out["models"] = M
    json.dump(out, open(PH / f"ranker_{by}.json", "w"), ensure_ascii=False, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))


if __name__ == "__main__":
    main()
