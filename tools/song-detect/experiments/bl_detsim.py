"""(e) detect 단계 분할 시뮬레이션: GPU 재탐지 없이 cache/detect 의 YAMNet 점수와 5초 창 보컬 비율(vocal.json)로 detect.detect() 뒷절반(sung 창 -> 구간 -> keep)을 그대로 재현하고,
gap_s / talk_break_s / 창 임계 / 계층(히스테리시스) 병합 변형이 곡 조각화(#20, #144 등)를 얼마나 푸는지, 승인 라이브끼리 거짓 병합이 생기는지 잰다.
검증: 기본 파라미터(pipeline 과 같은 vocal_thr=0.2)가 out/<방송>/1_detect.json 의 keep 구간을 그대로 재현해야 한다(assert).
shortcut: gap_s 를 키워 후보(candidates) 자체가 바뀌면 vocal 캐시 키가 달라 시뮬레이션 불가 -> 그 후보는 '캐시 없음'으로 세고 건너뛴다. 병합 후 refine(0.1초 YAMNet)은 다시 돌리지 않는다(경계는 detect 확장값)."""
import sys, os, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments")); os.chdir(ROOT)
import numpy as np
import detect as D
from paths import cache_of
import memo_audit as M

P0 = dict(D.P, vocal_thr=0.2)
OUT = ROOT / "cache/proto_boundary"


def weak_bridge(sung, weak, ws, gap_lo):
    """히스테리시스: 약한 창(weak)이 이어진 구간 중 sung 코어를 하나라도 품은 구간 전체를 sung 으로 올린다. 약한 구간 사이 틈은 gap_lo 초 이하만 이어 붙인다."""
    up = sung.copy()
    for s, e in D.runs(weak | sung, gap_lo, ws):
        a_, b_ = int(round(s / ws)), int(round(e / ws))
        if sung[a_:b_].any():
            up[a_:b_] = weak[a_:b_] | sung[a_:b_] | True
    return up


def sim(v, p, link=None):
    """detect.detect() 뒷절반. link=(vocal_lo, gap_lo): 히스테리시스."""
    w = ROOT / f"data/vod/nas/{v}.wav"
    a = np.load(cache_of(w, ".scores.npy"))
    cf = cache_of(w, ".vocal.json")
    cache = json.load(open(cf)) if Path(cf).exists() else {}
    out, miss, ws = [], 0, p["vocal_win_s"]
    for cs, ce in D.candidates(a, dict(p, gap_s=20)):       # 후보 묶음은 항상 gap_s=20(vocal 캐시 키가 이것에 맞춰져 있다), 변형 gap_s 는 sung 창 묶기에만
        s0, e0 = max(0.0, cs - p["pad_s"]), ce + p["pad_s"]
        key = f"{s0}-{e0}"
        if key not in cache:
            miss += 1
            continue
        r = np.array(cache[key], dtype=np.float32)
        sp, mu = D.win_mean(a, 1, s0, ws, len(r)), D.win_mean(a, 2, s0, ws, len(r))
        sung = (r >= p["vocal_thr"]) & (sp <= p["win_speech_max"]) & (mu >= p["win_music_min"])
        sung_run = sung
        if link:
            weak = (r >= link[0]) & (sp <= p["win_speech_max"]) & (mu >= p["win_music_min"])
            sung_run = weak_bridge(sung, weak, ws, link[1])
        rs = D.runs(sung_run, p["gap_s"], ws)
        for s, e in D.split_at_talk(rs, sung_run, sp > p["win_speech_max"], ws, p["talk_break_s"]):
            a_, b_ = int(s / ws), int(e / ws)
            cover = float(sung_run[a_:b_].mean())
            seg_sp, seg_mu = float(sp[a_:b_].mean()), float(mu[a_:b_].mean())
            keep = p["min_len_s"] <= (e - s) <= p["max_len_s"] and cover >= p["min_cover"] and seg_sp <= p["seg_speech_max"] and seg_mu >= p["seg_music_min"]
            s1, e1 = D.extend(a, s0 + s, s0 + e, p) if keep else (s0 + s, s0 + e)
            out.append(dict(start=s1, end=e1, keep=keep, raw=(s0 + s, s0 + e)))
    cur = None
    for o in sorted((o for o in out if o["keep"]), key=lambda o: o["start"]):
        if cur and o["start"] <= cur["end"]:
            cur["end"] = max(cur["end"], o["end"])
            o["keep"] = False
        else:
            cur = o
    return out, miss


def labeled():
    """vid -> [(구간, 종류)] 종류 = golden(승인 라이브) / live(메모 L/B) / N."""
    L = {}
    for e in json.load(open(ROOT / "experiments/golden_v4.json", encoding="utf8"))["songs"]:
        L.setdefault(e["vid"], []).append((tuple(e["refine"]), "golden"))
    for g in M.jl(M.EXP)["groups"]:
        L.setdefault(g["vno"], []).append((tuple(g["base"]), "N" if g["lab"] == "N" else "live"))
    return L


def vids_of():
    return [d.name for d in sorted((ROOT / "out").iterdir()) if (d / "1_detect.json").exists() and (ROOT / f"data/vod/nas/{d.name}.wav").exists()]


def validate():
    n = bad = 0
    for v in vids_of():
        real = sorted((g["start"], g["end"]) for g in json.load(open(ROOT / "out" / v / "1_detect.json", encoding="utf8")) if g["keep"])
        s, miss = sim(v, P0)
        mine = sorted((g["start"], g["end"]) for g in s if g["keep"])
        n += 1
        if len(real) != len(mine) or any(abs(x[0] - y[0]) > 0.6 or abs(x[1] - y[1]) > 0.6 for x, y in zip(real, mine)):
            bad += 1
            print("불일치", v, len(real), len(mine), miss)
    return n, bad


