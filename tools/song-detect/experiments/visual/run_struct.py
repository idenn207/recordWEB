"""구조 특징 단독 veto + 표준화 로지스틱(E13~E14). python run_struct.py [by]"""
import json, sys, warnings
warnings.filterwarnings("ignore")
from evlib import *
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
by = sys.argv[1] if len(sys.argv) > 1 else "streamer"
df, _ = dataset("b32")
S = pd.read_csv(PV / "struct.csv"); df = df.merge(S, on="key", how="left")
feats = [c for c in S.columns if c != "key"]
y = (df.live == 0).to_numpy().astype(int); g = df[by].to_numpy()
res = {}
print("== 단독 특징(방향은 학습 AUC 로 결정하지 않고 양방향 중 hold-out AUC 가 높은 쪽만 보고: 방향 선택 누수 주의 -> 표시용)")
for f in feats:
    v = df[f].to_numpy(float)
    a = auc(v[y == 1], v[y == 0]); d = 1 if a >= 0.5 else -1                 # 표시용 방향(전체 AUC): 단독 특징의 효과 크기 확인용
    r = veto(df, lambda tr, te: (d * v[tr], d * v[te]), by, ms=(0.0,))
    res[f] = dict(auc=max(a, 1 - a), N_hit=r[0.0]["N_hit"], L_lost=r[0.0]["L_lost"], hit_exposed=r[0.0]["N_hit_exposed"])
    print(f"{f:14} AUC {max(a, 1 - a):.3f} 방향 {'+' if d > 0 else '-'} | N 거름 {r[0.0]['N_hit']}/{r[0.0]['N']} 손실 {r[0.0]['L_lost']}")
X = df[feats].fillna(0).to_numpy(float)
def lr_fn(X, C):
    def fn(tr, te):
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9
        Z = (X - mu) / sd
        fit = lambda a: LogisticRegression(C=C, max_iter=500, class_weight="balanced").fit(Z[a], y[a])
        s_te = fit(tr).decision_function(Z[te]); s_tr = np.zeros(len(tr))
        for a, b in GroupKFold(5).split(tr, groups=g[tr]):
            s_tr[b] = fit(tr[a]).decision_function(Z[tr[b]])
        return s_tr, s_te
    return fn
for C in (0.03, 0.3, 3):
    r = veto(df, lr_fn(X, C), by, ms=(0.0, 0.1, 0.2))
    res[f"LR struct C={C}"] = {k: v for k, v in r.items() if k != "oof" and not str(k).startswith("hit")}
    print(line(f"LR struct C={C} ({by})", r), "|", line("", r, 0.1)[-62:])
# 기존 신호(표본 154곡: 신호 표에 있는 행)
sub = df[df.dep_ok.notna()].reset_index(drop=True)
y2 = (sub.live == 0).to_numpy().astype(int)
for f in ["tstd", "blk", "bright_px", "diff_med", "moving_frac", "rel_db", "bursts_per_min"]:
    v = sub[f].to_numpy(float)
    a = auc(v[y2 == 1], v[y2 == 0]); d = 1 if a >= 0.5 else -1
    r = veto(sub, lambda tr, te: (d * np.nan_to_num(v[tr]), d * np.nan_to_num(v[te])), by, ms=(0.0,))
    print(f"[기존신호 154곡] {f:14} AUC {max(a, 1 - a):.3f} | N 거름 {r[0.0]['N_hit']}/{r[0.0]['N']} 손실 {r[0.0]['L_lost']}")
json.dump(res, open(PV / f"res_struct_{by}.json", "w", encoding="utf8"), ensure_ascii=False, indent=1, default=str)
