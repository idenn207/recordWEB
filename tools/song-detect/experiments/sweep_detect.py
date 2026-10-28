"""detect 단계 파라미터 재탐지(점수 캐시 재사용) 평가기. detect.detect 원본 코드를 그대로 돌리되 Demucs 보컬 비율만 캐시에서 채운다.
- 보컬 캐시(cache/detect/<이름>.vocal.json)는 후보 구간 [cs-pad, ce+pad] 의 5초 창별 비율이다. 후보가 바뀌면(gap_s, music_min 등) 키가 달라지므로, 캐시된 모든 구간을
  방송 시간축 0.5초 격자(보컬 타임라인)에 깔고 새 구간의 창 평균을 거기서 구한다(구간 격자가 5초 배수로 맞으면 정확, 아니면 근사). 타임라인이 덮지 못한 창이 있으면 그 후보는 평가에서 제외(unevaluated 로 센다).
- 기본 설정(vocal_thr=0.2: pipeline.analyze 가 쓰는 값) 재생이 out/<id>/1_detect.json 과 같은지 selftest 로 확인한다.
지표(dict): keep_n(전 방송 KEEP 수), gold(golden 113곡 중 같은 곡으로 매칭), memoL(메모 라이브 그룹 매칭), memoN(메모 N 그룹이 여전히 KEEP = 상류 노출), new(기준에 없던 KEEP), lost(기준에 있던 KEEP 소실), drift8(매칭된 golden 중 경계가 8초 넘게 달라진 곡: refine 이 못 잡음), unev(평가 못 한 후보 수)
shortcut: refine/snap 을 다시 돌리지 않는 상류 평가라 경계 hit 은 보지 않는다. 덮이지 않은 영역(새 후보)은 평가 불가라 'new' 는 하한이다.
사용: python experiments/sweep_detect.py selftest"""
import json, os, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
os.chdir(ROOT)
import numpy as np
import detect
import paths

HOP = 0.5
BASEP = dict(detect.P, vocal_thr=0.2)                      # 파이프라인 기본 (pipeline.analyze -> vocal_thr=0.2)
_real_cache_of = paths.cache_of
_tmp = {}


def wav_of(vid):
    for p in (ROOT / f"data/vod/{vid}.wav", ROOT / f"data/vod/nas/{vid}.wav"):
        if p.exists():
            return p


def timeline(wav):
    """cache/detect/<이름>.vocal.json -> 0.5초 격자 보컬 비율 배열(덮이지 않은 곳 NaN)"""
    a = np.load(_real_cache_of(wav, ".scores.npy"), mmap_mode="r")
    V = np.full(len(a) + 40, np.nan, np.float32)
    voc = json.load(open(_real_cache_of(wav, ".vocal.json")))
    for k, r in voc.items():
        s0 = float(k.split("-")[0])
        for n, x in enumerate(r):
            i = int(round((s0 + 5 * n) / HOP))
            V[i:i + 10] = x
    return V, voc


