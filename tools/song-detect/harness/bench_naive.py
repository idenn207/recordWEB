"""기준선: 현행 pipeline.main 을 단계 파일(1~4)이 있는 상태로 슬러그마다 다시 돌린 시간(= route 만 바꿔도 지금은 이 비용). 스크래치 out 에서만 실행.
사용: python harness/bench_naive.py [out.json]"""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.lib import *
os.environ["SONG_NOCLIP"] = "1"
import pipeline
slugs = seed_scratch()
res = {}
t0 = time.perf_counter()
R = {r["slug"]: r for r in rows()}
for s in slugs:
    t = time.perf_counter()
    pipeline.main(R[s]["wav"], None, s, R[s]["streamer"], False, str(SCR))
    res[s] = round(time.perf_counter() - t, 2)
tot = round(time.perf_counter() - t0, 1)
json.dump(dict(total_s=tot, per_slug=res), open(sys.argv[1] if len(sys.argv) > 1 else PH / "bench_naive.json", "w"), indent=1)
print("naive route-only 61 방송", tot, "초")
