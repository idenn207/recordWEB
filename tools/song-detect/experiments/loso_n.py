"""일반화(LOSO) 측정: 등록부(known_negatives/approved)를 끄고, 풀에서 같은 방송/같은 스트리머를 빼고, 규칙만으로 N 을 얼마나 거르는지.
입력은 GPU 재탐지 없이 out/<슬러그|영상번호>/4_scene.json(후보 신호)과 cache/scene_pool.npz(키프레임)뿐. 읽기 전용.
조건(열):
  prod        출하 상태: 4_scene 의 multi + route.tier + known_pos + known_neg (등록부 켬)
  noreg       등록부 끔(known_*), 4_scene 에 저장된 multi/scene 그대로 (풀에서 같은 날짜 방송은 이미 뺀 상태, 영상번호 방송은 자기 프레임이 풀에 남아 낙관적)
  bcast       등록부 끔 + 풀에서 같은 방송(같은 스트리머+날짜, 영상번호 같음)을 빼고 multi/scene 재계산 = leave-one-broadcast-out
  streamer    등록부 끔 + 풀에서 같은 스트리머를 모두 뺌 = leave-one-streamer-out (같은 채널 기준이 없어 has_refs=False, auto 없음)
  nopool      풀 비교도 끔: 신호 규칙(대기 5분, 길이, idle/검은 띠/움직임 tstd, weak 대역, 피아노)만
  refit       streamer 와 같되 움직임 임계값을 뺀 스트리머 이외의 모든 세트 라이브 tstd 최댓값으로 다시 정함(임계값의 일반화)
  refit9      같되 blind9(NAS 1080p 파이프라인) 라이브만으로 정함(blind5/6/7/8 은 144p 영상이라 tstd 분포가 다름)
등급 -> 걸러짐 = drop/optional, 또는 review 인데 weak(움직임 25~34.5, 완성본 제외).
세트: blind9(104 중복 제거), blind5, blind6, blind78(scene_pool.EXTRA 개별 후보; 키프레임이 풀에 없어 풀 재계산 조건은 건너뜀).
사용: python experiments/loso_n.py [출력=data/review/blind9/audit/loso.json]"""
import contextlib, json, os, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
import numpy as np
import route, scene_multi, scene_pool
from labels import BLIND9, load as load_labels
from scene_multi import classify, feats
from scene_pool import EXTRA

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "data/review/blind9/audit/loso.json")
EXTRA_TAG = {"7A": "incidental", "7D1": "idle_screen", "7D2": "cover_watch", "8Q1": "sing_along"}
CONDS = ("prod", "noreg", "bcast", "streamer", "nopool", "refit", "refit9")
NOFR = np.zeros((0, 1296), np.float32)


def near(sc, start, end=None):
    """4_scene 의 keep 후보 중 [start,end] 와 가장 많이 겹치는 것(없으면 시작이 8초 이내인 가장 가까운 것)."""
    best, bo = None, 0
    for g in sc["segs"]:
        ov = min(g["end"], end if end else g["start"] + 1) - max(g["start"], start)
        if ov > bo:
            best, bo = g, ov
    if best is None:
        c = min(sc["segs"], key=lambda g: abs(g["start"] - start), default=None)
        best = c if c and abs(c["start"] - start) < 8 else None
    return best