def derive(V, voc, s0, e0):
    key = f"{s0}-{e0}"
    if key in voc:
        return voc[key], True
    n = int((e0 - s0) // 5)
    out, ok = [], True
    for k in range(n):
        i = int(round((s0 + 5 * k) / HOP))
        seg = V[i:i + 10]
        if len(seg) < 10 or np.isnan(seg).all():
            ok = False
            out.append(0.0)
        else:
            out.append(float(np.nanmean(seg)))
    return out, ok


class Replay:
    def __init__(self, vid):
        self.vid, self.wav = vid, wav_of(vid)
        self.V, self.voc = timeline(self.wav)
        self.a = np.load(_real_cache_of(self.wav, ".scores.npy"))
        self.dir = tempfile.mkdtemp()

    def run(self, P):
        """반환 (segments, 평가 못 한 후보 수). detect.detect 원본이 temp 보컬 캐시를 읽는다."""
        a = self.a
        cands = [(cs, ce, max(0.0, cs - P["pad_s"]), ce + P["pad_s"]) for cs, ce in detect.candidates(a, P)]
        cache, bad = {}, 0
        for c in cands:
            r, ok = derive(self.V, self.voc, c[2], c[3])
            cache[f"{c[2]}-{c[3]}"] = r
            bad += not ok
        f = Path(self.dir) / "v.json"
        f.write_text(json.dumps(cache))

        def co(wav, ext):
            return f if ext == ".vocal.json" else _real_cache_of(wav, ext)
        detect.cache_of = co
        try:
            segs = detect.detect(self.wav, False, P, "cpu")
        finally:
            detect.cache_of = _real_cache_of
        return [s for s in segs if s["keep"]], bad


def labels():
    """평가 대상: golden 113(2_refine 의 start0/end0 = detect 경계), 메모 그룹(base 경계). {vid: [(kind, s, e)]}"""
    import golden_gate as G, audit_engine as E, memo_audit as M
    Gd = json.load(open(G.GOLD, encoding="utf8"))
    exp = json.load(open(M.EXP, encoding="utf8"))
    T = {}
    for e in Gd["songs"]:
        for g in E.kept(e["vid"]):
            if abs(g["start"] - e["refine"][0]) < 0.2 and abs(g["end"] - e["refine"][1]) < 0.2:
                T.setdefault(e["vid"], []).append(("gold", g.get("start0", g["start"]), g.get("end0", g["end"]), e["id"]))
    for g in exp["groups"]:
        T.setdefault(g["vno"], []).append(("N" if g["lab"] == "N" else "L", g["base"][0], g["base"][1], g["gid"]))
    return T


def ovl(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def match(segs, s, e):
    c = [x for x in segs if ovl(x["start"], x["end"], s, e) > 0.5 * min(e - s, x["end"] - x["start"])]
    return max(c, key=lambda x: ovl(x["start"], x["end"], s, e), default=None)


def evaluate_vid(vid, P, base_segs, T):
    R = Replay(vid) if vid not in _RC else _RC[vid]
    _RC[vid] = R
    segs, bad = R.run(P)
    out = dict(keep_n=len(segs), unev=bad, gold=0, gold_n=0, L=0, L_n=0, N=0, N_n=0, new=0, lost=0, drift8=0, drift_abs=0.0)
    for kind, s, e, _ in T.get(vid, []):
        m = match(segs, s, e)
        if kind == "gold":
            out["gold_n"] += 1
            if m:
                out["gold"] += 1
                d = max(abs(m["start"] - s), abs(m["end"] - e))
                out["drift_abs"] += d
                out["drift8"] += d > 8
        elif kind == "L":
            out["L_n"] += 1; out["L"] += m is not None
        else:
            out["N_n"] += 1; out["N"] += m is not None
    out["new"] = sum(match(base_segs, x["start"], x["end"]) is None for x in segs)
    out["lost"] = sum(match(segs, x["start"], x["end"]) is None for x in base_segs)
    return out


_RC = {}


def _job(a):
    vids, cfg, base, T = a
    import tune
    undo = tune.apply({k: v for k, v in cfg.items() if not k.startswith("detect.P.")})
    P = dict(BASEP, **{k[9:]: v for k, v in cfg.items() if k.startswith("detect.P.")})
    try:
        return {v: evaluate_vid(v, P, base[v], T) for v in vids}
    finally:
        undo()


def sumup(parts):
    tot = {}
    for p in parts:
        for v in p.values():
            for k, x in v.items():
                tot[k] = tot.get(k, 0) + x
    tot["drift_abs"] = round(tot.get("drift_abs", 0.0) / max(1, tot.get("gold", 1)), 2)
    return tot


class DetEval:
    def __init__(self, workers=8):
        import multiprocessing as mp
        self.T = labels()
        self.vids = sorted(v for v in {p.name for p in (ROOT / "out").iterdir() if (p / "1_detect.json").exists()} if wav_of(v) and Path(_real_cache_of(wav_of(v), ".vocal.json")).exists())
        self.base = {v: [s for s in json.load(open(ROOT / "out" / v / "1_detect.json", encoding="utf8")) if s["keep"]] for v in self.vids}
        self.shards = [self.vids[i::workers] for i in range(workers)]
        self.pool = mp.get_context("spawn").Pool(workers) if workers > 1 else None

    def evaluate(self, cfg):
        jobs = [(sh, cfg, {v: self.base[v] for v in sh}, {v: self.T.get(v, []) for v in sh}) for sh in self.shards]
        parts = self.pool.map(_job, jobs) if self.pool else [_job(j) for j in jobs]
        return sumup(parts)

    def close(self):
        if self.pool:
            self.pool.close(); self.pool.join()


def selftest():
    vids = [p.name for p in (ROOT / "out").iterdir() if (p / "1_detect.json").exists() and wav_of(p.name)]
    bad = []
    for v in vids[:12]:
        w = wav_of(v)
        if not Path(_real_cache_of(w, ".vocal.json")).exists():
            continue
        R = Replay(v)
        segs, unev = R.run(BASEP)
        base = [s for s in json.load(open(ROOT / "out" / v / "1_detect.json", encoding="utf8")) if s["keep"]]
        ok = len(segs) == len(base) and all(abs(a["start"] - b["start"]) < 0.01 and abs(a["end"] - b["end"]) < 0.01 for a, b in zip(sorted(segs, key=lambda s: s["start"]), sorted(base, key=lambda s: s["start"])))
        if not ok or unev:
            bad.append((v, len(segs), len(base), unev))
    assert not bad, bad
    print("detect 재생 == 1_detect.json (12방송) ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()


GRID = {"smooth_s": [2, 3, 4, 6, 8, 10, 12], "music_min": [.3, .4, .5, .6, .7], "speech_max": [.15, .2, .3, .4, .5], "gap_s": [5, 10, 15, 20, 25, 30, 40], "cand_min_s": [30, 45, 60, 75, 90],
        "vocal_thr": [.1, .15, .2, .25, .3, .4, .5], "win_speech_max": [.1, .15, .25, .35, .5], "win_music_min": [.3, .4, .5, .6, .7], "min_len_s": [60, 75, 90, 105, 120], "max_len_s": [300, 330, 360, 400, 480],
        "talk_break_s": [5, 10, 15, 20, 30, 45], "min_cover": [.4, .5, .6, .7, .8, .9], "seg_speech_max": [.06, .09, .12, .15, .2, .3], "seg_music_min": [.4, .5, .6, .7, .8], "pad_s": [0, 5, 10, 15, 20],
        "ext_back_s": [15, 30, 45, 60, 90], "ext_fwd_s": [10, 20, 30, 45, 60], "ext_tail_s": [0, .75, 1.5, 2.25, 3]}
GRID_FN = {"detect.walk.dip": [1.5, 2, 3, 4, 6], "detect.walk.thr": [.3, .4, .5, .6, .7]}


def oat(out="cache/proto_sweep/detect_oat.json", workers=8):
    ev = DetEval(workers)
    base = ev.evaluate({})
    print("기준", base, flush=True)
    res, t0 = {}, time.time()
    items = [(f"detect.P.{k}", v) for k, v in GRID.items()] + list(GRID_FN.items())
    for key, vals in items:
        rows = []
        for v in vals:
            r = ev.evaluate({key: v})
            rows.append(dict(v=v, **r))
        res[key] = rows
        print(f"{key:22} " + " | ".join(f"{r['v']:g}: gold {r['gold']} L {r['L']} N {r['N']} keep {r['keep_n']} new {r['new']} lost {r['lost']} dr8 {r['drift8']} unev {r['unev']}" for r in rows), f"({time.time() - t0:.0f}s)", flush=True)
        json.dump(dict(base=base, params=res), open(out, "w", encoding="utf8"))
    ev.close()


if __name__ == "__main__" and sys.argv[1:] == ["oat"]:
    oat()
