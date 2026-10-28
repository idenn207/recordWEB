"""게이트 배치 비교 (E): (1) veto 전용 (2) 점수화: 시각 점수 + 오디오 신호를 로지스틱으로 합침 (3) review 우선순위: 규칙 통과(노출) 후보 안에서 시각 점수의 N/L AUROC 와 상위 k 정밀도.
신호 표 행(154곡)만 사용. python run_place.py [by=streamer]"""
import sys, warnings
warnings.filterwarnings("ignore")
from evlib import *
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
import logo_route as LR
by = sys.argv[1] if len(sys.argv) > 1 else "streamer"
Z = np.load(PV / "zs_scores.npz", allow_pickle=True)
df, _ = dataset("b32")
sc = {k: Z[k] for k in Z.files if k != "keys"}
df["vis"] = np.mean([sc[k] for k in sc if k.endswith("|max")], 0)
sub = df[df.dep_ok.notna()].reset_index(drop=True)
y = (sub.live == 0).to_numpy().astype(int); g = sub[by].to_numpy()
print(f"표본 {len(sub)}곡 N {y.sum()} L {(1-y).sum()} (신호 표 행)")
# (1) veto
v = sub.vis.to_numpy()
for m in (0.0, 0.1):
    r = veto(sub, lambda tr, te: (v[tr], v[te]), by, ms=(m,)); x = r[m]
    print(f"(1) veto 시각 m={m}: AUC {r['auc']:.3f} {r['auc_ci']} N {x['N_hit']}/{x['N']} (노출 {x['N_hit_exposed']}/{x['N_exposed']}) 손실 {x['L_lost']}")
# (2) 점수화: 오디오 신호 + 시각 점수 로지스틱(표준화), 임계는 학습 라이브 최댓값(+m)
A = ["rel_db", "bursts_per_min", "tstd", "speech"]
def lr_fn(cols, C=0.3):
    X = sub[cols].fillna(sub[cols].median()).to_numpy(float)
    def fn(tr, te):
        mu, sd = X[tr].mean(0), X[tr].std(0) + 1e-9; Zs = (X - mu) / sd
        fit = lambda a: LogisticRegression(C=C, max_iter=500, class_weight="balanced").fit(Zs[a], y[a])
        s_te = fit(tr).decision_function(Zs[te]); s_tr = np.zeros(len(tr))
        for a, b in GroupKFold(5).split(tr, groups=g[tr]):
            s_tr[b] = fit(tr[a]).decision_function(Zs[tr[b]])
        return s_tr, s_te
    return fn
for name, cols in (("오디오만(rel_db,bursts,tstd,speech)", A), ("시각만(vis)", ["vis"]), ("오디오+시각", A + ["vis"])):
    for m in (0.0, 0.1):
        r = veto(sub, lr_fn(cols), by, ms=(m,)); x = r[m]
        print(f"(2) 점수화 {name} m={m}: AUC {r['auc']:.3f} {r['auc_ci']} N {x['N_hit']}/{x['N']} (노출 {x['N_hit_exposed']}/{x['N_exposed']}) 손실 {x['L_lost']}")
# (3) review 우선순위: 배포 규칙 통과 후보(dep_ok=1) 안에서 시각 점수가 N 을 위로(= 사람이 나중에) 올리는가
e = sub[sub.dep_ok == 1]
a = auc(e.vis[e.live == 0], e.vis[e.live == 1])
print(f"(3) 우선순위: 규칙 통과 {len(e)}곡(N {int((e.live==0).sum())}, L {int((e.live==1).sum())}) 안에서 시각 점수 AUROC(N>L) {a:.3f}")
o = e.sort_values("vis", ascending=False)
for k in (5, 10):
    print(f"    시각 점수 상위 {k}곡 중 N {int((o.head(k).live==0).sum())}개 (무작위 기대 {k*(e.live==0).mean():.1f}개)")
# 마지막 k 곡(= 시각이 가장 라이브 같음)에서 N 비율
for k in (10, 20):
    print(f"    시각 점수 하위 {k}곡(가장 라이브 같음) 중 N {int((o.tail(k).live==0).sum())}개")
