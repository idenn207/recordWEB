"""소형 VLM 질의 점수 평가 (E): python run_vlm_eval.py <smol500|...> -- 질문별 AUC/veto(양방향), 6질문 로지스틱, SigLIP2 앙상블과 스태킹"""
import sys, warnings, json
warnings.filterwarnings("ignore")
from evlib import *
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
name = sys.argv[1]; by = "streamer"
df, _ = dataset("b32")
V = np.load(PV / f"vlm_{name}.npz")
keep = [i for i, k in enumerate(df.key) if k.replace("/", "|") in V.files]
df = df.iloc[keep].reset_index(drop=True)
Q = ["web_or_video", "game_scene", "mic_avatar", "big_avatar", "other_streamer", "static_text"]
X = np.stack([V[k.replace("/", "|")] for k in df.key])          # (n, 6, F)
y = (df.live == 0).to_numpy(); g = df[by].to_numpy()
print(f"{name}: {len(df)}곡 (N {y.sum()}, 라이브 {(~y).sum()})")
F = {}
for qi, q in enumerate(Q):
    for agg, f in (("max", X[:, qi].max(1)), ("mean", X[:, qi].mean(1))):
        a = auc(f[y], f[~y]); d = 1 if a >= 0.5 else -1
        r = veto(df, lambda tr, te: (d * f[tr], d * f[te]), by, ms=(0.0, 0.1))
        F[(q, agg)] = d * f
        print(f"{q:14} {agg:4} 방향 {'+' if d>0 else '-'} AUC {max(a,1-a):.3f} | m=0.1 N {r[0.1]['N_hit']}/{r[0.1]['N']} 손실 {r[0.1]['L_lost']} | m=0.0 N {r[0.0]['N_hit']} 손실 {r[0.0]['L_lost']}")
Xs = np.concatenate([X.max(2), X.mean(2)], 1)
def lr(Xf, C=0.3):
    def fn(tr, te):
        mu, sd = Xf[tr].mean(0), Xf[tr].std(0) + 1e-9; Z = (Xf - mu) / sd
        fit = lambda a: LogisticRegression(C=C, max_iter=500, class_weight="balanced").fit(Z[a], y[a])
        s_te = fit(tr).decision_function(Z[te]); s_tr = np.zeros(len(tr))
        for a, b in GroupKFold(5).split(tr, groups=g[tr]):
            s_tr[b] = fit(tr[a]).decision_function(Z[tr[b]])
        return s_tr, s_te
    return fn
r = veto(df, lr(Xs), by, ms=(0.0, 0.1)); print(line("LR 6질문(max+mean)", r), "|", line("", r, 0.1)[-60:])
Zs = np.load(PV / "zs_scores.npz", allow_pickle=True); ks = list(Zs["keys"]); idx = [ks.index(k) for k in df.key]
sig = np.mean([Zs[k] for k in Zs.files if k.startswith("sig2b16|") and k.endswith("|max")], 0)[idx]
r = veto(df, lambda tr, te: (sig[tr], sig[te]), by, ms=(0.0, 0.1)); print(line("SigLIP2 제로샷(같은 곡)", r), "|", line("", r, 0.1)[-60:])
r = veto(df, lr(np.c_[Xs, sig]), by, ms=(0.0, 0.1)); print(line("LR 6질문 + SigLIP2", r), "|", line("", r, 0.1)[-60:])
