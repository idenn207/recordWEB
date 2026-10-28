"""개념 탐지기 (E12~E15): 프롬프트마다 곡 점수(프레임 max/mean) -> 폴드 안에서 그리디로 탐지기 선택(임계 = 학습 라이브 극값 + m x 범위, 학습 라이브 손실 0 + 이득 >= 2) -> hold-out 에서 OR 로 거름.
python run_det.py <별칭> [모드] [by=streamer|group]"""
import json, sys, warnings
warnings.filterwarnings("ignore")
import torch
from evlib import *
import prompts
from embed import load
alias = sys.argv[1]; mode = sys.argv[2] if len(sys.argv) > 2 else "squash"; by = sys.argv[3] if len(sys.argv) > 3 else "streamer"


def concept_matrix(alias, mode, agg):
    df, E = dataset(alias, mode)
    m, _, tok = load(alias)
    names = list(prompts.CONCEPTS)
    with torch.no_grad():
        T = torch.nn.functional.normalize(m.encode_text(tok([prompts.CONCEPTS[n] for n in names]).cuda()).float(), dim=-1).cpu().numpy()
    L = E @ T.T * 100                                                   # (n, 8, p)
    S = L.max(1) if agg == "max" else L.mean(1)
    return df, S, names


def select(S, y, k_max, m, min_gain=2):
    """학습 표본에서 (열, 방향, 임계) 그리디. 방향 +: 점수 > 임계 이면 N"""
    live = S[y == 0]; left = (y == 1).copy(); rules = []
    for _ in range(k_max):
        best = None
        for j in range(S.shape[1]):
            for d in (1, -1):
                v = d * S[:, j]; lv = v[y == 0]
                thr = lv.max() + m * (lv.max() - lv.min())
                hit = (v > thr) & left
                if hit.sum() >= min_gain and (best is None or hit.sum() > best[0]):
                    best = (int(hit.sum()), j, d, thr, hit)
        if best is None:
            break
        rules.append(best[1:4]); left &= ~best[4]
    return rules


def fire(S, rules):
    h = np.zeros(len(S), bool)
    for j, d, t in rules:
        h |= d * S[:, j] > t
    return h


def run(df, S, names, by, m, k_max):
    y = (df.live == 0).to_numpy().astype(int); g = df[by].to_numpy()
    hit = np.zeros(len(df), bool); picked = {}
    for u in np.unique(g):
        te = g == u
        r = select(S[~te], y[~te], k_max, m)
        hit[te] = fire(S[te], r)
        for j, d, t in r:
            picked[names[j] + ("+" if d > 0 else "-")] = picked.get(names[j] + ("+" if d > 0 else "-"), 0) + 1
    Nm = y == 1; dep = df.dep_ok.to_numpy()
    return dict(N_hit=int((hit & Nm).sum()), N=int(Nm.sum()), L_lost=int((hit & ~Nm).sum()), L=int((~Nm).sum()), N_hit_exposed=int((hit & Nm & (dep == 1)).sum()), N_exposed=int((Nm & (dep == 1)).sum()),
                lost=[k[-26:] for k in df.key[hit & ~Nm]], by_tag={t: f"{int((hit & Nm & (df.tag == t).to_numpy()).sum())}/{int((Nm & (df.tag == t).to_numpy()).sum())}" for t in sorted(df.tag[Nm].unique())}, picked=picked)


if __name__ == "__main__":
    out = {}
    for agg in ("max", "mean"):
        df, S, names = concept_matrix(alias, mode, agg)
        for m in (0.0, 0.1, 0.2):
            for k in (1, 3):
                r = run(df, S, names, by, m, k)
                out[f"{agg}/m{m}/k{k}"] = r
                print(f"{alias} {mode} {by} det {agg} m={m} k={k}: N 거름 {r['N_hit']}/{r['N']} (노출 {r['N_hit_exposed']}/{r['N_exposed']}) 라이브 손실 {r['L_lost']}/{r['L']}", flush=True)
    json.dump(out, open(PV / f"res_det_{alias}_{mode}_{by}.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
