"""끝 early / 시작 late 플래그 조합: musv 사슬(E1 류 점수 신호) 와 Whisper 가사 사슬을 OR / AND / 순서(musv 우선) 로 합친 결과. asr_vad_eval 의 활동 캐시(cache/proto_asr/act)와 전사를 쓴다.
  python experiments/asr_combo.py [--tx t_small_auto] [--W 40 --gap 8 --min 3]"""
import sys, os, json, argparse
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT); sys.path.insert(0, str(ROOT / "experiments")); sys.path.insert(0, str(ROOT))
import asr_bounds as B
from asr_vad_eval import chain
from asr_run import groups

ap = argparse.ArgumentParser(); ap.add_argument("--tx", default="t_small_auto"); ap.add_argument("--W", type=float, default=40); ap.add_argument("--gap", type=float, default=8); ap.add_argument("--min", type=float, default=3.0)
ap.add_argument("--chunk", type=int, default=1); ap.add_argument("--uniq", type=float, default=0.0); ap.add_argument("--maxw", type=float, default=99.0)
a = ap.parse_args()
p = dict(B.P, chunk=a.chunk, uniq=a.uniq, maxw=a.maxw)
rows = []
for g in groups():
    f = ROOT / "cache/proto_asr/act" / f"{g['gid']}.json"
    d = B.load_tx(a.tx, g["gid"])
    if g["lab"] == "N" or not f.exists() or not d:
        continue
    act = json.load(open(f))
    ly = B.lyric(B.words(d, B.scores(g["vno"]), p))
    rows.append((g, act["musv"], [[w[0], w[1]] for w in ly]))
for side, want in (("end", "early"), ("start", "late")):
    res = {k: [0, 0, 0, 0] for k in ("musv", "whisper", "OR", "AND")}
    for g, mv, wl in rows:
        sd = g["sides"][side]
        if sd["issue"] not in (want, "ok"):
            continue
        e = g["base"][1 if side == "end" else 0]
        fm = chain(mv, e, side, a.W, a.gap, a.min) is not None
        fw = chain(wl, e, side, a.W, a.gap, a.min) is not None
        for k, v in (("musv", fm), ("whisper", fw), ("OR", fm or fw), ("AND", fm and fw)):
            res[k][0 if sd["issue"] == want else 2] += v
            res[k][1 if sd["issue"] == want else 3] += 1
    print(f"[{side}] " + " | ".join(f"{k}: 양성 {v[0]}/{v[1]} 음성 {v[2]}/{v[3]}" for k, v in res.items()))
