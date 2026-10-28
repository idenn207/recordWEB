"""전사 설정 여러 개를 같은 곡 집합(모든 태그에 전사가 있는 곡)에서 비교하는 한 줄 표.
  python experiments/asr_table.py <태그> <태그> ... [--k 3 --W 20 --gap 8 --sing 0.15 --music 0.3]
열: n곡 / rtf(처리초/오디오초) / VRAM(MB) / 가사단어/분(라이브 곡 안) / 환각 세그먼트 비율 / 끝 early flag tp/양성 fp/음성 / 시작 late flag / 오프셋 중앙(시작,끝)+IQR / LOO hit@3 (시작,끝)"""
import sys, json, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import asr_bounds as B, asr_eval as A

ap = argparse.ArgumentParser(); ap.add_argument("tags", nargs="+"); ap.add_argument("--k", type=int, default=3); ap.add_argument("--W", type=float, default=20); ap.add_argument("--gap", type=float, default=8)
ap.add_argument("--sing", type=float, default=B.P["sing"]); ap.add_argument("--music", type=float, default=B.P["music"]); ap.add_argument("--cr", type=float, default=B.P["cr"]); ap.add_argument("--alp", type=float, default=B.P["alp"])
ap.add_argument("--nsp", type=float, default=B.P["nsp"])
a = ap.parse_args()
p = dict(B.P, sing=a.sing, music=a.music, cr=a.cr, alp=a.alp, nsp=a.nsp)
Ds = {t: A.prep(t, p) for t in a.tags}
common = set.intersection(*[set(D) for D in Ds.values()])
print(f"공통 곡 {len(common)}개 (p={ {k: p[k] for k in ('cr','alp','nsp','sing','music')} }, k={a.k} W={a.W} gap={a.gap})")
print(f"{'태그':20} {'rtf':>6} {'MB':>5} {'단어/분':>7} {'환각%':>5} | {'끝 tp/pos':>9} {'fp/neg':>7} | {'시작 tp/pos':>10} {'fp/neg':>7} | {'오프셋 시작 med[IQR]':>22} {'끝 med[IQR]':>20} | LOOhit3 시작 끝")
for t, D in Ds.items():
    D = {k: v for k, v in D.items() if k in common}
    m = json.load(open(Path(__file__).resolve().parent.parent / "cache/proto_asr/tx" / t / "meta.json"))
    nw = sum(len(v[1]) for v in D.values()); mins = sum((v[0]["base"][1] - v[0]["base"][0]) for v in D.values()) / 60
    segs = [s for v in D.values() for s in v[2]["segs"]]
    hall = 100 * np.mean([s["cr"] > p["cr"] or s["alp"] < p["alp"] or s["nsp"] > p["nsp"] for s in segs]) if segs else 0
    R = A.verifier(D, a.W, a.gap, a.k)
    S, E = A.offsets(D, 30)
    f = lambda x: f"{np.median(x):6.1f}[{np.percentile(x, 25):.0f},{np.percentile(x, 75):.0f}]" if len(x) else "-"
    loo = lambda x: sum(abs(x[i] - np.median(np.delete(x, i))) <= 3 for i in range(len(x))) if len(x) > 3 else -1
    print(f"{t:20} {m.get('rtf', 0):6.3f} {m.get('vram_after_mb', 0):5} {nw / mins:7.1f} {hall:5.1f} | {R['end']['tp']:>4}/{R['end']['pos']:<4} {R['end']['fp']:>3}/{R['end']['neg']:<3} | {R['start']['tp']:>5}/{R['start']['pos']:<4} {R['start']['fp']:>3}/{R['start']['neg']:<3} | {f(S):>22} {f(E):>20} | {loo(S)}/{len(S)} {loo(E)}/{len(E)}")
