"""sweep 트랙 공용 평가기: 경계 규칙 상수(tune.py 키)를 바꿔 golden gate + 메모 감사 지표를 빠르게 낸다.
- fast_rms_db : snap.rms_db 와 같은 값(프레임 시작 샘플 int(t*SR) 동일)을 한 번에 벡터로 계산(원본은 프레임마다 파이썬 루프, 전체 시간의 95%). install() 로 snap/audit_engine 에 끼운다.
- evaluate(cfg) : 병렬 작업자(방송 단위 분할)가 golden 113곡 + 메모 대상 곡의 경계를 계산 -> 지표 dict. cfg 는 tune.apply 키. 병렬은 CPU 프로세스(분기가 많은 순차 규칙이라 GPU 벡터화 이점이 없음, 근거는 experiments_log/sweep.md).
- refine 편향(refine.refine.bias_start/bias_end)은 YAMNet 재실행 없이 '찾은 경계(start != start0)'에 (새 편향 - 기존 편향)을 더해 흉내 낸다.
지표(dict 키): gold_dev(golden 이탈 건수, 목표 0), gold_flags, hit05/hit3/hit10(메모 숫자 정답 22곡-경계 중), med_err, dir_pass(27), ok_pass(67), len_gt5, vanished, multi, moved2(전체 keep 구간 중 기준 설정 대비 2초 넘게 움직인 수, wide=True 일 때)
사용: python experiments/sweep_core.py selftest   (기준 설정이 golden_gate/memo_audit 와 같은 값을 내는지, fast_rms_db 가 원본과 같은지)"""
import copy, json, os, sys, time, gc
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
os.chdir(ROOT)
import numpy as np
import snap

SR, FR = 16000, 0.1
_orig_rms = snap.rms_db


_CACHE, _CB, _CMAX = {}, [0], 200e6       # (파일, t0, t1) -> (ts, db): 설정이 달라도 경계가 같은 호출이 대부분이라 바이트 상한 LRU 로 재사용


def fast_rms_db(pcm, t0, t1):
    """snap.rms_db 와 같은 (시각, dBFS). 프레임 길이는 1600 고정(원본은 float 반올림으로 1599~1601 샘플이 섞임: 0.003dB 미만 차이). 파일 끝을 넘으면 원본."""
    key = (getattr(pcm, "filename", id(pcm)), t0, t1)
    hit = _CACHE.pop(key, None)
    if hit is not None:
        _CACHE[key] = hit
        return hit
    ts = np.arange(max(0.0, t0), t1, FR)
    n = len(ts)
    if n == 0:
        return _orig_rms(pcm, t0, t1)
    st = (ts * SR).astype(np.int64)
    fl = int(FR * SR)
    if st[-1] + fl > len(pcm):
        return _orig_rms(pcm, t0, t1)
    base = np.asarray(pcm)
    d = np.diff(st)
    if n == 1 or ((d >= fl - 1) & (d <= fl + 1)).all():
        if (d == fl).all():
            x = base[st[0]:st[0] + n * fl].reshape(n, fl)
        else:
            x = base[st[:, None] + np.arange(fl)[None, :]]
    else:
        return _orig_rms(pcm, t0, t1)
    x = x.astype(np.float32)
    ms = np.einsum("ij,ij->i", x, x) / (fl * 32768.0 ** 2)
    out = (ts, 20 * np.log10(np.sqrt(ms + 1e-12)))
    _CACHE[key] = out
    _CB[0] += out[1].nbytes * 2
    while _CB[0] > _CMAX:
        k0 = next(iter(_CACHE)); v = _CACHE.pop(k0); _CB[0] -= v[1].nbytes * 2
    return out


def install():
    snap.rms_db = fast_rms_db
    try:
        import audit_engine
        audit_engine.rms_db = fast_rms_db
    except Exception:
        pass


