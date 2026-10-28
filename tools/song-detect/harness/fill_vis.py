"""스크래치 루트(cache/harness/out_m)의 4_scene.json 에 화면 신호 vis 를 채운다(n_visual, NAS 프레임 + GPU). torch+open_clip 이 있는 venv python 으로 실행.
  C:/_tools/wt/venv/Scripts/python.exe harness/fill_vis.py [슬러그 ...]      (이미 vis 가 있는 후보는 건너뜀 = 이어서 실행 가능)
메인 out/ 은 건드리지 않는다. 채운 뒤 `python harness/check.py` 의 변화 리포트가 weak 변화를 보여 준다."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.lib import *
import harness.manifest as M

sys.path.insert(0, str(ROOT / "datasets"))
import nas_ingest as N

run = M.Run(vis_fn=None)
path = {r["slug"]: r["path"] for r in rows()}
slugs = sys.argv[1:] or [r["slug"] for r in rows()]
import n_visual
t = __import__("time").time()
for s in slugs:
    f = run.root / s / "4_scene.json"
    sc = json.load(open(f, encoding="utf8"))
    n = sum(g.get("vis") is None for g in sc["segs"])
    n_visual.fill(sc["segs"], N.url_of(path[s]))
    f.write_text(json.dumps(sc, ensure_ascii=False, indent=1), encoding="utf8")
    print(f"{s}: {n}후보 채움, vis 없음 {sum(g.get('vis') is None for g in sc['segs'])} ({__import__('time').time() - t:.0f}초)", flush=True)
