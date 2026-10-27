"""회귀 감사 1단계(읽기 전용): 모든 방송의 keep 후보에 대해 v3(snap 규칙 전부 끔, 컷 여유 v3) 와 v4(현재) 경계/등급을 재계산해 cache/audit/master.json 에 쓴다.
변한 후보(곡 경계 0.05초 초과)는 규칙별 단독 켬(only) 과 하나만 끔(loo) 도 계산해 원인 규칙을 기록한다.
v3 등급 = 이전 카드(NAS: cache/pre_v4/<방송>/cards, VOD: out/<id>/cards), v4 등급 = NAS 는 현재 카드, VOD 는 4_scene.json 으로 현재 route 를 재현(tier+known_pos+known_neg)."""
import sys, json, glob, os, copy, gc
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_engine as E
from audit_engine import ROOT, ALL
import route

def cards(d):
    return [json.load(open(f, encoding="utf8")) for f in sorted(glob.glob(str(d / "cards" / "*.json")))]

def cmatch(cs, rs, re_):
    """카드의 boundary.refine 가 (rs,re) 와 같은 것."""
    return next((c for c in cs if abs(c["boundary"]["refine"][0] - rs) < 0.2 and abs(c["boundary"]["refine"][1] - re_) < 0.2), None)

def sim_tier(vid, g4, has_refs, s, e):
    g = copy.deepcopy(g4); g["start"], g["end"], g["len"] = s, e, e - s
    try:
        import piano_gate; piano_gate.annotate(vid, [g])
    except Exception: pass
    g["tier"], g["tier_why"] = route.tier(g, has_refs)
    route.known_pos(vid, g); route.known_neg(vid, g)
    return g["tier"], g["tier_why"], g.get("ref_bd")

def main():
    os.chdir(ROOT)
    out = []
    for d in sorted((ROOT / "out").iterdir()):
        vid = d.name
        if not (d / "2_refine.json").exists() or not (d / "4_scene.json").exists() or not E.wav_path(vid): continue
        nas = vid.startswith("20")
        K = E.kept(vid)
        sc = json.load(open(d / "4_scene.json", encoding="utf8"))
        segs4 = sc["segs"]
        if len(segs4) != len(K): print("seg 수 불일치", vid, len(segs4), len(K)); continue
        c3 = cards(ROOT / "cache/pre_v4" / vid) if nas else cards(d)
        c4 = cards(d) if nas else None
        for i, g in enumerate(K):
            rs, re_ = g["start"], g["end"]
            v3 = E.calc(vid, rs, re_, ALL, False)
            v4 = E.calc(vid, rs, re_, set(), True)
            r = dict(vid=vid, nas=nas, k=i, refine=[rs, re_], v3=v3, v4=v4, tstd=segs4[i].get("tstd"), multi=segs4[i].get("multi"), scene=segs4[i].get("scene"))
            changed = max(abs(v4["song_s"] - v3["song_s"]), abs(v4["song_e"] - v3["song_e"])) > 0.05
            if changed:
                r["only"], r["loo"] = {}, {}
                for rule in sorted(ALL):
                    o = E.calc(vid, rs, re_, ALL - {rule}, False); l = E.calc(vid, rs, re_, {rule}, False)
                    r["only"][rule] = [o["song_s"] - v3["song_s"], o["song_e"] - v3["song_e"]]
                    r["loo"][rule] = [l["song_s"] - v4["song_s"], l["song_e"] - v4["song_e"]]   # 이 규칙을 끄면 v4 에서 얼마나 달라지나
            cc3 = cmatch(c3, rs, re_)
            r["tier3"] = (cc3["tier"], cc3["tier_why"]) if cc3 else None
            if nas:
                cc4 = cmatch(c4, rs, re_)
                r["tier4"] = (cc4["tier"], cc4["tier_why"], cc4.get("ref_bd")) if cc4 else None
            r["tier4_sim"] = sim_tier(vid, segs4[i], sc["has_refs"], v4["song_s"], v4["song_e"])
            out.append(r)
        E._W.clear(); gc.collect()
        print(vid, len(K), flush=True)
    json.dump(out, open(ROOT / "cache/audit/master.json", "w", encoding="utf8"), ensure_ascii=False, indent=0)
    print("total", len(out))

if __name__ == "__main__":
    main()
