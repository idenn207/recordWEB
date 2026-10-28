"""N 신호 후보(n_asr 전사 특징 + asr_pitch 피치 특징)의 분리력: blind9 곡(N 55 / 라이브 49)에서 단독 AUROC(부트스트랩 95%) + 유형별 + 기존 규칙이 못 거른 N 에 대한 추가 포착.
  python experiments/asr_n_eval.py [--tx t_small_auto] [--boot 1000]
추가 포착 기준: 기존 배포 신호(n_signals: rel_db<-5.7 | bursts>2.1)가 거르지 못한 N 중, 임계(= 라이브 극값 + 0.1 x 범위, 라이브 손실 0 방향)로 새로 거르는 수. 표본 내 임계라 과적합 참고값이다."""
import sys, os, json, argparse
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT); sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
import numpy as np, pandas as pd
import asr_bounds as B, n_asr
from asr_run import groups


def auc(pos, neg):
    """P(pos > neg) + 0.5 P(=): 행렬 비교(GPU 불필요한 크기)"""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    return float(((pos[:, None] > neg[None]) + 0.5 * (pos[:, None] == neg[None])).mean())


def table(tx):
    pit = pd.read_csv(ROOT / "cache/proto_asr/pitch.csv").set_index("gid")
    sig = pd.read_csv(ROOT / "cache/audit/signals.csv", dtype={"vno": str}, keep_default_na=True, na_values=[""])
    rows = []
    for g in groups():
        d = B.load_tx(tx, g["gid"])
        if not d:
            continue
        f = n_asr.features(d, B.scores(g["vno"]), *g["base"])
        m = sig[(sig.vno == g["vno"]) & (abs(sig.start - g["base"][0]) < 1)]
        r = dict(gid=g["gid"], vno=g["vno"], tag=g["tag"], N=int(g["lab"] == "N"), **f)
        if g["gid"] in pit.index:
            r.update({k: pit.loc[g["gid"], k] for k in ("active_frac", "voiced_frac", "poly_frac", "stem_rel_db")})
        if len(m):
            r.update(rel_db=m.iloc[0].rel_db, bursts=m.iloc[0].bursts_per_min, speech=m.iloc[0].speech)
        rows.append(r)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--tx", default="t_small_auto"); ap.add_argument("--boot", type=int, default=1000)
    a = ap.parse_args()
    df = table(a.tx)
    feats = [c for c in df.columns if c not in ("gid", "vno", "tag", "N")]
    rng = np.random.default_rng(0)
    print(f"행 {len(df)} (N {int(df.N.sum())}, 라이브 {int((1 - df.N).sum())}), 전사 {a.tx}")
    print(f"{'특징':12} {'AUROC(N 이 큰 쪽)':>18} {'95% 구간':>14} | 유형별 AUROC(N 유형 vs 라이브)")
    res = {}
    for c in feats:
        x = df[["N", "tag", "vno", c]].dropna()
        if x.N.nunique() < 2:
            continue
        A = auc(x[x.N == 1][c], x[x.N == 0][c])
        # 방송(vno) 단위 부트스트랩
        vnos = x.vno.unique(); bs = []
        for _ in range(a.boot):
            y = pd.concat([x[x.vno == v] for v in rng.choice(vnos, len(vnos))])
            if y.N.nunique() == 2:
                bs.append(auc(y[y.N == 1][c], y[y.N == 0][c]))
        lo, hi = np.percentile(bs, [2.5, 97.5])
        bt = {t: round(auc(x[x.tag == t][c], x[x.N == 0][c]), 2) for t in sorted(x[x.N == 1].tag.unique()) if (x.tag == t).sum() >= 3}
        res[c] = dict(auc=A, lo=lo, hi=hi, by_tag=bt)
        print(f"{c:12} {A:18.2f} [{lo:.2f},{hi:.2f}] | {bt}")
    # 추가 포착: 기존 신호가 못 거른 N
    d2 = df.dropna(subset=["rel_db", "bursts"])
    rest = d2[(d2.N == 1) & (d2.rel_db >= -5.7) & (d2.bursts <= 2.1)]
    live = d2[d2.N == 0]
    print(f"\n기존 신호(rel_db/bursts)가 못 거른 N {len(rest)}/{int(d2.N.sum())} (표 겹침 {len(d2)}행), 라이브 {len(live)}")
    for c in feats:
        if c in ("rel_db", "bursts", "speech") or c not in d2 or d2[c].isna().all():
            continue
        lv = live[c].dropna()
        if len(lv) < 5:
            continue
        sgn = 1 if res.get(c, {}).get("auc", .5) >= .5 else -1        # N 이 큰 쪽이면 라이브 최댓값 위가 N
        rngv = lv.max() - lv.min()
        th = lv.max() + .1 * rngv if sgn > 0 else lv.min() - .1 * rngv
        hit = rest[(rest[c] > th) if sgn > 0 else (rest[c] < th)]
        lost = int(((live[c] > th) if sgn > 0 else (live[c] < th)).sum())
        print(f"  {c:12} 방향 {'N 큼' if sgn > 0 else 'N 작음'} 임계 {th:8.3f} 추가 포착 {len(hit):2}/{len(rest)}  라이브 손실 {lost}/{len(live)}  {dict(hit.tag.value_counts())}")
    df.to_csv(ROOT / "cache/proto_asr/n_features.csv", index=False)
    print("\n[라이브 하위/상위 분위수 임계에서의 포착-손실 곡선: 기존 신호가 못 거른 N 대상]")
    for c in feats:
        if c in ("rel_db", "bursts", "speech") or c not in d2 or d2[c].isna().all() or res.get(c, {}).get("auc", .5) in (None,):
            continue
        lv = live[c].dropna()
        if len(lv) < 5:
            continue
        sgn = 1 if res[c]["auc"] >= .5 else -1
        out = []
        for q in (0, 2.5, 5, 10):
            th = np.percentile(lv, 100 - q) if sgn > 0 else np.percentile(lv, q)
            hit = int(((rest[c] > th) if sgn > 0 else (rest[c] < th)).sum())
            lost = int(((live[c] > th) if sgn > 0 else (live[c] < th)).sum())
            out.append(f"q{q}%: 포착 {hit}/{len(rest)} 손실 {lost}/{len(live)}")
        if max(res[c]["auc"], 1 - res[c]["auc"]) > .65:
            print(f"  {c:12} {'N 큼' if sgn > 0 else 'N 작음'} | " + " | ".join(out))