# ---------------------------------------------------------------- 대상 목록
def targets(wide=False):
    """(golden 곡 목록, 메모 그룹 목록, vid -> [(rs, re, found_s, found_e)] 계산할 refine 후보)"""
    import golden_gate as G, audit_engine as E, memo_audit as M
    Gd = json.load(open(G.GOLD, encoding="utf8"))
    exp = json.load(open(M.EXP, encoding="utf8"))
    need = {}
    def add(vid, rs, re_):
        for g in E.kept(vid):
            if abs(g["start"] - rs) < 0.2 and abs(g["end"] - re_) < 0.2:
                need.setdefault(vid, {})[(g["start"], g["end"])] = (abs(g["start"] - g.get("start0", g["start"])) > 1e-9, abs(g["end"] - g.get("end0", g["end"])) > 1e-9)
    for e in Gd["songs"]:
        add(e["vid"], *e["refine"])
    for g in exp["groups"]:
        for k in E.kept(g["vno"]):
            if min(k["end"], g["base"][1]) - max(k["start"], g["base"][0]) > 0.0:       # 기준 경계와 조금이라도 겹치면(후보 경계는 설정에 따라 이동하므로 넉넉히)
                need.setdefault(g["vno"], {})[(k["start"], k["end"])] = (abs(k["start"] - k.get("start0", k["start"])) > 1e-9, abs(k["end"] - k.get("end0", k["end"])) > 1e-9)
    if wide:                                                 # 정답 없는 구간까지: 전 방송 keep 후보(부작용 측정용)
        for d in sorted((ROOT / "out").iterdir()):
            if (d / "2_refine.json").exists() and E.wav_path(d.name) and (ROOT / "cache/detect" / (E.wav_path(d.name).stem + ".scores.npy")).exists():
                for g in E.kept(d.name):
                    need.setdefault(d.name, {})[(g["start"], g["end"])] = (abs(g["start"] - g.get("start0", g["start"])) > 1e-9, abs(g["end"] - g.get("end0", g["end"])) > 1e-9)
    return Gd, exp, {v: [(a, b, fs, fe) for (a, b), (fs, fe) in d.items()] for v, d in need.items()}


# ---------------------------------------------------------------- 작업자
_S = {}


def _wk_init():
    install()
    import tune
    _S["tune"] = tune


def _wk_run(args):
    """(cfg, vids, bias_delta) -> {vid: {(rs, re): calc 결과}}. 이 작업자의 tune 상태는 호출마다 적용/되돌림."""
    cfg, jobs, bias = args
    import audit_engine as E
    tune = _S["tune"]
    undo = tune.apply({k: v for k, v in cfg.items() if not k.startswith("refine.refine.")})
    out = {}
    try:
        for vid, segs in jobs.items():
            res = {}
            for rs, re_, fs, fe in segs:
                s2, e2 = rs + (bias[0] if fs else 0.0), re_ + (bias[1] if fe else 0.0)
                c = E.calc(vid, s2, e2)
                pcm, a, _ = E.wdata(vid)
                ref = float(np.median(snap.rms_db(pcm, c["song_s"], c["song_e"])[1]))
                ts, db = snap.rms_db(pcm, c["song_e"], max(c["clip_e"], c["song_e"] + 0.2))
                ix = np.clip(np.round((ts - 0.4875) / 0.5).astype(int), 0, len(a) - 1)
                tsp = int(((a[ix, 1] > 0.15) & (db > ref - 25)).sum())                 # 곡 끝~컷 사이에 들리는 말소리 프레임(0.1초) 수
                res[(rs, re_)] = dict(song_s=c["song_s"], song_e=c["song_e"], clip_s=c["clip_s"], clip_e=c["clip_e"], fix_s=c["fix_s"], fix_e=c["fix_e"], tsp=tsp)
            out[vid] = res
            if len(E._W) > 12:
                E._W.clear(); gc.collect()
    finally:
        undo()
    return out


