"""N 유형별로 쓸 수 있는 신호 탐색(읽기 전용): 후보마다 오디오/화면/메타 특징을 뽑아 유형별 AUC, 라이브 손실 0 조건 재현율(+ 스트리머 단위 LOSO)을 표로.
입력은 cache/detect/<이름>.scores.npy(열 Singing, Speech, Music, 0.5초), data/vod/**.wav, cache/scene_pool.npz(키프레임), data/nas_index.json/vod_meta.json(제목).
라이브 = blind5/6/9/78 의 라이브 전부(L+B). 유형 = labels 의 tag. 한 특징이 어떤 유형을 '라이브 손실 0' 으로 얼마나 거르는지:
  recall0      라이브 전체 범위(최소~최대) 밖에 있는 해당 유형 N 의 비율(방향은 AUC>0.5 쪽, 같은 표본에서 정한 값 = 낙관적)
  loso_rec/lost  스트리머 s 의 라이브/N 을 평가할 때 임계값을 나머지 스트리머 라이브 범위로만 정함 -> 해당 유형 N 거름 수 / 뺀 스트리머 라이브 손실 수
사용: python experiments/loso_signals.py [출력=data/review/blind9/audit/loso_signals.json]"""
import json, os, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))
os.chdir(ROOT)
import numpy as np
import scene_pool
import loso_n
from snap import pcm_of

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "data/review/blind9/audit/loso_signals.json")
SR = 16000


def runs(m):
    """bool 배열의 True 연속 구간 (시작, 길이) 목록"""
    out, i = [], 0
    while i < len(m):
        if m[i]:
            j = i
            while j < len(m) and m[j]:
                j += 1
            out.append((i, j - i))
            i = j
        else:
            i += 1
    return out


def audio_feats(a, s, e):
    """a = scores(0.5초 x [Singing, Speech, Music]). 구간과 앞뒤 60초 맥락의 말/노래/음악 분포."""
    i0, i1 = int(s * 2), min(int(e * 2), len(a))
    x = a[i0:i1]
    n = len(x)
    sg, sp, mu = x[:, 0], x[:, 1], x[:, 2]
    f = dict(sing=sg.mean(), speech=sp.mean(), music=mu.mean(), speech_frac=(sp > 0.3).mean())
    third = np.array_split(sp, 3)
    f["sp_front"], f["sp_mid"], f["sp_back"] = (t.mean() for t in third)
    mid = slice(int(n * 0.2), int(n * 0.8))
    f["sp_mid_frac"] = (sp[mid] > 0.3).mean()                 # 노래 한가운데(앞뒤 20% 제외)의 말소리 비율
    f["sp_mid_music"] = ((sp[mid] > 0.3) & (mu[mid] > 0.5)).mean()    # 음악이 깔린 채 말하는 비율(노래 중 멘트)
    b = runs(sp > 0.5)
    b = [(i, l) for i, l in b if l >= 2]                      # 1초 이상 말 덩어리
    f["bursts_per_min"] = len(b) / (n / 120)
    f["burst_max_s"] = max([l for _, l in b], default=0) / 2
    ns = runs(sp < 0.3)
    f["nospeech_max_frac"] = max([l for _, l in ns], default=0) / n     # 가장 긴 무말 구간 비율
    f["sing_low_frac"] = (sg < 0.2).mean()
    f["sing_std"] = sg.std()
    f["music_low_frac"] = (mu < 0.3).mean()
    for nm, (c0, c1) in dict(before=(max(0, i0 - 120), i0), after=(i1, min(len(a), i1 + 120))).items():
        c = a[c0:c1]
        f[f"ctx_speech_{nm}"] = c[:, 1].mean() if len(c) > 10 else np.nan
        f[f"ctx_music_{nm}"] = c[:, 2].mean() if len(c) > 10 else np.nan
        f[f"ctx_sing_{nm}"] = c[:, 0].mean() if len(c) > 10 else np.nan
    f["ctx_speech"] = np.nanmean([f["ctx_speech_before"], f["ctx_speech_after"]])
    return f


def screen_feats(fr, d):
    """fr = 키프레임(48x27 회색, 키프레임 간격은 GOP 이라 불균일). d = 풀 항목별 최근접 거리 행렬(없으면 None)."""
    if len(fr) < 3:
        return {}
    f = {}
    sd = fr.std(0)
    f["tstd"] = float(sd.mean() * 255)
    f["static_frac"] = float((sd < 3 / 255).mean())           # 거의 안 변하는 픽셀(오버레이/UI 고정부)
    f["moving_frac"] = float((sd > 20 / 255).mean())          # 크게 변하는 픽셀
    f["blk"] = float(((fr < 14 / 255).mean(0) > 0.9).mean())
    f["bright"] = float(fr.mean())
    df = np.abs(np.diff(fr, axis=0)).mean(1)
    f["diff_med"] = float(np.median(df))
    f["diff_p90"] = float(np.percentile(df, 90))
    f["cut_frac"] = float((df > 0.15).mean())                 # 화면이 크게 바뀐 키프레임 간 비율(레이아웃/장면 전환)
    f["kf_per_min"] = len(fr)                                 # 후보 길이로 나누기 전 원값(아래에서 정규화)
    return f


