"""작업대 전 방송 sweep: out/<방송>/2_refine.json 의 keep 후보 전부에 제안 규칙을 얹었을 때 곡 경계가 1초 넘게 움직이는 구간과 카드 등급/장면(부작용 점검).
사용(다른 스크립트에서): from bl_sweep import sweep; sweep({"이름": prop}, policy="all"|"rev")  -> cache/proto_boundary/sweep_<이름>.json"""
import sys; sys.path.insert(0, 'experiments')
from bound_lab import *
import audit_engine as E

CARDS = {}


def cards(vid):
    if vid not in CARDS:
        CARDS[vid] = [json.load(open(c, encoding="utf8")) for c in (ROOT / "out" / vid / "cards").glob("*.json")]
    return CARDS[vid]


def tier_of(vid, s, e):
    c = max(cards(vid), key=lambda c: min(c["end"], e) - max(c["start"], s), default=None)
    return (c["tier"], c.get("multi", "?")) if c and min(c["end"], e) > max(c["start"], s) else ("--", "?")


def cand_list():
    return [(d.name, g) for d in sorted((ROOT / "out").iterdir()) if (d / "2_refine.json").exists() and E.wav_path(d.name) for g in E.kept(d.name)]


def sweep(props, policy="all", thr=1.0):
    C = cand_list()
    out = {}
    for name, p in [(None, None)] + list(props.items()):
        res = {}
        with proposing(None if p is None else (p if policy == "all" else review_only(p)), name or "base"):
            for vid, g in C:
                o = E.calc(vid, g["start"], g["end"])
                res[(vid, round(g["start"], 1))] = (o["song_s"], o["song_e"], o["clip_s"], o["clip_e"], g["end"] - g["start"])
                if len(E._W) > 2: E._W.clear()
        if name is None:
            base = res; continue
        mv = []
        for k, v in res.items():
            b = base[k]
            ds, de = v[0] - b[0], v[1] - b[1]
            if abs(ds) > thr or abs(de) > thr:
                t, m = tier_of(k[0], b[0], b[1])
                mv.append(dict(vid=k[0], start=k[1], ds=round(ds, 1), de=round(de, 1), tier=t, scene=m, len=round(b[1] - b[0])))
        by = {}
        for x in mv:
            by[x["tier"]] = by.get(x["tier"], 0) + 1
        (OUT / f"sweep_{name}.json").write_text(json.dumps(dict(n=len(C), moved=mv, by_tier=by), ensure_ascii=False, indent=1), encoding="utf8")
        out[name] = dict(n=len(C), moved=len(mv), by_tier=by)
        print(f"[sweep {name}@{policy}] 후보 {len(C)}개 중 곡 경계 {thr}초 초과 이동 {len(mv)}개, 등급별 {by}", flush=True)
    return out