VARS = {"기본(gap20,talk15)": dict(), "gap_s 25": dict(gap_s=25), "gap_s 30": dict(gap_s=30), "gap_s 40": dict(gap_s=40), "talk_break 20": dict(talk_break_s=20), "talk_break 30": dict(talk_break_s=30),
        "gap30+talk30": dict(gap_s=30, talk_break_s=30), "win_music_min 0.4": dict(win_music_min=0.4), "win_music_min 0.3": dict(win_music_min=0.3), "vocal_thr 0.15": dict(vocal_thr=0.15), "vocal_thr 0.1": dict(vocal_thr=0.1),
        "min_cover 0.5": dict(min_cover=0.5), "min_len 60": dict(min_len_s=60), "히스테리시스 lo0.1 gap60": dict(link=(0.1, 60)), "히스테리시스 lo0.1 gap40": dict(link=(0.1, 40)), "히스테리시스 lo0.05 gap60": dict(link=(0.05, 60)),
        "gap40+히스테리시스 lo0.1": dict(gap_s=40, link=(0.1, 60))}


def evaluate():
    LB = labeled()
    vids = vids_of()
    base, rows = None, []
    for name, kw in VARS.items():
        kw = dict(kw)
        link = kw.pop("link", None)
        p = dict(P0, **kw)
        keeps, miss = {}, 0
        for v in vids:
            s, m = sim(v, p, link)
            keeps[v] = [(g["start"], g["end"]) for g in s if g["keep"]]
            miss += m
        if base is None:
            base = keeps
        ext = {}                                              # 확장 전용: 원래 keep 을 덮는(상위집합) 변형 구간만 받고 길이 360초 이하일 때만, 새 구간은 버림
        for v in vids:
            ext[v] = []
            for b in base[v]:
                cs = [sg for sg in keeps[v] if min(sg[1], b[1]) - max(sg[0], b[0]) > 0.5 * (b[1] - b[0])]
                u = (min([b[0]] + [c[0] for c in cs]), max([b[1]] + [c[1] for c in cs]))
                ext[v].append(u if u[1] - u[0] <= p["max_len_s"] else b)
        same = lambda x, y: abs(x[0] - y[0]) < 1 and abs(x[1] - y[1]) < 1
        e_ch = [(v, b, u) for v in vids for b, u in zip(base[v], ext[v]) if not same(b, u)]
        e_g = [(v, b, u) for v, b, u in e_ch if any(k == "golden" and min(b[1], iv[1]) - max(b[0], iv[0]) > 0.3 * (iv[1] - iv[0]) for iv, k in LB.get(v, []))]
        e_n = [(v, b, u) for v, b, u in e_ch if any(k == "N" and min(b[1], iv[1]) - max(b[0], iv[0]) > 0.3 * (iv[1] - iv[0]) for iv, k in LB.get(v, []))]
        e_l = [(v, b, u) for v, b, u in e_ch if any(k == "live" and min(b[1], iv[1]) - max(b[0], iv[0]) > 0.3 * (iv[1] - iv[0]) for iv, k in LB.get(v, []))]
        tot = sum(len(x) for x in keeps.values())
        chg = lost = merged_gold = 0
        cls = {"golden": 0, "live": 0, "N": 0}
        for v in vids:
            for sg in keeps[v]:
                if any(same(sg, b) for b in base[v]):
                    continue
                chg += 1
                ov = lambda iv: min(sg[1], iv[1]) - max(sg[0], iv[0])
                for k in {k for iv, k in LB.get(v, []) if ov(iv) > 0.3 * (iv[1] - iv[0])}:
                    cls[k] += 1
                if sum(1 for iv, k in LB.get(v, []) if k == "golden" and ov(iv) > 0.3 * (iv[1] - iv[0])) >= 2:
                    merged_gold += 1                              # 거짓 병합: 한 keep 이 승인 라이브 2곡 이상과 각각 30% 넘게 겹침
            for b in base[v]:
                if not any(min(sg[1], b[1]) - max(sg[0], b[0]) > 0.5 * (b[1] - b[0]) for sg in keeps[v]):
                    lost += 1                                     # 원래 keep 이 절반 넘게 덮이지 않음
        t20 = [sg for sg in keeps.get("2026-10-04_rize_1", []) if sg[1] > 10850 and sg[0] < 11170]
        t144 = [sg for sg in keeps.get("2026-10-24_toa_3", []) if sg[1] > 5500 and sg[0] < 5660]
        rows.append(dict(name=name, keep=tot, changed=chg, lost=lost, changed_on=cls, merged_golden=merged_gold, nocache=miss, ext_changed=len(e_ch), ext_golden=[[v, round(b[0]), round(u[0] - b[0], 1), round(u[1] - b[1], 1)] for v, b, u in e_g], ext_live=len(e_l), ext_N=len(e_n), t20=[[round(x) for x in s] for s in t20], t144=[[round(x) for x in s] for s in t144]))
        print(f"{name:26s} keep {tot:3d} 바뀐 {chg:3d} (승인 {cls['golden']} 라이브 {cls['live']} N {cls['N']}) 승인 2곡 병합 {merged_gold} 사라짐 {lost} 캐시없음 {miss} | 확장전용: 바뀐 {len(e_ch)} (승인 {len(e_g)} 라이브 {len(e_l)} N {len(e_n)}) | #20 {rows[-1]['t20']} #144 {rows[-1]['t144']}", flush=True)
    (OUT / "detsim.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf8")


if __name__ == "__main__":
    if sys.argv[1:] == ["validate"]:
        n, bad = validate()
        print(f"방송 {n}개 중 기본 파라미터가 1_detect.json keep 을 재현하지 못한 방송 {bad}")
        assert bad == 0
    else:
        evaluate()