def pool_dist(r, meta, d):
    """장면 풀 거리(같은 방송은 뺌): d_live 모든 스트리머 라이브 풀, d_neg 오탐 풀, d_same 같은 스트리머 라이브(다른 방송), d_margin = d_live - d_neg(음수일수록 라이브 풀에 가까움).
    shortcut: 풀의 N 라벨은 이 표본 자체라 d_neg 는 낙관적(같은 유형 다른 방송 N 이 풀에 남음). d_same 은 같은 스트리머 다른 방송 라이브만."""
    m = r["pm"]
    if m is None or d is None:
        return {}
    keep = lambda o: not (o["videoNo"] == m["videoNo"] or (o["name"] == m["name"] and o.get("date") and o.get("date") == m.get("date")))
    col = lambda f: np.array([j for j, o in enumerate(meta) if keep(o) and f(o)], int)
    med = lambda c: float(np.median(d[:, c].min(1))) if len(c) else np.nan
    dl, dn, ds = med(col(lambda o: o["live"])), med(col(lambda o: not o["live"])), med(col(lambda o: o["live"] and o["name"] == m["name"]))
    return dict(d_live=dl, d_neg=dn, d_same=ds, d_margin=dl - dn)


def chroma(y):
    """numpy 크로마: 4096 FFT, 0.5초 간격, 12 음계. (프레임, 12)"""
    hop, n = 8000, 4096
    w = np.hanning(n)
    fr = np.stack([y[i:i + n] * w for i in range(0, len(y) - n, hop)])
    S = np.abs(np.fft.rfft(fr, axis=1))
    fq = np.fft.rfftfreq(n, 1 / SR)
    ok = (fq > 60) & (fq < 2000)
    pc = np.round(12 * np.log2(fq[ok] / 440) + 69).astype(int) % 12
    C = np.zeros((len(fr), 12))
    for k in range(12):
        C[:, k] = S[:, ok][:, pc == k].sum(1)
    return C


def rep_feats(pcm, s, e):
    """구간 첫 12초 크로마가 구간 밖 +-150초(practice.rep_near)와, 구간 안 뒤쪽에서(반복재생) 얼마나 닮았나."""
    t0 = max(0.0, s - 150)
    y = pcm[int(t0 * SR):int((e + 150) * SR)].astype(np.float32) / 32768
    C = chroma(y)
    C = C - C.mean(0)
    C /= np.linalg.norm(C, axis=1, keepdims=True) + 1e-6
    W = 24
    X = np.stack([C[i:i + W].ravel() for i in range(len(C) - W + 1)])
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-6
    i0, i1 = int(round((s - t0) / 0.5)), int(round((e - t0) / 0.5))
    sim = X @ X[i0]
    out = float(max((sim[j] for j in range(len(X)) if j < i0 - W or j > i1), default=0))
    inside = [sim[j] for j in range(i0 + 2 * W, min(i1 - W, len(X)))]          # 구간 안에서 시작 12초 패턴이 다시 나옴(후렴 반복도 포함)
    return dict(rep_near=out, rep_inside=float(max(inside, default=0)))


