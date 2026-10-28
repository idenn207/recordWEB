"""scene 단계 후보 1개의 실제 비용(NAS thumbs)과 결정성 확인: 저장된 4_scene 값과 다시 계산한 값을 비교. 401 이면 즉시 중단.
사용: python harness/scene_probe.py [후보수=8]"""
import json, os, sys, time, statistics as S
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.lib import *
from harness.scene_real import real_scene_fn, NasDown
n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
sl = [r["slug"] for r in rows()]
pick = []
for s in sl[::max(1, len(sl) // n)][:n]:
    segs = json.load(open(ROOT / "out" / s / "4_scene.json", encoding="utf8"))["segs"]
    if segs:
        pick.append((s, segs[len(segs) // 2]))
st, out = [], []
try:
    for s, g in pick:
        r = real_scene_fn(s, g, st)
        out.append(dict(slug=s, start=round(g["start"]), len=round(g["len"]), sec=round(st[-1], 1), same_multi=r["multi"] == g.get("multi"),
                        d_tstd=None if r["tstd"] is None or g.get("tstd") is None else round(r["tstd"] - g["tstd"], 3), d_scene=None if r["scene"] is None or g.get("scene") is None else round(r["scene"] - g["scene"], 4)))
        print(out[-1], flush=True)
except NasDown as e:
    print("NAS 중단:", e)
json.dump(out, open(PH / "scene_probe.json", "w"), indent=1)
if st:
    print(f"후보 {len(st)}개 thumbs 평균 {S.mean(st):.1f}초 (중앙값 {S.median(st):.1f}, 최대 {max(st):.1f})")
