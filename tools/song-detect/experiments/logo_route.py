"""LOGO(Leave-One-Group-Out) 평가 도구: 등록부(known_*) 없이 route 규칙+신호가 N 을 얼마나 거르고 라이브를 얼마나 잃는지.
그룹 = 스트리머 x 방송일(--by streamer 면 스트리머). hold-out 그룹마다 신호 선택과 임계를 그 그룹을 뺀 표본으로만 다시 정한다(누수 방지).
  1. build : 후보마다 신호를 한 번 계산해 cache/audit/signals.csv 로 저장(재사용). route 의 기존 신호 + PLAN_NEXT 1.5절 신호.
  2. eval  : 신호 표에서 규칙 변형별 hold-out 결과(N 노출/weak/drop, 라이브 손실)와 그룹 단위 부트스트랩 95% 구간.
행 설명(규칙 변형):
  A  현재 임계(표본 내 선택 = 과적합 참고값. 1.4절 수치 노출 23 / weak 22 / drop 10 of 55 를 재현해야 함)
  B  A + 신호 선택(그룹 제외 학습)            C  tstd 임계를 그룹 밖 라이브 최댓값으로 재추정(weak 대역 없음)
  D  C + 신호 선택(그룹 제외 학습)           (m=여유: 임계 = 학습 라이브 극값 + m x 학습 라이브 범위)
분류: drop = 거름(구조 규칙 / tstd / 선택된 신호), weak = 현재 weak 대역(25~34.5)에 있고 거르지 않은 것, 노출 = 나머지(review 로 완성본에 노출).
라이브 손실 = drop + weak (loso_n 과 같은 정의).
  배포 규칙(n_signals.P: 구조 규칙 + tstd>34.5 + 오디오 신호 2개, weak 대역 없음)은 표본 내 값이라 eval 끝에 따로 출력(deployed): 라이브 88 중 걸린 수 0 을 assert.
사용: python experiments/logo_route.py [build|eval] [--rebuild] [--by group|streamer|both] [--cands default|all|신호,신호] [--boot 2000] [--out data/review/blind9/audit/logo_route.json]"""
import argparse, json, os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "experiments"))
os.chdir(ROOT)
import tune  # SONG_TUNE 환경변수가 있으면 상수 오버라이드(tune.py 참고), 없으면 아무 일도 안 한다
import numpy as np
import pandas as pd

SIG = Path("cache/audit/signals.csv")
# 후보 신호(특징, 설명). route 의 기존 신호 + 1.5절. 방향은 학습 표본의 AUC 로 정한다.
CANDS = ["speech", "bursts_per_min", "sing_std", "moving_frac", "bright_px", "rel_db", "diff_med", "speech_frac"]
# shortcut: 풀 거리 계열(scene, d_live/d_neg)은 풀에 같은 스트리머 다른 방송 프레임이 들어 있어 hold-out 값 자체가 누수라 후보에서 뺐다(scene 은 실제로 토아 11곡을 라이브 손실로 만듦, 단독 라이브 손실 14). 새 스트리머는 풀 기준이 없으므로 쓸 수도 없다.


