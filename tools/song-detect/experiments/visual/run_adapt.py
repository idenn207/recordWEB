"""E: 교차모달 적응(텍스트 임베딩을 학습 표본으로 추가한 선형 프로브, Lin et al. 2023 초록 수준 확인) + Tip-Adapter 식 캐시(제로샷 + 학습 프레임 유사도 가중 투표; 공식은 초록에 없어 원문 수식 미확인, 아래는 우리 구현)
python run_adapt.py <별칭> [by]"""
import json, sys, warnings
warnings.filterwarnings("ignore")
import torch
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from evlib import *
import prompts, probes as P
from embed import load
alias = sys.argv[1]; by = sys.argv[2] if len(sys.argv) > 2 else "streamer"
df, E = dataset(alias)
m, _, tok = load(alias)
tx = lambda ts: torch.nn.functional.normalize(m.encode_text(tok(ts).cuda()).float(), dim=-1).detach().cpu().numpy()
N_txt = sum([s["N"] for s in prompts.SETS.values() if s is not prompts.SETS["D_only_N"]], []); L_txt = sum([s["L"] for s in prompts.SETS.values() if s is not prompts.SETS["D_only_N"]], [])
Tn, Tl = tx(N_txt), tx(L_txt)
y = (df.live == 0).astype(int).to_numpy(); g = df[by].to_numpy(); n, T, D = E.shape
F = E.reshape(-1, D); yy = np.repeat(y, T)
Xt = np.r_[Tn, Tl]; yt = np.r_[np.ones(len(Tn)), np.zeros(len(Tl))]


def xmodal(C, wt):
    def fit(idx):
        ii = (idx[:, None] * T + np.arange(T)).ravel()
        X = np.r_[F[ii], np.repeat(Xt, wt, 0)]; yv = np.r_[yy[ii], np.repeat(yt, wt)]
        return LogisticRegression(C=C, max_iter=400, class_weight="balanced").fit(X, yv)
    def fn(tr, te):
        sc = lambda mdl, idx: mdl.decision_function(E[idx].reshape(-1, D)).reshape(len(idx), T).max(1)
        s_te = sc(fit(tr), te); s_tr = np.zeros(len(tr))
        for a, b in GroupKFold(5).split(tr, groups=g[tr]):
            s_tr[b] = sc(fit(tr[a]), tr[b])
        return s_tr, s_te
    return fn


def tip(alpha, beta):
    zs = (E @ Tn.T).max(2).max(1) * 100 - (E @ Tl.T).max(2).max(1) * 100
    def cache(src, dst):                                         # dst 곡마다: 학습 프레임과의 유사도 가중 (N 프레임 - 라이브 프레임) 투표
        S = E[dst].reshape(-1, D) @ F[(src[:, None] * T + np.arange(T)).ravel()].T
        w = np.exp(-beta * (1 - S)); lab = np.repeat(2 * y[src] - 1, T)
        return ((w * lab).sum(1) / w.sum(1)).reshape(len(dst), T).max(1)
    def fn(tr, te):
        s_tr = np.zeros(len(tr))
        for a, b in GroupKFold(5).split(tr, groups=g[tr]):
            s_tr[b] = zs[tr[b]] + alpha * cache(tr[a], tr[b])
        return s_tr, zs[te] + alpha * cache(tr, te)
    return fn


out = {}
for name, fn in [("xmodal C=1 w=1", xmodal(1.0, 1)), ("xmodal C=1 w=5", xmodal(1.0, 5)), ("xmodal C=0.1 w=5", xmodal(0.1, 5)), ("tip a=5 b=5", tip(5, 5)), ("tip a=20 b=10", tip(20, 10)), ("tip a=50 b=20", tip(50, 20))]:
    r = veto(df, fn, by, ms=(0.0, 0.1, 0.2)); out[name] = {k: v for k, v in r.items() if k != "oof" and not str(k).startswith("hit")}
    print(line(f"{alias} {name} ({by})", r), "|", line("", r, 0.1)[-62:], flush=True)
json.dump(out, open(PV / f"res_adapt_{alias}_{by}.json", "w", encoding="utf8"), ensure_ascii=False, indent=1, default=str)