def records(meta, F):
    R = []
    pm = {(m["set"], m["id"]): m for m in meta}
    K9 = json.load(open("data/review/blind9/key.json", encoding="utf8"))
    for k, l in BLIND9.items():
        kk = K9[k]
        sf = Path(f"out/{kk['videoNo']}/4_scene.json")
        sc = json.load(open(sf, encoding="utf8"))
        g = near(sc, kk["start"], kk["end"])
        if g is None:
            continue
        R.append(dict(set="blind9", id=k, key=f"blind9/{k}", name=kk["name"], vno=kk["videoNo"], live=l["live"], tag=l["tag"], bok=l["boundary_ok"], g=g, has_refs=sc["has_refs"], pm=pm.get(("blind9", k))))
    lab = load_labels()
    for s in ("blind5", "blind6"):
        K = json.load(open(f"data/review/{s}/key.json", encoding="utf8"))
        for v, l in lab[s].items():
            kk = K[v]
            sf = Path(f"out/{kk['videoNo']}/4_scene.json")
            sc = json.load(open(sf, encoding="utf8")) if sf.exists() else None
            g = near(sc, kk["start"], kk["end"]) if sc else None
            m = pm.get((s, v))
            g = dict(g) if g else dict(start=kk["start"], end=kk["end"], len=kk["len"], keep=True, multi=None, speech=None)
            fr = F.get(f"{s}/{v}", NOFR)
            if len(fr) >= 3:
                g["tstd"], g["blk"] = feats(fr)
            R.append(dict(set=s, id=v, key=f"{s}/{v}", name=kk["name"], vno=kk["videoNo"], live=l["live"], tag=l["tag"], bok=l.get("boundary_ok"), g=g, has_refs=bool(sc and sc["has_refs"]), pm=m))
    for vno, st, live, tag in EXTRA:
        sf = Path(f"out/{vno}/4_scene.json")
        if not sf.exists():
            continue
        sc = json.load(open(sf, encoding="utf8"))
        g = near(sc, st)
        if g is None or abs(g["start"] - st) >= 8:
            continue
        nm = next((v["name"] for p in Path("data").glob("vods*.json") for v in json.load(open(p, encoding="utf8")) if str(v["videoNo"]) == str(vno)), "?")
        R.append(dict(set="blind78", id=tag, key=f"blind78/{tag}", name=nm, vno=vno, live=live, tag=None if live else EXTRA_TAG.get(tag, "?"), bok=None, g=g, has_refs=sc["has_refs"], pm=None))
    return R


@contextlib.contextmanager
def thr(**kw):
    old = dict(scene_multi.P)
    scene_multi.P.update(kw)
    try:
        yield
    finally:
        scene_multi.P.clear()
        scene_multi.P.update(old)


def grade(r, multi, scene, has_refs, registry=False, use_likely=True):
    """한 후보의 등급 -> (tier, why, weak, likely). registry=True 면 known_pos/known_neg 까지 적용."""
    g = dict(r["g"], multi=multi, scene=scene, tier=None)
    g["tier"], g["tier_why"] = route.tier(g, has_refs)
    if registry:
        route.known_pos(r["vno"], g)
        route.known_neg(r["vno"], g)
    lk = scene_pool.likely_flag(g, r["vno"]) if use_likely else False
    return g["tier"], g["tier_why"], bool(g["weak"]), bool(lk)


DM = Path("cache/audit/loso_dm.npz")


def _init(P, off):
    global _P, _OFF
    _P, _OFF = P, off


def _dm_one(fr):
    """후보 키프레임 fr 와 풀 항목 j 마다 '프레임별 최근접 거리(항목 안 최소)' 행렬 (프레임 x 풀항목)."""
    P, off = _P, _OFF
    out = np.empty((len(fr), len(off) - 1), np.float32)
    for i, f in enumerate(fr):
        d = np.abs(P - f).mean(1)
        out[i] = np.minimum.reduceat(d, off[:-1])
    return out


def dist_matrices(R, meta, F, workers=4):
    """모든 후보 x 풀 항목의 최근접 거리 행렬(캐시). 제외 집합이 달라도 열을 골라 min 만 하면 연결 풀과 같은 값이라 한 번만 계산한다."""
    keys = [f"{m['set']}/{m['id']}" for m in meta]
    sig = np.array([len(F[k]) for k in keys] + [len(r_f) for r_f in (F.get(r["key"], NOFR) for r in R)])
    if DM.exists():
        z = np.load(DM, allow_pickle=True)
        if np.array_equal(z["sig"], sig):
            return {k: z[k] for k in z.files if k != "sig"}
    P = np.concatenate([F[k] for k in keys]).astype(np.float32)
    off = np.cumsum([0] + [len(F[k]) for k in keys])
    todo = [r for r in R if r["key"] in F and len(F[r["key"]]) >= 3]
    from multiprocessing import Pool
    with Pool(workers, initializer=_init, initargs=(P, off)) as pool:
        mats = pool.map(_dm_one, [F[r["key"]] for r in todo], chunksize=1)
    D = {r["key"].replace("/", "|"): m for r, m in zip(todo, mats)}
    DM.parent.mkdir(parents=True, exist_ok=True)
    np.savez(DM, sig=sig, **D)
    return D