def dual_pitch(pcm, a, s, e):
    """원곡 보컬 + 따라 부르는 목소리의 이중 음정 단서: 말 없이 음악이 있는 프레임에서 f0 후보 상위 두 개(옥타브/배음 관계 제외)의 살리언스 비율.
    shortcut: 반주 악기와 섞인 혼합음에서 보컬 둘만 분리하지 못한다. 근사 단서일 뿐, 표본이 작아 판별력 주장 금지."""
    y = pcm[int(s * SR):int(min(e, s + 240) * SR)].astype(np.float32) / 32768
    n, hop = 2048, 1024
    w = np.hanning(n)
    nf = (len(y) - n) // hop
    if nf < 10:
        return {}
    fq = np.fft.rfftfreq(n, 1 / SR)
    f0 = 90 * 2 ** (np.arange(0, 3 * 24) / 24)             # 90Hz~720Hz, 1/24 옥타브
    H = np.zeros((len(f0), len(fq)), np.float32)
    for k, f in enumerate(f0):
        for h in range(1, 7):
            j = np.argmin(abs(fq - f * h))
            H[k, j] += 0.84 ** (h - 1)
    r2, ok = [], 0
    for i in range(nf):
        t = s + i * hop / SR
        ai = min(int(t * 2), len(a) - 1)
        if a[ai, 1] > 0.3 or a[ai, 2] < 0.5:                    # 말 없이 음악이 있는 프레임(YAMNet Singing 열은 값이 0.0x 로 작아 문턱으로 못 씀)
            continue
        sp = np.log1p(30 * np.abs(np.fft.rfft(y[i * hop:i * hop + n] * w)))
        sal = H @ sp
        k1 = int(np.argmax(sal))
        mask = np.ones(len(f0), bool)
        for rat in (1, 2, 0.5, 3, 1 / 3, 1.5, 2 / 3):          # 같은 음, 옥타브, 5도 배음 근처 제외
            c = int(round(24 * np.log2(rat))) + k1
            mask[max(0, c - 3):c + 4] = False
        if not mask.any():
            continue
        k2 = int(np.argmax(np.where(mask, sal, -1)))
        r2.append(sal[k2] / (sal[k1] + 1e-9))
        ok += 1
    if ok < 10:
        return {}
    r2 = np.array(r2)
    return dict(dual_med=float(np.median(r2)), dual_p80=float(np.percentile(r2, 80)), dual_frac=float((r2 > 0.9).mean()))


def meta_feats(r, nas, vmeta):
    """제목 키워드/카테고리 (NAS 슬러그는 제목만, 영상번호는 vod_meta 의 카테고리+제목)."""
    t, c = "", ""
    if str(r["vno"]).startswith("20"):
        t = (nas.get(r["vno"]) or {}).get("title", "")
    else:
        v = vmeta.get(str(r["vno"]))
        if v:
            t, c = v.get("title", ""), v.get("category", "")
    return dict(title=t, category=c)


