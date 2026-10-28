"""축 (g) 서비스 처리량/지연 측정. Go 서비스(songd)를 띄우고 replay 작업을 보낸다.
  1. 호출당 파이썬 시작(spawn) vs 상주 작업자 지연
  2. 작업자 수별 처리량(동기 요청 동시 클라이언트 64, 작업 200개)
  3. 리소스 모드 cap80 vs unlimited (처리량, 큐 대기, 모드 전환 시간)
  4. 혼합 부하: 무거운 sweep(30조합) 사이에 가벼운 replay 의 큐 대기
사용: python harness/bench_svc.py -> cache/proto_harness/bench_svc.json"""
import http.client, json, os, subprocess, sys, time, statistics as S
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.lib import *

EXE, PORT = str(PH / "songd.exe"), 8790
res = {}
SW = {"grid": [{"npp": {"rel_db": -9 + 0.3 * i, "bursts": 2.1}} for i in range(20)]}        # 처리량용 작업: sweep 20조합(작업자 안에서 약 70ms)


def call(method, path, body=None):
    c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=300)
    c.request(method, path, json.dumps(body) if body is not None else None, {"Content-Type": "application/json"})
    r = c.getresponse(); d = json.loads(r.read()); c.close(); return d


BOOT = {}


def start(n=0, mode="cap80"):
    t0 = time.perf_counter()
    p = subprocess.Popen([EXE, "-addr", f"127.0.0.1:{PORT}", "-mode", mode, "-n", str(n), "-py", sys.executable, "-worker", str(ROOT / "harness/worker.py")], stderr=subprocess.DEVNULL)
    for _ in range(300):
        try:
            h = call("GET", "/healthz")
            break
        except Exception:
            time.sleep(0.1)
    call("POST", "/jobs?wait=1", {"op": "ping"})          # 첫 ping 이 돌아오면 작업자 1개가 카드 적재까지 끝낸 것
    BOOT["s"] = round(time.perf_counter() - t0, 2)
    return p


def ready(n):
    """작업자가 모두 뜰 때까지(상주 작업자는 카드를 올리는 데 시간이 듦): ping 을 n 개 동시에 보내 전부 응답하면 준비 끝"""
    t = time.perf_counter()
    with ThreadPoolExecutor(n * 2) as ex:
        list(ex.map(lambda _: call("POST", "/jobs?wait=1", {"op": "ping"}), range(n * 2)))
    return time.perf_counter() - t


def stop(p):
    p.terminate(); p.wait()          # 작업자는 표준입력이 닫히면 스스로 끝난다
    time.sleep(0.5)


# 1. spawn vs 상주
t = []
for _ in range(5):
    t0 = time.perf_counter()
    subprocess.run([sys.executable, str(ROOT / "harness/worker.py")], input='{"id":1,"op":"replay","args":{"registry":false}}\n', capture_output=True, text=True)
    t.append(time.perf_counter() - t0)
res["spawn_ms"] = round(S.median(t) * 1000)
p = start(1)
cold = ready(1)
lat = []
for _ in range(30):
    t0 = time.perf_counter(); r = call("POST", "/jobs?wait=1", {"op": "replay", "args": {"registry": False}}); lat.append((time.perf_counter() - t0) * 1000)
res["resident"] = dict(cold_start_s=BOOT["s"], p50_ms=round(S.median(lat), 1), p95_ms=round(sorted(lat)[28], 1), http_overhead_ms=round(S.median(lat) - S.median([call("POST", "/jobs?wait=1", {"op": "ping"})["run_ms"] for _ in range(1)]) , 1))
stop(p)
print("spawn", res["spawn_ms"], "ms | 상주", res["resident"])

# 2. 작업자 수별 처리량
res["scaling"] = {}
for n in (1, 2, 4, 8, 16, 20):
    p = start(n); cold = ready(n)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(64) as ex:
        outs = list(ex.map(lambda _: call("POST", "/jobs?wait=1", {"op": "sweep", "args": SW}), range(200)))
    dt = time.perf_counter() - t0
    qm = sorted(o["queue_ms"] for o in outs)
    res["scaling"][n] = dict(jobs_per_s=round(200 / dt, 1), q_p50_ms=round(qm[100]), q_p95_ms=round(qm[190]), run_p50_ms=round(S.median(o["run_ms"] for o in outs), 1), startup_s=round(cold, 1))
    print("workers", n, res["scaling"][n]); stop(p)

# 3. 모드
res["modes"] = {}
for mode in ("cap80", "unlimited"):
    p = start(0, mode); h = call("GET", "/healthz"); cold = ready(h["workers"])
    t0 = time.perf_counter()
    with ThreadPoolExecutor(64) as ex:
        outs = list(ex.map(lambda _: call("POST", "/jobs?wait=1", {"op": "sweep", "args": SW}), range(300)))
    dt = time.perf_counter() - t0
    res["modes"][mode] = dict(workers=h["workers"], jobs_per_s=round(300 / dt, 1), run_p50_ms=round(S.median(o["run_ms"] for o in outs), 1), startup_s=round(cold, 1))
    if mode == "cap80":
        t0 = time.perf_counter(); call("POST", "/mode", {"mode": "unlimited"}); ready(call("GET", "/healthz")["workers"]); res["modes"]["switch_cap80_to_unlimited_s"] = round(time.perf_counter() - t0, 1); print("모드 전환", res["modes"]["switch_cap80_to_unlimited_s"], "초")
    print(mode, res["modes"][mode]); stop(p)

# 4. 혼합 부하: 무거운 sweep 8개 + 가벼운 replay 100개
p = start(4); ready(4)
grid = {"grid": [{"npp": {"rel_db": -9 + 0.2 * i, "bursts": 2.1}} for i in range(400)]}
t0 = time.perf_counter()
heavy = [call("POST", "/jobs", {"op": "sweep", "args": grid})["id"] for _ in range(8)]
with ThreadPoolExecutor(16) as ex:
    light = list(ex.map(lambda _: call("POST", "/jobs?wait=1", {"op": "replay", "args": {"registry": False}}), range(100)))
tl = time.perf_counter() - t0
while any(call("GET", f"/jobs/{i}")["status"] not in ("done", "error") for i in heavy):
    time.sleep(0.2)
th = time.perf_counter() - t0
ql = sorted(o["queue_ms"] for o in light)
res["mixed"] = dict(workers=4, light_done_s=round(tl, 1), all_done_s=round(th, 1), light_q_p50_ms=round(ql[50]), light_q_p95_ms=round(ql[95]), heavy_run_s=round(S.median(call("GET", f"/jobs/{i}")["run_ms"] for i in heavy) / 1000, 1))
print("mixed", res["mixed"]); stop(p)
json.dump(res, open(PH / "bench_svc.json", "w"), indent=1)