def classify_dm(fr, dl, dn, p, tb=None):
    """scene_multi.classify 와 같은 논리, 거리만 행렬에서(dl/dn = 프레임별 최근접 거리 배열 또는 None)."""
    if len(fr) < 3:
        return "unknown"
    tstd, blk = tb if tb and tb[0] is not None else feats(fr)         # 출하 파이프라인은 NAS 영상 키프레임에서 잰 4_scene 값을 쓴다(풀 프레임은 완성본 클립이라 경계값이 조금 다름)
    if tstd < p["idle"]:
        return "idle"
    if p["black"] < blk <= p["black_max"]:
        return "watch"
    if tstd > p["motion"]:
        return "watch"
    if dl is None:
        return "unknown"
    dl = float(np.median(dl))
    dn = float(np.median(dn)) if dn is not None else 9.0
    if dl < dn and tstd >= p["weak"]:
        return "unknown"
    return "live" if dl < dn else "unknown"


def recompute(r, meta, F, D, unit):
    """풀에서 unit(bcast/streamer)을 빼고 multi/scene 재계산. 키프레임이 풀에 없으면 None."""
    m, fr, d = r["pm"], F.get(r["key"]), D.get(r["key"].replace("/", "|"))
    if m is None or fr is None or d is None:
        return None
    if unit == "streamer":
        keep = lambda o: o["name"] != m["name"]
    else:
        keep = lambda o: not (o["videoNo"] == m["videoNo"] or (o["name"] == m["name"] and o.get("date") and o.get("date") == m.get("date")))
    col = lambda f: np.array([j for j, o in enumerate(meta) if f(o)], int)
    cl, cn, cs = col(lambda o: keep(o) and o["live"]), col(lambda o: keep(o) and not o["live"]), col(lambda o: keep(o) and o["live"] and o["name"] == m["name"])
    pick = lambda c: d[:, c].min(1) if len(c) else None
    if unit != "streamer" and len(cs) and scene_pool.eligible(meta, m["name"], keep):
        sc, has = float(np.median(pick(cs))), True
    else:
        sc, has = None, False
    return classify_dm(fr, pick(cl), pick(cn), scene_multi.P, (r["g"].get("tstd"), r["g"].get("blk"))), sc, has


def cls(tier, weak):
    return "drop" if tier in ("drop", "optional") else "weak" if (weak and tier == "review") else tier


def tally(rows, cond):
    """rows 의 cond 열 분포: N(오탐)과 라이브 각각 등급 분포, N 유형별 샘플 수/통과(auto,review) 수."""
    out = {}
    for lv in (False, True):
        S = [x for x in rows if x["live"] is lv and cond in x]
        c = Counter(x[cond]["cls"] for x in S)
        out["live" if lv else "N"] = dict(n=len(S), **{k: c.get(k, 0) for k in ("auto", "review", "weak", "drop")}, likely=sum(x[cond]["likely"] for x in S))
    bytag = defaultdict(Counter)
    for x in rows:
        if x["live"] is False and cond in x:
            bytag[x["tag"]][x[cond]["cls"]] += 1
    out["N_by_tag"] = {t: dict(n=sum(c.values()), leak=c["auto"] + c["review"], auto=c["auto"], review=c["review"], weak=c["weak"], drop=c["drop"]) for t, c in sorted(bytag.items(), key=lambda kv: str(kv[0]))}
    out["live_lost"] = [x["key"] for x in rows if x["live"] is True and cond in x and x[cond]["cls"] in ("drop", "weak")]
    return out