class Evaluator:
    def __init__(self, workers=6, wide=False):
        import multiprocessing as mp
        self.Gd, self.exp, self.need = targets(wide)
        self.wide, self.baseR = wide, None
        vids = sorted(self.need, key=lambda v: -len(self.need[v]))
        self.workers = workers
        self.shards = [{} for _ in range(workers)]
        load = [0] * workers
        for v in vids:                                           # 큰 방송부터 가장 가벼운 작업자에
            i = load.index(min(load))
            self.shards[i][v] = self.need[v]
            load[i] += len(self.need[v])
        self.pool = mp.get_context("spawn").Pool(workers, initializer=_wk_init) if workers > 1 else None
        if not self.pool:
            _wk_init()
        self.base = None
        self.scene = {}

    def calc_all(self, cfg):
        b = (cfg.get("refine.refine.bias_start", 0.3) - 0.3, cfg.get("refine.refine.bias_end", 1.6) - 1.6)
        jobs = [(cfg, sh, b) for sh in self.shards if sh]
        parts = self.pool.map(_wk_run, jobs) if self.pool else [_wk_run(j) for j in jobs]
        R = {}
        for p in parts:
            R.update(p)
        return R

    # golden_gate.current 와 같은 등급 계산 (경계 계산은 밖에서)
    def _tier(self, vid, rs, re_, c):
        import audit_engine as E, route
        K = E.kept(vid)
        k = next(i for i, g in enumerate(K) if abs(g["start"] - rs) < 0.2 and abs(g["end"] - re_) < 0.2)
        if vid not in self.scene:
            self.scene[vid] = json.load(open(ROOT / "out" / vid / "4_scene.json", encoding="utf8"))
        sc = self.scene[vid]
        g = copy.deepcopy(sc["segs"][k]); g["start"], g["end"], g["len"] = c["fix_s"], c["fix_e"], c["fix_e"] - c["fix_s"]
        try:
            import piano_gate; piano_gate.annotate(vid, [g])
        except Exception:
            pass
        g["tier"], g["tier_why"] = route.tier(g, sc["has_refs"])
        route.known_pos(vid, g); route.known_neg(vid, g)
        return g["tier"], g["tier_why"]

    def gold_flags(self, R, cfg):
        """golden_gate.check 와 같은 이탈 판정. 반환 [(id, flag)]"""
        import golden_gate as G
        import tune
        undo = tune.apply({k: v for k, v in cfg.items() if k.startswith(("route.", "scene_multi.", "n_signals."))})
        try:
            cur = {}
            for e in self.Gd["songs"]:
                c = next((v for (a, b), v in R[e["vid"]].items() if abs(a - e["refine"][0]) < 0.2 and abs(b - e["refine"][1]) < 0.2), None)
                if c is None:
                    cur[e["id"]] = None; continue
                t, w = self._tier(e["vid"], *e["refine"], c)
                cur[e["id"]] = dict(s=c["song_s"], e=c["song_e"], clip=c["clip_e"] - c["clip_s"], tier=t, why=w)
        finally:
            undo()
        dev = []
        for e in self.Gd["songs"]:
            c, f = cur[e["id"]], e["frozen"]
            if c is None:
                dev.append((e["id"], "곡사라짐")); continue
            if abs(c["s"] - f["s"]) > 2: dev.append((e["id"], "시작이동"))
            if abs(c["e"] - f["e"]) > 2: dev.append((e["id"], "끝이동"))
            if abs(c["clip"] - f["clip"]) > 3: dev.append((e["id"], "클립길이"))
            if c["tier"] == "drop": dev.append((e["id"], "곡사라짐"))
            elif G.RANK[c["tier"]] < G.RANK[e["expect"]]: dev.append((e["id"], "등급하락"))
            for i in (0, 1):
                if e["truth"] and e["truth"][i] is not None and f["err"][i] is not None:
                    err = (c["s"] if i == 0 else c["e"]) - e["truth"][i]
                    if abs(err) > abs(f["err"][i]) + 2: dev.append((e["id"], "정답멀어짐" + "시끝"[i]))
            for q in self.Gd["songs"]:
                if q is not e and q["vid"] == e["vid"] and cur[q["id"]] and G.ovl(c["s"], c["e"], cur[q["id"]]["s"], cur[q["id"]]["e"]) > 1 \
                        and G.ovl(f["s"], f["e"], q["frozen"]["s"], q["frozen"]["e"]) <= 1:
                    dev.append((e["id"], "병합겹침")); break
        return dev, cur

    def memo(self, R):
        import memo_audit as M
        slug_of = {g["vno"]: g["slug"] for g in self.exp["groups"]}
        S = []
        for vid, res in R.items():
            if vid in slug_of:
                S += [dict(slug=slug_of[vid], s=c["song_s"], e=c["song_e"], rule="engine") for c in res.values()]
        ev = M.evaluate(self.exp, S)
        return M.summarize(ev), ev

    def evaluate(self, cfg, wide=False):
        t = time.time()
        R = self.calc_all(cfg)
        dev, cur = self.gold_flags(R, cfg)
        s, ev = self.memo(R)
        out = dict(gold_dev=len(dev), gold_flags=dev, hit05=s["hit@0.5"], hit3=s["hit@3"], hit10=s["hit@10"], med_err=s["median_abs_err"], dir_pass=s["dir_pass"], dir_n=s["dir_n"],
                   ok_pass=s["ok_pass"], ok_n=s["ok_n"], len_gt5=s["len_err_gt5"], vanished=s["vanished"], multi=s["multi_output"], num_n=s["num_sides"], sec=round(time.time() - t, 2))
        if self.wide:
            if self.baseR is None:
                self.baseR = R
            mv = [(v, k) for v in R for k, c in R[v].items() if v in self.baseR and k in self.baseR[v] and max(abs(c["song_s"] - self.baseR[v][k]["song_s"]), abs(c["song_e"] - self.baseR[v][k]["song_e"])) > 2]
            out["moved2"], out["n_wide"] = len(mv), sum(len(x) for x in R.values())
            out["movedc"] = sum(1 for v in R for k, c in R[v].items() if v in self.baseR and k in self.baseR[v] and max(abs(c["clip_s"] - self.baseR[v][k]["clip_s"]), abs(c["clip_e"] - self.baseR[v][k]["clip_e"])) > 0.5)
            out["tail_sp"] = sum(c["tsp"] for v in R for c in R[v].values())
            out["tail_cut"] = round(float(np.mean([c["clip_e"] - c["song_e"] for v in R for c in R[v].values()])), 3)
        out["_R"] = R
        out["_cur"] = cur
        return out

    def close(self):
        if self.pool:
            self.pool.close(); self.pool.join()


