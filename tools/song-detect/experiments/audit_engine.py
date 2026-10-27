"""회귀 감사 엔진(읽기 전용): refine 경계 -> finalize.fix -> make_final.snap_quiet -> lead_pad/trail_pad 를 snap 규칙 on/off 로 재계산.
off = 끈 규칙 집합(ALL = 예전 v3 snap 과 동일). 반환: song_s, song_e(곡 경계), clip_s, clip_e(여유 포함, v4 는 컷 >= 곡 끝 + 1.0초; tail=False 면 v3)."""
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
import numpy as np
import snap, make_final
from snap import pcm_of, rms_db
from finalize import fix
from paths import cache_of
from blind9_bounds import patched

ALL = {"E1", "E1b", "E2", "E3", "S1", "S2"}
_W = {}

def wav_path(vid):
    for p in (ROOT / f"data/vod/{vid}.wav", ROOT / f"data/vod/nas/{vid}.wav"):
        if p.exists(): return p

def wdata(vid):
    if vid not in _W:
        w = wav_path(vid)
        _W[vid] = (pcm_of(w), np.load(cache_of(w, ".scores.npy")), snap.voc_of(w))
    return _W[vid]

def calc(vid, rs, re_, off=frozenset(), tail=True):
    pcm, a, voc = wdata(vid)
    undo = patched(set(off))
    try:
        g = fix(pcm, a, dict(keep=True, start=rs, end=re_, len=re_ - rs), voc)
    finally:
        undo()
    ref = float(np.median(rms_db(pcm, g["start"], g["end"])[1]))
    s, _ = make_final.snap_quiet(pcm, a, g["start"], ref)
    e, _ = make_final.snap_quiet(pcm, a, g["end"], ref)
    cs, lead = make_final.lead_pad(pcm, a, ref, s)
    ce, trail = make_final.trail_pad(pcm, a, ref, e)
    st = list(g.get("stages") or [])                    # make_final.make 와 같은 순서로 규칙 이동 기록(refine -> 컷)
    for rule, edge, b, af in (("snap_quiet", "start", g["start"], s), ("snap_quiet", "end", g["end"], e), ("lead_pad", "start", s, cs), ("trail_pad", "end", e, ce)):
        snap.mv(st, rule, edge, b, af)
    if tail: ce = snap.mv(st, "tail", "end", ce, make_final.tail_cut(pcm, a, ref, e, ce))
    return dict(song_s=s, song_e=e, clip_s=cs, clip_e=ce, snap_why=g.get("why_snap"), fix_s=g["start"], fix_e=g["end"], stages=st)

def kept(vid):
    """out/<vid>/2_refine.json 의 keep 구간(원본 순서)."""
    f = ROOT / "out" / vid / "2_refine.json"
    return [g for g in json.load(open(f, encoding="utf8")) if g["keep"]] if f.exists() else []
