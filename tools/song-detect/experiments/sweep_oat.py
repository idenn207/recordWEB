"""경계 규칙 상수의 OAT(한 번에 하나) 민감도: 각 상수를 기본값 x 배율로 바꿔 sweep_core 지표를 잰다.
사용: python experiments/sweep_oat.py [--out cache/proto_sweep/oat.json] [--only 접두어,...] [--workers 8]
출력 json: {키: {"default": v, "rows": [{"v": 값, ...지표}]}}. 요약 표는 sweep_report.py 가 만든다.
shortcut: 배율 격자라 dB/초 단위 상수의 의미 있는 간격과 안 맞을 수 있다(RUN 같은 정수는 별도 값). 확률형(0~1)은 1.0 으로 자른다."""
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sweep_core as S

FACT = [0.25, 0.5, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 2.0, 3.0]
INT = {"snap.RUN": [1, 2, 3, 4, 5, 6, 8], "snap.B_SP": [1, 2, 3, 4, 6], "snap.B_ITER": [1, 2, 3, 4, 6, 8]}
# 오염 방지로 뺀 것: 단위/표본률/성능(HOP SR FR WIN LIMIT 등), 보고서가 따로 다루는 detect/route 계열
KEYS = """snap.BACK snap.FWD snap.MARGIN snap.LOW snap.RUN snap.LOOK snap.GAP snap.HOLE snap.DROP snap.SPEECH snap.MU snap.LEAD snap.EXT_MU
snap.B_DB snap.B_GAP snap.B_TAIL snap.B_FWD snap.B_SP snap.B_ITER snap.B_MAXLEN
snap.E1_MU snap.E1_SP snap.E1_GAP snap.E1_MIN snap.E1_CAP
snap.E1B_MU snap.E1B_SP snap.E1B_GAP snap.E1B_CAP snap.E1B_DROP snap.E1B_LOUD snap.E1B_GUARD snap.E1B_VOC
snap.CODA_FAR snap.CODA_RUN snap.music_run.gap snap.deep_end.look snap.deep_end.depth snap.deep_end.minlen snap.deep_end.nxt snap.deep_end.nxt_db
snap.start_s1.gap snap.start_s1.vmax snap.start_s1.within snap.start_s1.min_left snap.start_s1.lead
snap.start_s2.vmin snap.start_s2.mumin snap.start_s2.spmax snap.start_s2.maxback
finalize.MAXRATIO make_final.TAIL make_final.TAIL_MIN make_final.TAIL_SP make_final.TAIL_DB make_final.TAIL_EXT make_final.TAIL_LOUD make_final.PAD_WIN make_final.PAD_MIN make_final.PAD_EDGE
refine.refine.bias_start refine.refine.bias_end""".split()


def grid(key, d, fine=False):
    if fine:
        if key in INT:
            return sorted({v for v in INT[key] if abs(v - d) <= 2})
        return sorted({round(d * (1 + 0.02 * k), 5) for k in range(-10, 11) if d * (1 + 0.02 * k) > 0})
    if key in INT:
        return INT[key]
    vals = [d * f for f in FACT]
    if 0 < d <= 1.0 and d != 1.0:
        vals = [min(v, 1.0) for v in vals]
    return sorted({round(v, 4) for v in vals} | {d})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="cache/proto_sweep/oat.json")
    ap.add_argument("--only", default="")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-wide", action="store_true")
    ap.add_argument("--fine", action="store_true", help="기본값 +-20% 를 2% 간격으로(실제 절벽까지 거리 측정)")
    a = ap.parse_args()
    import tune
    cur = tune.listing()
    ev = S.Evaluator(a.workers, wide=not a.no_wide)
    base = ev.evaluate({})
    print("기준", {k: v for k, v in base.items() if not k.startswith("_")}, flush=True)
    keys = [k for k in KEYS if not a.only or k.startswith(tuple(a.only.split(",")))]
    res = {}
    t0 = time.time()
    for key in keys:
        d = cur[key]
        rows = []
        for v in grid(key, d, a.fine):
            r = ev.evaluate({key: v})
            rows.append(dict(v=v, **{k: x for k, x in r.items() if not k.startswith("_")}))
        res[key] = dict(default=d, rows=rows)
        lo = [r for r in rows if r["gold_dev"] == 0]
        print(f"{key:28} 기본 {d}  golden 0 인 값 {len(lo)}/{len(rows)}  hit3 {min(r['hit3'] for r in rows)}-{max(r['hit3'] for r in rows)}  moved2 {min(r.get('moved2', 0) for r in rows)}-{max(r.get('moved2', 0) for r in rows)}  ({time.time() - t0:.0f}s)", flush=True)
        json.dump(dict(base={k: v for k, v in base.items() if not k.startswith("_")}, params=res), open(a.out, "w", encoding="utf8"), ensure_ascii=False)
    ev.close()


if __name__ == "__main__":
    main()
