"""선형 프로브/kNN/제로샷 점수 함수 모음 (evlib.veto 에 넣는다). 모두 클수록 N."""
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold


def song_feat(E, agg="mean"):
    """(n, 8, D) -> (n, D*k)"""
    if agg == "mean":
        x = E.mean(1)
    elif agg == "meanstd":
        x = np.concatenate([E.mean(1), E.std(1)], 1)
    elif agg == "maxmin":
        x = np.concatenate([E.max(1), E.min(1)], 1)
    elif agg == "med":
        x = np.median(E, 1)
    else:
        raise ValueError(agg)
    return x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-9) if agg in ("mean", "med") else x


def _fit_lr(X, y, C):
    return LogisticRegression(C=C, max_iter=300, class_weight="balanced").fit(X, y)


def lr_song(E, y, groups, C=1.0, agg="mean", k_inner=5):
    """곡 단위 로지스틱. 임계용 학습 점수는 학습 그룹 안 GroupKFold(k_inner)의 hold-out 점수(과적합 점수로 임계를 잡지 않으려고)."""
    X = song_feat(E, agg)
    def fn(tr, te):
        m = _fit_lr(X[tr], y[tr], C)
        s_te = m.decision_function(X[te])
        s_tr = np.zeros(len(tr))
        for a, b in GroupKFold(min(k_inner, len(set(groups[tr])))).split(tr, groups=groups[tr]):
            s_tr[b] = _fit_lr(X[tr][a], y[tr][a], C).decision_function(X[tr][b])
        return s_tr, s_te
    return fn


def lr_frame(E, y, groups, C=1.0, agg="mean", k_inner=5):
    """프레임 단위 로지스틱(프레임이 곡 라벨 상속) -> 곡 점수 = 프레임 점수의 mean/max/p75"""
    n, T, D = E.shape
    F = E.reshape(-1, D); yy = np.repeat(y, T); gg = np.repeat(groups, T)
    red = dict(mean=lambda s: s.mean(1), max=lambda s: s.max(1), p75=lambda s: np.percentile(s, 75, axis=1), min=lambda s: s.min(1))[agg]
    def fn(tr, te):
        itr = (tr[:, None] * T + np.arange(T)).ravel()
        m = _fit_lr(F[itr], yy[itr], C)
        s_te = red(m.decision_function(E[te].reshape(-1, D)).reshape(len(te), T))
        s_tr = np.zeros(len(tr))
        for a, b in GroupKFold(min(k_inner, len(set(groups[tr])))).split(tr, groups=groups[tr]):
            ia = (tr[a][:, None] * T + np.arange(T)).ravel()
            s_tr[b] = red(_fit_lr(F[ia], yy[ia], C).decision_function(E[tr[b]].reshape(-1, D)).reshape(len(b), T))
        return s_tr, s_te
    return fn


def knn(E, y, groups, k=5, agg="mean"):
    """곡 임베딩 코사인 kNN: 점수 = 가장 가까운 k 개 중 N 비율 - 라이브 비율 가중(유사도 합 차이). 학습 점수는 학습 안에서 leave-one-group-out 이웃"""
    X = song_feat(E, agg)
    S = X @ X.T
    def score(rows, cols, grp_excl):
        out = []
        for i in rows:
            ok = np.array([c for c in cols if groups[c] != groups[i]]) if grp_excl else cols
            s = S[i, ok]; o = np.argsort(-s)[:k]
            w = np.exp(s[o] * 10)
            out.append((w * (2 * y[ok][o] - 1)).sum() / w.sum())
        return np.array(out)
    return lambda tr, te: (score(tr, tr, True), score(te, tr, False))


def zeroshot(E, T_n, T_l, agg="mean", temp=100.0):
    """텍스트 임베딩 T_n(N 개념 목록), T_l(라이브 개념 목록) 로 프레임별 (max N 로짓 - max 라이브 로짓) -> 곡 집계. 학습 없음: 학습 점수도 같은 값"""
    ln = E @ T_n.T * temp; ll = E @ T_l.T * temp                      # (n, T, p)
    d = ln.max(2) - ll.max(2)                                          # (n, T)
    s = dict(mean=d.mean(1), max=d.max(1), med=np.median(d, 1), min=d.min(1))[agg]
    return lambda tr, te: (s[tr], s[te])
