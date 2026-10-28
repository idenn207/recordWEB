"""visual 트랙 평가 라이브러리. 곡 204개(라이브 134 / N 70), 곡당 프레임 8장 임베딩, 그룹 hold-out(스트리머 x 방송일 / 스트리머).
점수 s = 'N 같음'(클수록 N). veto 평가: hold-out 그룹마다 학습 그룹의 라이브 점수 최댓값 + m x 범위를 임계로 하고, 임계 초과를 거른다(라이브 손실 0 이 목표, m 은 여유).
지표: AUROC(전체 hold-out 점수 모아서) + 그룹 부트스트랩 구간, veto 거름 N 수, 라이브 손실, 유형별 거름, 배포 규칙 통과 N(노출) 중 거름 수.
shortcut: 스트리머 11명 표본이라 hold-out 구간이 넓다. 점추정 하나로 읽지 말고 구간으로 읽는다."""
import json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments")); os.chdir(ROOT)
import numpy as np, pandas as pd

PV = Path("cache/proto_visual")


def manifest():
    m = pd.DataFrame(json.load(open(PV / "manifest.json", encoding="utf8")))
    m["streamer"] = m.group.str.split("|").str[0]
    return m


def load_emb(alias, mode="squash"):
    z = np.load(PV / f"emb_{alias}_{mode}.npz")
    return {k.replace("|", "/"): z[k] for k in z.files}


def dataset(alias="b32", mode="squash"):
    """(df, E) df = manifest 중 프레임이 있는 곡, E = (n, 8, D) 임베딩. 배포 규칙 통과 여부 dep_ok(신호 표에 있는 행만 판단, 없으면 NaN)도 붙인다."""
    m, Z = manifest(), load_emb(alias, mode)
    m = m[m.key.isin(Z)].reset_index(drop=True)
    E = np.stack([Z[k] for k in m.key])
    m = m.merge(deployed_pass(), on="key", how="left")
    return m, E


_DEP = None


def deployed_pass():
    """신호 표(cache/audit/signals.csv) 행마다 배포 규칙(구조 규칙 + tstd>34.5 + n_signals 두 신호)이 거르는지. dep_ok=1 이면 규칙을 통과해 사람에게 노출되는 후보."""
    global _DEP
    if _DEP is None:
        import n_signals
        from scene_multi import P as MP
        s = pd.read_csv("cache/audit/signals.csv", dtype={"vno": str}, keep_default_na=True)
        fl = np.array([bool(n_signals.fire(dict(rel_db=r, bursts=b))) for r, b in zip(s.rel_db.fillna(0), s.bursts_per_min.fillna(0))])
        base = ((s.struct_cls == "drop") | (s.tstd > MP["motion"])).to_numpy()
        s["dep_ok"] = (~(base | fl)).astype(float)
        _DEP = s[["key", "dep_ok", "tstd", "blk", "speech", "rel_db", "bursts_per_min", "sing_std", "bright_px", "diff_med", "moving_frac"]]
    return _DEP


def auc(pos, neg):
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    if not len(pos) or not len(neg):
        return np.nan
    g = (pos[:, None] > neg[None]).mean() + 0.5 * (pos[:, None] == neg[None]).mean()
    return float(g)


def gboot(df, score, B=1000, seed=0):
    """AUROC(N 이 양성)의 그룹(스트리머 x 방송일) 부트스트랩 95% 구간"""
    rng = np.random.default_rng(seed)
    g = df.group.to_numpy(); ug = np.unique(g); idx = {u: np.flatnonzero(g == u) for u in ug}
    y = (df.live == 0).to_numpy()
    out = []
    for _ in range(B):
        ii = np.concatenate([idx[u] for u in rng.choice(ug, len(ug))])
        if y[ii].any() and (~y[ii]).any():
            out.append(auc(score[ii][y[ii]], score[ii][~y[ii]]))
    return np.percentile(out, [2.5, 97.5]).round(3).tolist()


def veto(df, score_fn, by="group", ms=(0.0, 0.1), inner=False):
    """score_fn(train_idx, test_idx) -> (학습 점수(임계용, 학습 안 한 값이어야 함), 시험 점수). 모든 점수는 클수록 N.
    반환 dict: oof(hold-out 점수), 각 m 에 대해 거른 N, 손실 라이브, 유형별."""
    grp = df[by if by != "group" else "group"].to_numpy()
    y = (df.live == 0).to_numpy()
    oof = np.full(len(df), np.nan)
    thr = {m: np.full(len(df), np.nan) for m in ms}
    for u in np.unique(grp):
        te = np.flatnonzero(grp == u); tr = np.flatnonzero(grp != u)
        s_tr, s_te = score_fn(tr, te)
        oof[te] = s_te
        sl = s_tr[~y[tr]]                                    # 학습 라이브 점수
        for m in ms:
            thr[m][te] = sl.max() + m * (sl.max() - sl.min())
    res = dict(oof=oof, auc=auc(oof[y], oof[~y]), auc_ci=gboot(df, oof))
    dep = df.dep_ok.to_numpy()
    for m in ms:
        hit = oof > thr[m]
        res[f"hit{m}"] = hit
        res[m] = dict(N_hit=int((hit & y).sum()), N=int(y.sum()), L_lost=int((hit & ~y).sum()), L=int((~y).sum()),
                      N_hit_exposed=int((hit & y & (dep == 1)).sum()), N_exposed=int((y & (dep == 1)).sum()),
                      lost=[k[-26:] for k in df.key[hit & ~y]],
                      by_tag={t: f"{int((hit & y & (df.tag == t).to_numpy()).sum())}/{int((y & (df.tag == t).to_numpy()).sum())}" for t in sorted(df.tag[y].unique())})
    return res


def line(name, r, m=0.0):
    x = r[m]
    return (f"{name:34} AUC {r['auc']:.3f} {r['auc_ci']} | m={m}: N 거름 {x['N_hit']}/{x['N']} (노출 N {x['N_hit_exposed']}/{x['N_exposed']}) 라이브 손실 {x['L_lost']}/{x['L']}")


if __name__ == "__main__":
    df, E = dataset("b32")
    print(len(df), df.live.sum(), df.dep_ok.notna().sum(), "dep_ok 노출 N", int(((df.live == 0) & (df.dep_ok == 1)).sum()))
    # 자가검사: 라벨 누수 점수(정답 그대로)는 AUC 1, 무작위는 0.5 근처, 손실 0
    y = (df.live == 0).to_numpy().astype(float)
    r = veto(df, lambda tr, te: (y[tr], y[te]))
    assert r["auc"] == 1.0 and r[0.0]["L_lost"] == 0 and r[0.0]["N_hit"] == r[0.0]["N"] - 0 or r[0.0]["N_hit"] > 0, r[0.0]
    rr = np.random.default_rng(0).random(len(df))
    r = veto(df, lambda tr, te: (rr[tr], rr[te]))
    assert 0.35 < r["auc"] < 0.65, r["auc"]
    print("ok", line("무작위", r))