def build(path=SIG):
    import loso_n, scene_pool
    from loso_signals import audio_feats, screen_feats
    from snap import SR, HOP, pcm_of, rms_db
    from scene_multi import P as MP
    meta, F = scene_pool.pool()
    R = loso_n.records(meta, F)
    nas = None
    rows, cache_a, cache_p, cache_lv = [], {}, {}, {}
    for r in R:
        g, v = r["g"], str(r["vno"])
        s, e = g["start"], g["end"]
        date = (r["pm"] or {}).get("date") or f"v{v}"            # shortcut: blind78 은 풀 메타가 없어 영상번호로 방송을 구분
        row = dict(key=r["key"], set=r["set"], name=r["name"], vno=v, group=f"{r['name']}|{date}", live=int(bool(r["live"])), tag=r["tag"] or "", bok=r["bok"],
                   len=e - s, start=s, tstd=g.get("tstd"), blk=g.get("blk"), speech=g.get("speech"), scene=g.get("scene"), multi=g.get("multi") or "", has_refs=int(bool(r["has_refs"])))
        t, why, weak, _ = loso_n.grade(r, g.get("multi"), g.get("scene"), r["has_refs"])
        row.update(base_tier=t, base_why=why, base_weak=int(weak), base_cls=loso_n.cls(t, weak))
        # 구조 규칙만(움직임 임계를 무한대로): route.tier 는 MP['motion'] 도 보므로 임계를 풀어 다시 등급
        mu = "unknown" if g.get("multi") == "watch" and (g.get("tstd") or 0) > MP["motion"] else g.get("multi")      # 저장된 watch 가 움직임 때문이면 구조 규칙 판정에서 뺀다(검은 띠 watch 는 유지)
        with loso_n.thr(motion=1e9, weak=1e9):
            t2, why2, _, _ = loso_n.grade(r, mu, g.get("scene"), r["has_refs"])
        row.update(struct_cls=loso_n.cls(t2, False), struct_why=why2)
        wav = Path(f"data/vod/nas/{v}.wav") if v.startswith("20") else Path(f"data/vod/{v}.wav")
        sc = Path(f"cache/detect/{wav.stem}.scores.npy")
        if sc.exists():
            a = cache_a.setdefault(v, np.load(sc))
            f = audio_feats(a, s, e)
            row.update({k: f[k] for k in ("sing", "speech_frac", "music", "bursts_per_min", "sing_std", "sp_mid_frac", "nospeech_max_frac", "ctx_speech")})
            if wav.exists():
                pcm = cache_p.setdefault(v, pcm_of(wav))
                if v not in cache_lv:        # 방송의 말소리 음량 = Speech>=0.7 프레임(최대 1500개 표본) 0.5초 rms dBFS 중앙값
                    idx = np.flatnonzero(a[:, 1] >= 0.7)
                    idx = idx[::max(1, len(idx) // 1500)]
                    lv = lambda i: 20 * np.log10(np.sqrt(((pcm[int(i * HOP * SR):int(i * HOP * SR) + 8000].astype(np.float32) / 32768) ** 2).mean()) + 1e-9)
                    cache_lv[v] = float(np.median([lv(i) for i in idx])) if len(idx) else np.nan
                row["song_db"] = float(np.median(rms_db(pcm, s, e)[1]))
                row["rel_db"] = row["song_db"] - cache_lv[v]
        fr = F.get(r["key"])
        if fr is not None and len(fr) >= 3:
            sf = screen_feats(fr, None)
            row.update({"tstd_kf": sf["tstd"], "moving_frac": sf["moving_frac"], "static_frac": sf["static_frac"], "diff_med": sf["diff_med"], "cut_frac": sf["cut_frac"]})
            row["bright_px"] = float((fr > 215 / 255).mean())          # 밝은 픽셀(lum>215) 비율: 웹/흰 배경 레이아웃. shortcut: 48x27 평균 축소 키프레임 기준이라 audit(320x180 프레임) 값보다 낮게 나온다
            row["n_kf"] = len(fr)
        rows.append(row)
    df = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")
    return df


def load(rebuild=False):
    if rebuild or not SIG.exists():
        return build()
    return pd.read_csv(SIG, keep_default_na=True, na_values=[""], dtype={"vno": str, "tag": str, "multi": str}).fillna({"tag": "", "multi": ""})


def golden_scene(s):
    """golden 곡의 저장된 4_scene.json 후보(refine 구간과 같은 keep 후보) -> (후보, has_refs). golden_gate.current 와 같은 매칭"""
    import audit_engine as E
    k = next(i for i, g in enumerate(E.kept(s["vid"])) if abs(g["start"] - s["refine"][0]) < 0.2 and abs(g["end"] - s["refine"][1]) < 0.2)
    sc = json.load(open(f"out/{s['vid']}/4_scene.json", encoding="utf8"))
    return sc["segs"][k], sc["has_refs"]


def with_golden(df):
    """승인 라이브(golden_v4.json)를 라이브 전용 행으로 덧붙인다(같은 방송 같은 구간이 이미 표에 있으면 건너뜀). 신호 임계가 표 밖 라이브에도 버티는지 보려는 것이라 N 행은 없다.
    채우는 열(리뷰 A2-3): 구조 규칙 입력(tstd, blk, speech, scene, multi, struct_cls: 저장된 4_scene.json, build() 와 같은 규칙), 점수 캐시 오디오 특징(audio_feats), rel_db, bursts_per_min. 비어 있는 열은 화면 키프레임 특징 3개(moving_frac, bright_px, diff_med)뿐이라
    그 신호가 선택돼도 golden 행에는 적용되지 않는다(손실 수는 하한).
    shortcut: 그룹 = 방송(영상번호)로 둬서 스트리머 단위 hold-out 은 방송 단위와 같아진다(스트리머 이름 매핑 생략)."""
    import n_signals, loso_n
    from loso_signals import audio_feats
    from scene_multi import P as MP
    rows, miss = [], []
    for s in json.load(open("experiments/golden_v4.json", encoding="utf8"))["songs"]:
        a, b = s["frozen"]["s"], s["frozen"]["e"]
        if ((df.vno == s["vid"]) & (np.minimum(df.start + df.len, b) - np.maximum(df.start, a) > 0.5 * (b - a))).any():
            continue
        seg = [dict(keep=True, start=a, end=b)]
        wav = Path(f"data/vod/nas/{s['vid']}.wav") if s["vid"].startswith("20") else Path(f"data/vod/{s['vid']}.wav")
        n_signals.fill(seg, wav)
        if seg[0].get("bursts") is None:
            miss.append(s["id"])
        else:
            g, has_refs = golden_scene(s)
            g = dict(g, weak=False, tier=None)
            mu = "unknown" if g.get("multi") == "watch" and (g.get("tstd") or 0) > MP["motion"] else g.get("multi")      # build() 와 같은 구조 규칙 판정(움직임 임계 해제)
            with loso_n.thr(motion=1e9, weak=1e9):
                t2, why2, _, _ = loso_n.grade(dict(g=g, vno=s["vid"]), mu, g.get("scene"), has_refs, use_likely=False)
            f = audio_feats(np.load(f"cache/detect/{wav.stem}.scores.npy"), a, b)
            rows.append(dict(key=f"golden/{s['id']}", set="golden", name=f"golden|{s['vid']}", vno=s["vid"], group=f"golden|{s['vid']}", live=1, tag="", len=b - a, start=a,
                             tstd=g.get("tstd"), blk=g.get("blk"), speech=g.get("speech"), scene=g.get("scene"), multi=g.get("multi") or "", has_refs=int(bool(has_refs)),
                             struct_cls=loso_n.cls(t2, False), struct_why=why2, base_cls="review",
                             **{k: f[k] for k in ("sing", "speech_frac", "music", "sing_std", "sp_mid_frac", "nospeech_max_frac", "ctx_speech")}, bursts_per_min=seg[0]["bursts"], rel_db=seg[0]["rel_db"]))
    assert not miss, f"golden 라이브 {len(miss)}행이 점수 캐시/wav 가 없어 빠진다(조용히 빠지면 라이브 풀 136 검사가 빈 집합으로 통과한다, 리뷰 B-2): {miss[:5]}"
    return pd.concat([df, pd.DataFrame(rows)], ignore_index=True)


def auc(pos, neg):
    """P(pos > neg) + 0.5 P(=)"""
    from loso_signals import auc as _a
    return _a(np.asarray(pos, float), np.asarray(neg, float))


def select(df, base_rej, cands, mult, k_max=3, min_gain=2):
    """학습 표본 df 에서 신호를 탐욕적으로 고른다: 임계 = 학습 라이브 극값 + mult x 범위(학습 라이브 손실 0), 이득 = 아직 안 걸린 학습 N 중 새로 걸리는 수.
    반환 [(특징, '>'|'<', 임계)]."""
    live = df[df.live == 1]
    left = (df.live == 0).to_numpy() & ~base_rej
    chosen = []
    for _ in range(k_max):
        best = None
        for c in cands:
            if c in [x[0] for x in chosen]:
                continue
            lv = live[c].dropna().to_numpy(float)
            if len(lv) < 10:
                continue
            nv = df.loc[left, c].dropna().to_numpy(float)
            if len(nv) < 2:
                continue
            up = auc(nv, lv) >= 0.5
            rng = lv.max() - lv.min()
            thr = lv.max() + mult * rng if up else lv.min() - mult * rng
            hit = (df[c] > thr).to_numpy() if up else (df[c] < thr).to_numpy()
            hit = hit & left & df[c].notna().to_numpy()
            gain = int(hit.sum())
            if gain >= min_gain and (best is None or gain > best[0]):
                best = (gain, c, ">" if up else "<", float(thr), hit)
        if best is None:
            break
        chosen.append(best[1:4])
        left &= ~best[4]
    return chosen


def fire(df, rules):
    """규칙 목록이 거르는 행(bool 배열). 값이 없는 행은 거르지 않는다."""
    m = np.zeros(len(df), bool)
    for c, d, t in rules:
        v = df[c].to_numpy(float)
        m |= np.where(np.isnan(v), False, (v > t) if d == ">" else (v < t))
    return m


def holdout(df, by, variant, mult=0.0, cands=CANDS):
    """variant: 'A' 현재 임계, 'B' A+신호, 'C' tstd 재추정, 'D' C+신호. 각 행의 hold-out 결과(drop/weak/ok)와 폴드별 선택 신호."""
    out = np.array(["ok"] * len(df), dtype=object)
    folds = {}
    for grp in df[by].unique():
        te = (df[by] == grp).to_numpy()
        tr = df[~te]
        if variant in ("A", "B"):
            base_tr = (tr.base_cls == "drop").to_numpy()
            base_te = df.base_cls[te].to_numpy()
            weak_te = (df.base_cls[te] == "weak").to_numpy()
        else:                                                    # tstd 임계 = 학습 라이브 최댓값(+0.01), weak 대역 없음
            T = tr[tr.live == 1].tstd.max() + 0.01
            base_tr = ((tr.struct_cls == "drop") | (tr.tstd > T)).to_numpy()
            base_te = np.where((df.struct_cls[te] == "drop") | (df.tstd[te] > T), "drop", "ok")
            weak_te = np.zeros(te.sum(), bool)
        rules = select(tr, base_tr, cands, mult) if variant in ("B", "D") else []
        hit = fire(df[te], rules)
        res = np.where((base_te == "drop") | hit, "drop", np.where(weak_te, "weak", "ok"))
        out[te] = res
        folds[grp] = [(c, d, round(t, 4)) for c, d, t in rules]
    return out, folds


def tally(df, res, mask=None):
    """분류 집계: N 노출/weak/drop, 라이브 손실(drop+weak)."""
    m = np.ones(len(df), bool) if mask is None else mask
    N, L = m & (df.live == 0).to_numpy(), m & (df.live == 1).to_numpy()
    c = lambda sel, k: int((sel & (res == k)).sum())
    return dict(n_N=int(N.sum()), N_ok=c(N, "ok"), N_weak=c(N, "weak"), N_drop=c(N, "drop"), n_L=int(L.sum()), L_ok=c(L, "ok"), L_weak=c(L, "weak"), L_drop=c(L, "drop"))


def boot(df, res, by, mask, B, seed=0):
    """그룹 단위 부트스트랩(그룹을 복원추출) 95% 구간: N 노출률(ok/N), N 노출+weak 률, 라이브 손실률."""
    rng = np.random.default_rng(seed)
    g = df[by].to_numpy()
    ug = np.unique(g)
    rows = np.array([[((g == u) & mask & (df.live == 0).to_numpy()).sum(), ((g == u) & mask & (df.live == 0).to_numpy() & (res == "ok")).sum(),
                      ((g == u) & mask & (df.live == 0).to_numpy() & (res == "weak")).sum(), ((g == u) & mask & (df.live == 1).to_numpy()).sum(),
                      ((g == u) & mask & (df.live == 1).to_numpy() & (res != "ok")).sum()] for u in ug])
    est = []
    for _ in range(B):
        s = rows[rng.integers(0, len(ug), len(ug))].sum(0)
        est.append([s[1] / s[0] if s[0] else np.nan, (s[1] + s[2]) / s[0] if s[0] else np.nan, s[4] / s[3] if s[3] else np.nan])
    q = np.nanpercentile(np.array(est), [2.5, 97.5], axis=0)
    return dict(N_ok=q[:, 0].round(3).tolist(), N_ok_weak=q[:, 1].round(3).tolist(), L_lost=q[:, 2].round(3).tolist(), n_groups=int(len(ug)))


def rows_of(margins):
    return [("A", 0.0, "현재 임계(표본 내, 과적합 참고)")] + [("B", m, f"A + 신호 선택(m={m})") for m in margins] +            [("C", 0.0, "tstd 임계 재추정(weak 대역 없음)")] + [("D", m, f"C + 신호 선택(m={m})") for m in margins]


def single_signals(df, by, cands):
    """신호 하나씩, C 규칙 위에서: 전체 AUC, hold-out 에서 추가로 거른 N 수와 라이브 손실(임계 = 학습 라이브 극값, m=0)."""
    base, _ = holdout(df, by, "C")
    out = {}
    for c in cands:
        a = auc(df.loc[df.live == 0, c].dropna(), df.loc[df.live == 1, c].dropna()) if df[c].notna().sum() > 20 else np.nan
        rej_N = lost_L = 0
        for grp in df[by].unique():
            te = (df[by] == grp).to_numpy()
            tr = df[~te]
            T = tr[tr.live == 1].tstd.max() + 0.01
            btr = ((tr.struct_cls == "drop") | (tr.tstd > T)).to_numpy()
            r = select(tr, btr, [c], 0.0, 1, 1)
            h = fire(df[te], r) & (base[te] == "ok")
            rej_N += int((h & (df.live[te] == 0).to_numpy()).sum())
            lost_L += int((h & (df.live[te] == 1).to_numpy()).sum())
        out[c] = dict(auc=None if np.isnan(a) else round(float(max(a, 1 - a)), 3), N_rej=rej_N, L_lost=lost_L)
    return out


def fmt(t, ci, key_ok="N_ok"):
    return (f"N {t['n_N']}: 노출 {t['N_ok']:2} ({t['N_ok'] / t['n_N']:.0%} [{ci['N_ok'][0]:.0%}-{ci['N_ok'][1]:.0%}]) weak {t['N_weak']:2} drop {t['N_drop']:2} | "
            f"라이브 {t['n_L']}: 손실 {t['L_weak'] + t['L_drop']} (weak {t['L_weak']} drop {t['L_drop']}; {(t['L_weak'] + t['L_drop']) / t['n_L']:.1%} [{ci['L_lost'][0]:.1%}-{ci['L_lost'][1]:.1%}])")


def evaluate(df, by, cands, B, margins):
    res = {}
    subsets = {"blind9": (df.set == "blind9").to_numpy(), "전체": np.ones(len(df), bool)}
    for v, m, name in rows_of(margins):
        out, folds = holdout(df, by, v, m, cands)
        live, tag = df.live.to_numpy(), df.tag.to_numpy()
        res[f"{v}{'' if v in 'AC' else f' m={m}'}"] = dict(name=name, out=out, folds=folds, exposed_N=[f"{k}:{t}" for k, t, o, l in zip(df.key, tag, out, live) if l == 0 and o == "ok"],
                                                          lost_live=[k for k, o, l in zip(df.key, out, live) if l == 1 and o != "ok"],
                                                          **{s: dict(tally(df, out, mk), ci=boot(df, out, by, mk, B)) for s, mk in subsets.items()})
    return res


def selftest():
    """합성 표: 신호 f 는 라이브 0~1, N 은 2~3(분리됨), 그룹 g0 의 라이브만 1.5 로 튀어 hold-out 에서 손실이 나와야 한다."""
    n = 40
    rng = np.random.default_rng(1)
    d = pd.DataFrame(dict(live=[1] * n + [0] * n, f=np.r_[rng.uniform(0, 1, n), rng.uniform(2, 3, n)], tstd=5.0, struct_cls="review", base_cls="review", group=[f"g{i % 4}" for i in range(2 * n)]))
    d.loc[0, "f"] = 1.5                                                    # g0 의 라이브 1개가 N 쪽으로 넘어감
    r = select(d, np.zeros(len(d), bool), ["f"], 0.0)
    assert r and r[0][:2] == ("f", ">") and 0.9 < r[0][2] < 1.6, r
    out, folds = holdout(d, "group", "D", 0.0, ["f"])
    t = tally(d, out)
    assert t["n_N"] == n and t["L_drop"] == 1 and t["N_ok"] <= 5, t           # g0 hold-out 에서만 라이브 1개 손실, N 은 거의 다 걸림
    out, _ = holdout(d, "group", "D", 1.0, ["f"])
    assert tally(d, out)["L_drop"] == 0                                    # 여유 m 이 임계를 넘겨 손실 제거
    ci = boot(d, out, "group", np.ones(len(d), bool), 200)
    assert ci["L_lost"][0] == 0 and ci["n_groups"] == 4


def deployed(df):
    """배포 규칙(route.mark_likely 가 쓰는 n_signals.fire + 구조 규칙 + tstd>motion)을 신호 표에 그대로 적용한 표본 내 결과. 라이브가 하나라도 걸리면 실패."""
    import n_signals
    from scene_multi import P as MP
    fl = np.array([bool(n_signals.fire(dict(rel_db=r, bursts=b))) for r, b in zip(df.rel_db.fillna(0), df.bursts_per_min.fillna(0))])     # 신호 없는 행(NaN)은 걸지 않음
    base = ((df.struct_cls == "drop") | (df.tstd > MP["motion"])).to_numpy()
    res = np.where(base | fl, "drop", "ok")
    out = {s: tally(df, res, mk) for s, mk in {"blind9": (df.set == "blind9").to_numpy(), "전체": np.ones(len(df), bool)}.items()}
    assert out["전체"]["L_drop"] == 0, [k for k, r, l in zip(df.key, res, df.live) if l == 1 and r != "ok"]
    return out, [f"{k}:{t}" for k, t, r, l in zip(df.key, df.tag, res, df.live) if l == 0 and r == "ok"]


def main():
    selftest()
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", nargs="?", default="eval", choices=["build", "eval"])
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--by", default="both", choices=["group", "streamer", "both"])
    ap.add_argument("--cands", default="default", help="default | all | 쉼표로 나열한 신호 열 이름")
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--golden", action="store_true", help="승인 라이브(golden_v4)를 라이브 전용 행으로 추가해 임계가 표 밖 라이브에도 버티는지 본다")
    ap.add_argument("--margins", default="0,0.1,0.2", help="임계 여유 m 목록(학습 라이브 범위의 비율)")
    ap.add_argument("--out", default="data/review/blind9/audit/logo_route.json")
    a = ap.parse_args()
    df = load(a.rebuild or a.cmd == "build")
    if a.cmd == "build":
        print(f"신호 표 {len(df)}행 x {df.shape[1]}열 -> {SIG}")
        return
    cands = CANDS if a.cands == "default" else a.cands.split(",") if a.cands != "all" else [c for c in df.columns if df[c].dtype.kind == "f" and c not in ("tstd", "blk", "start", "len", "live", "bok", "tstd_kf", "song_db", "n_kf", "scene", "has_refs", "base_weak")]
    if a.golden:
        df = with_golden(df)
        print(f"golden 라이브 {int((df.set == 'golden').sum())}행 추가(표와 같은 방송 같은 구간은 제외)")
    df["streamer"] = df.name
    report = {}
    for by in (("group", "streamer") if a.by == "both" else (a.by,)):
        col = "group" if by == "group" else "streamer"
        R = evaluate(df, col, cands, a.boot, [float(x) for x in a.margins.split(',')])
        report[by] = {k: {s: v[s] for s in ("blind9", "전체")} | {x: v[x] for x in ("name", "folds", "exposed_N", "lost_live")} for k, v in R.items()}
        report[by]["single"] = single_signals(df, col, cands)
        print(f"\n===== hold-out 단위: {'스트리머 x 방송일' if by == 'group' else '스트리머'} ({df[col].nunique()}개 그룹), 부트스트랩 {a.boot}회 =====")
        for k, v in R.items():
            for s in ("blind9", "전체"):
                print(f"  {k:8} {v['name'][:22]:22} [{s:6}] {fmt(v[s], v[s]['ci'])}")
            if k.startswith(("B", "D")):
                from collections import Counter
                cnt = Counter(c for f in v["folds"].values() for c, _, _ in f)
                print(f"           선택된 신호(폴드 {len(v['folds'])}개 중 횟수): {dict(cnt)}")
                print(f"           노출 N 유형: {dict(Counter(x.split(':')[-1] for x in v['exposed_N']))} | 손실 라이브: {[x[-22:] for x in v['lost_live']]}")
        print("  [신호 하나씩, C 규칙 위에 추가, m=0] 신호: AUC / 추가로 거른 N / 라이브 손실")
        for c, x in sorted(report[by]["single"].items(), key=lambda kv: -kv[1]["N_rej"]):
            print(f"     {c:16} AUC {x['auc']}  N 거름 {x['N_rej']:2}  라이브 손실 {x['L_lost']}")
    dep, exp = deployed(df)
    report["deployed"] = dict(in_sample=dep, exposed_N=exp)
    print("\n[배포 규칙 표본 내(과적합 참고)] " +" | ".join(f"{s}: N 노출 {t['N_ok']}/{t['n_N']} 라이브 걸림 {t['L_drop']}/{t['n_L']}" for s, t in dep.items()))
    best = (report.get("group") or report["streamer"])["A"]["blind9"]
    assert (best["N_ok"], best["N_weak"], best["N_drop"], best["n_N"]) == (23, 22, 10, 55), f"1.4절 수치 재현 실패: {best}"
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    json.dump(report, open(a.out, "w", encoding="utf8"), ensure_ascii=False, indent=1, default=lambda o: o.tolist() if hasattr(o, "tolist") else str(o))
    print(f"\n[점검] 행 A blind9 = 노출 23 / weak 22 / drop 10 of 55 재현 확인. 저장: {a.out}")


if __name__ == "__main__":
    main()