def selftest():
    install()
    import random
    from snap import pcm_of
    w = ROOT / "data/vod/nas/2026-10-06_nana_1.wav"
    pcm = pcm_of(w)
    rnd = random.Random(1)
    for _ in range(400):
        t0 = rnd.uniform(0, len(pcm) / SR - 200)
        t1 = t0 + rnd.uniform(0.05, 120)
        a, b = _orig_rms(pcm, t0, t1)[1], fast_rms_db(pcm, t0, t1)[1]
        assert np.allclose(a, b, atol=1e-2), (t0, t1, np.abs(a - b).max())
    assert np.allclose(_orig_rms(pcm, len(pcm) / SR - 2, len(pcm) / SR + 1)[1], fast_rms_db(pcm, len(pcm) / SR - 2, len(pcm) / SR + 1)[1], equal_nan=True)      # 파일 끝 넘는 경우
    print("fast_rms_db ok")
    import golden_gate as G, memo_audit as M
    ev = Evaluator(6)
    t = time.time()
    r = ev.evaluate({})
    print("기준:", {k: v for k, v in r.items() if not k.startswith("_")}, f"{time.time() - t:.1f}s")
    assert r["gold_dev"] == 0 and (r["hit05"], r["hit3"], r["hit10"]) == (5, 9, 11) and r["dir_pass"] == 13 and r["ok_pass"] == 67 and r["len_gt5"] == 2, r
    t = time.time()
    r = ev.evaluate({"snap.E1B_VOC": 0.5})
    print(f"두 번째(웜) {time.time() - t:.1f}s")
    ev.close()
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["selftest"]:
        selftest()
