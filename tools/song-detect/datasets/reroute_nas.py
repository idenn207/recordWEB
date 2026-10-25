"""NAS 방송 전체의 pipeline 을 다시 돌려 route/카드를 갱신(GPU 탐지 캐시 재사용). 장면(4_scene.json)은 풀에서 빠지는 방송(승인 풀에 같은 스트리머+날짜가 있는 방송)만 지워 다시 계산한다(--all 이면 전부).
사용: python datasets/reroute_nas.py [동시수=2] [--all]"""
import json, sys, shutil, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nas_ingest as N

import scene_pool
POOL = {(m["name"], m["date"]) for m in scene_pool.pool()[0]}
rows = [r for r in json.load(open(N.IDX, encoding="utf8")) if (N.ROOT / "out" / r["slug"] / "3_final.json").exists()]


def one(r):
    if "--all" in sys.argv or (r["streamer"], r["date"]) in POOL:
        (N.ROOT / "out" / r["slug"] / "4_scene.json").unlink(missing_ok=True)
    t = time.time()
    try:
        N.pipe(r)
        print(time.strftime("%H:%M:%S"), "ok", r["slug"], round(time.time() - t), flush=True)
    except Exception as e:
        print(time.strftime("%H:%M:%S"), "FAIL", r["slug"], str(e)[-200:], flush=True)


with ThreadPoolExecutor(int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 2) as ex:
    list(ex.map(one, rows))
print("끝", len(rows), flush=True)
