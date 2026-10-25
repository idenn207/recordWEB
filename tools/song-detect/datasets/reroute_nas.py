"""NAS 방송 전체의 장면(4_scene.json)만 지우고 pipeline 을 다시 돌려 route/카드를 새 승인 풀 기준으로 갱신(GPU 탐지 캐시 재사용). 사용: python datasets/reroute_nas.py [동시수=2]"""
import json, sys, shutil, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nas_ingest as N

rows = [r for r in json.load(open(N.IDX, encoding="utf8")) if (N.ROOT / "out" / r["slug"] / "3_final.json").exists()]


def one(r):
    (N.ROOT / "out" / r["slug"] / "4_scene.json").unlink(missing_ok=True)
    t = time.time()
    try:
        N.pipe(r)
        print(time.strftime("%H:%M:%S"), "ok", r["slug"], round(time.time() - t), flush=True)
    except Exception as e:
        print(time.strftime("%H:%M:%S"), "FAIL", r["slug"], str(e)[-200:], flush=True)


with ThreadPoolExecutor(int(sys.argv[1]) if len(sys.argv) > 1 else 2) as ex:
    list(ex.map(one, rows))
print("끝", len(rows), flush=True)
