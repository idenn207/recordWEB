"""회귀 감사 공용 로더(읽기 전용): v3(out/stale_v3) 와 v4(out/final*) 완성본 json, 곡 매칭."""
import json, glob, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

def _load(pat):
    out = []
    for f in sorted(glob.glob(str(ROOT / pat), recursive=True)):
        j = json.load(open(f, encoding="utf8"))
        p = Path(f)
        j["_f"] = str(p.relative_to(ROOT)).replace("\\", "/")
        j["_slug"] = p.parent.name
        j["_stem"] = p.stem
        j["_dir"] = "final_review" if "final_review" in j["_f"] else "final"
        out.append(j)
    return out

def v3(): return _load("out/stale_v3/final*/*/*.json")
def v4(): return _load("out/final/*/*.json") + _load("out/final_review/*/*.json")

def ov(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0)) / max(1e-9, min(a1 - a0, b1 - b0))

def name_of(slug): return re.sub(r"^\d+_[^_]+_", "", slug)   # 2026-10-06_nana_1

def match(j, pool, thr=0.5):
    """j(song_start/end, slug) 와 같은 방송에서 겹침 최대인 pool 항목."""
    best, bo = None, thr
    for p in pool:
        if p["_slug"] != j["_slug"]: continue
        o = ov(j["song_start"], j["song_end"], p["song_start"], p["song_end"])
        if o > bo: best, bo = p, o
    return best