def auc(pos, neg):
    """P(pos > neg) + 0.5 P(=): 순위합"""
    x = np.concatenate([pos, neg])
    rk = x.argsort().argsort() + 1.0
    for v in np.unique(x):          # 동순위 평균
        m = x == v
        rk[m] = rk[m].mean()
    return (rk[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def evaluate(R, feats_list, types):
    """유형 x 특징 -> auc(해당 유형 N 이 라이브보다 큰 쪽 확률), 방향, recall0, loso_rec, loso_lost, n"""
    res = {}
    live = [r for r in R if r["live"]]
    for t in types:
        neg = [r for r in R if r["live"] is False and r["tag"] == t]
        res[t] = {}
        for ft in feats_list:
            lv = np.array([r["f"].get(ft, np.nan) for r in live], float)
            nv = np.array([r["f"].get(ft, np.nan) for r in neg], float)
            lm, nm = ~np.isnan(lv), ~np.isnan(nv)
            if nm.sum() < 2 or lm.sum() < 10:
                continue
            a = auc(nv[nm], lv[lm])
            sgn = 1 if a >= 0.5 else -1                        # N 이 큰 쪽(+1)/작은 쪽(-1)
            lo, hi = lv[lm].min(), lv[lm].max()
            rej = (nv[nm] > hi) if sgn > 0 else (nv[nm] < lo)   # 라이브 범위 밖(= 라이브 손실 0)인 N
            # LOSO: 스트리머 s 를 뺀 라이브 범위로만 임계 -> s 의 N 거름 수, s 의 라이브 손실 수
            lr = ll = 0
            for s in {r["name"] for r in R}:
                tr = np.array([r["f"].get(ft, np.nan) for r in live if r["name"] != s], float)
                tr = tr[~np.isnan(tr)]
                if len(tr) < 10:
                    continue
                thr = tr.max() if sgn > 0 else tr.min()
                tn = np.array([r["f"].get(ft, np.nan) for r in neg if r["name"] == s], float)
                tl = np.array([r["f"].get(ft, np.nan) for r in live if r["name"] == s], float)
                tn, tl = tn[~np.isnan(tn)], tl[~np.isnan(tl)]
                lr += int(((tn > thr) if sgn > 0 else (tn < thr)).sum())
                ll += int(((tl > thr) if sgn > 0 else (tl < thr)).sum())
            res[t][ft] = dict(auc=round(float(max(a, 1 - a)), 3), dir=">" if sgn > 0 else "<", recall0=round(float(rej.mean()), 3), n=int(nm.sum()), loso_rej=lr, loso_live_lost=ll,
                              live_range=[round(float(lo), 3), round(float(hi), 3)], n_med=round(float(np.median(nv[nm])), 3), live_med=round(float(np.median(lv[lm])), 3))
    return res


def main():
    meta, F = scene_pool.pool()
    R = loso_n.records(meta, F)
    D = loso_n.dist_matrices(R, meta, F)
    nas = {x["slug"]: x for x in json.load(open("data/nas_index.json", encoding="utf8"))}
    vmeta = {str(v["videoNo"]): v for v in json.load(open("data/vod_meta.json", encoding="utf8"))}
    cache_a, cache_p = {}, {}
    for r in R:
        v = str(r["vno"])
        wav = Path(f"data/vod/nas/{v}.wav") if v.startswith("20") else Path(f"data/vod/{v}.wav")
        sc = Path(f"cache/detect/{wav.stem}.scores.npy")
        g = r["g"]
        s, e = g["start"], g["end"]
        f = {"len": e - s, "start_h": s / 3600, "has_speech_sig": g.get("speech")}
        if sc.exists():
            a = cache_a.setdefault(v, np.load(sc))
            f.update(audio_feats(a, s, e))
        fr = F.get(r["key"])
        if fr is not None and len(fr) >= 3:
            f.update(screen_feats(fr, D.get(r["key"].replace("/", "|"))))
            f.update(pool_dist(r, meta, D.get(r["key"].replace("/", "|"))))
            f["kf_per_min"] = len(fr) / ((e - s) / 60)
        elif g.get("tstd") is not None:
            f["tstd"], f["blk"] = g["tstd"], g.get("blk")
        if wav.exists() and sc.exists():
            pcm = cache_p.setdefault(v, pcm_of(wav))
            f.update(rep_feats(pcm, s, e))
            f.update(dual_pitch(pcm, cache_a[v], s, e))
        m = meta_feats(r, nas, vmeta)
        r["meta"] = m
        t = m["title"]
        f["title_song"] = float(bool(re.search(r"노래|가창|노래방|커버|singing|song|라이브|콘서트|합창|음악", t, re.I)))
        f["title_game"] = float(bool(re.search(r"게임|GTA|마크|마인|서버|리듬|스타|롤|발로|오버워치|배그", t, re.I))) if t else np.nan
        f["cat_game"] = float(m["category"] == "game") if m["category"] else np.nan
        f["cat_song"] = float(m["category"] in ("song", "music")) if m["category"] else np.nan
        r["f"] = {k: (float(v) if isinstance(v, (int, float, np.floating, np.integer)) and v is not None else np.nan) for k, v in f.items()}
        print(r["key"], r["live"], r["tag"], f"len {f['len']:.0f}", flush=True) if False else None
    types = sorted({r["tag"] for r in R if r["live"] is False and r["tag"]})
    feats_list = sorted({k for r in R for k in r["f"]} - {"has_speech_sig"})
    ev = evaluate(R, feats_list, types)
    # 요약: 유형별 상위 특징 (AUC 순, recall0>0 이고 LOSO 라이브 손실 0 인 것 우선)
    summ = {}
    for t, d in ev.items():
        best = sorted(d.items(), key=lambda kv: (-kv[1]["auc"]))[:6]
        zero = sorted([(k, v) for k, v in d.items() if v["loso_live_lost"] == 0 and v["loso_rej"] > 0], key=lambda kv: -kv[1]["loso_rej"])[:4]
        summ[t] = dict(n=next(iter(d.values()))["n"] if d else 0, top_auc=best, loso_zero_loss=zero)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(dict(eval=ev, summary=summ, n_live=sum(r["live"] is True for r in R), n_neg=sum(r["live"] is False for r in R),
                   items=[dict(key=r["key"], set=r["set"], name=r["name"], live=r["live"], tag=r["tag"], title=r["meta"]["title"], f={k: (None if np.isnan(v) else round(v, 4)) for k, v in r["f"].items()}) for r in R]),
              open(OUT, "w", encoding="utf8"), ensure_ascii=False, indent=1, default=float)
    print(f"라이브 {sum(r['live'] is True for r in R)}  N {sum(r['live'] is False for r in R)}  유형 {types}")
    for t, v in summ.items():
        print(f"\n## {t} (n={v['n']})")
        for k, x in v["top_auc"]:
            print(f"  AUC {x['auc']:.2f} {k:18} N{x['dir']}  N중앙 {x['n_med']:.3f} 라이브중앙 {x['live_med']:.3f} 라이브범위 {x['live_range']}  recall0 {x['recall0']:.2f}  LOSO 거름 {x['loso_rej']}/{x['n']} 라이브손실 {x['loso_live_lost']}")
        for k, x in v["loso_zero_loss"]:
            print(f"  [LOSO 손실0] {k:18} AUC {x['auc']:.2f} 거름 {x['loso_rej']}/{x['n']}")


if __name__ == "__main__":
    main()