def main():
    meta, F = scene_pool.pool()
    R = records(meta, F)
    D = dist_matrices(R, meta, F)
    # 실제 등급 계산: 조건별
    for r in R:
        g = r["g"]
        r["prod"] = dict(zip(("tier", "why", "weak", "likely"), grade(r, g.get("multi"), g.get("scene"), r["has_refs"], True)))
        r["noreg"] = dict(zip(("tier", "why", "weak", "likely"), grade(r, g.get("multi"), g.get("scene"), r["has_refs"])))
        tb = (g.get("tstd"), g.get("blk"))      # 풀 없이 신호 규칙만: classify 안의 idle/검은 띠/움직임은 쓰고 live/neg 풀 거리만 끔
        mu0 = classify_dm(F.get(r["key"], np.zeros((3, 1296), np.float32)) if len(F.get(r["key"], NOFR)) >= 3 else np.zeros((3, 1296), np.float32), None, None, scene_multi.P, tb) if tb[0] is not None else "unknown"
        r["nopool"] = dict(zip(("tier", "why", "weak", "likely"), grade(r, mu0, None, False)))
        for unit in (("bcast", "streamer") if r["set"] != "blind78" else ()):      # blind78 은 키프레임이 풀에 없어 풀 재계산 조건 제외
            rc = recompute(r, meta, F, D, unit)
            r["noframes"] = rc is None
            rc = rc or ("unknown", None, False)             # 키프레임이 없는 후보(대기 화면 등)는 풀 비교 없이 신호 규칙만
            if rc:
                r[unit] = dict(zip(("tier", "why", "weak", "likely"), grade(r, rc[0], rc[1], rc[2])))
                r[unit]["multi"] = rc[0]
    # 임계값 재추정(refit): 뺀 스트리머 이외의 라이브 tstd 최댓값 -> 그 값을 motion/weak 로 쓰고(weak 대역 없음) streamer 조건 다시
    for r in R:
        if r["set"] == "blind78":
            continue
        T = max((x["g"].get("tstd") or 0) for x in R if x["live"] and x["name"] != r["name"] and x["g"].get("tstd") is not None) + 0.01
        r["refit_T"] = round(T, 2)
        with thr(motion=T, weak=T):
            rc = recompute(r, meta, F, D, "streamer") or ("unknown", None, False)
            r["refit"] = dict(zip(("tier", "why", "weak", "likely"), grade(r, rc[0], rc[1], rc[2])))
        T9 = max((x["g"].get("tstd") or 0) for x in R if x["live"] and x["set"] == "blind9" and x["name"] != r["name"]) + 0.01     # 같은 NAS 1080p 파이프라인(blind9) 라이브만으로
        r["refit9_T"] = round(T9, 2)
        with thr(motion=T9, weak=T9):
            rc = recompute(r, meta, F, D, "streamer") or ("unknown", None, False)
            r["refit9"] = dict(zip(("tier", "why", "weak", "likely"), grade(r, rc[0], rc[1], rc[2])))
    for r in R:
        for c in CONDS:
            if c in r:
                r[c]["cls"] = cls(r[c]["tier"], r[c]["weak"])
    res = {}
    for s in ("blind9", "blind5", "blind6", "blind78"):
        rows = [r for r in R if r["set"] == s]
        res[s] = {c: tally(rows, c) for c in CONDS}
        res[s]["n_records"] = len(rows)
    # 스트리머별 refit 라이브 손실 (뺀 스트리머 라이브 tstd 가 T 를 넘으면 손실)
    det = [dict(key=r["key"], set=r["set"], name=r["name"], live=r["live"], tag=r["tag"], bok=r["bok"], start=round(r["g"]["start"], 1), len=round(r["g"]["len"], 1), tstd=r["g"].get("tstd"), blk=r["g"].get("blk"),
                speech=r["g"].get("speech"), noframes=r.get("noframes"), refit_T=r.get("refit_T"), **{c: r[c]["cls"] + (":" + r[c]["tier"] if r[c]["cls"] != r[c]["tier"] else "") + ("*" if r[c]["likely"] else "") for c in CONDS if c in r}) for r in R]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(dict(summary=res, items=det, thresholds=dict(scene_multi.P)), open(OUT, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    mm = [(r["key"], r["g"].get("multi"), r["bcast"]["multi"]) for r in R if "bcast" in r and r["set"] == "blind9" and r["g"].get("multi") != r["bcast"]["multi"]]
    print(f"[점검] blind9 에서 풀 재계산(bcast) multi 가 저장값과 다른 후보 {len(mm)}/104: {mm[:6]}")
    print("[점검] 키프레임 없는 후보(풀 비교 생략):", [r["key"] for r in R if r.get("noframes")])
    show(res)


def show(res):
    for s, d in res.items():
        print(f"\n== {s} (후보 {d['n_records']})")
        for c in CONDS:
            t = d[c]
            N, L = t["N"], t["live"]
            if not N["n"] and not L["n"]:
                continue
            print(f"  {c:9} N {N['n']:3}: auto {N['auto']:2} review {N['review']:2} (likely {N['likely']}) weak {N['weak']:2} drop {N['drop']:2} | 걸러짐 {(N['weak'] + N['drop'])}/{N['n']}   라이브 {L['n']:3}: auto {L['auto']:2} review {L['review']:2} weak {L['weak']:2} drop {L['drop']:2} 손실 {L['weak'] + L['drop']}")
    print("\n[blind9 streamer 조건: N 유형별 (n / 새는 수)]")
    for t, v in res["blind9"]["streamer"]["N_by_tag"].items():
        print(f"  {t:17} {v['n']:2} / 새는 {v['leak']:2}  (review {v['review']} auto {v['auto']} weak {v['weak']} drop {v['drop']})")


if __name__ == "__main__":
    main()
