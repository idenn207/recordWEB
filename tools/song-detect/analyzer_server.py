"""상주 분석기 서비스: 컨테이너 안에서 계속 돌며 YAMNet/Demucs 를 한 번만 올려 두고 작업을 받는다 (방송마다 docker run 으로 모델을 다시 올리는 낭비를 없앤다).
API (JSON, 포트 8765): POST /detect {wav, params:{vocal_thr:0.2,..}, out, force, device}  POST /refine {wav, in, out, params}  -> {job}
                       GET /health   GET /jobs (목록)   GET /jobs/<id> (상태, 진행 로그, 오류)
경로는 컨테이너 기준(/work/...): 프로젝트 폴더 전체를 /work 로 마운트하고, 호스트 경로 변환은 analyzer_client.py 가 한다.
작업은 직렬 큐: GPU 는 동시에 1개, CPU 는 SONG_JOBS(기본 1)개. 결과는 CLI(detect.py/refine.py)와 같고 cache/detect 캐시도 같이 쓴다.
리소스: limits.py 의 80% 상한 - GPU 가동률(SONG_GPU_LIMIT)과 VRAM(SONG_GPU_MEM) 기본값, CPU torch 스레드는 코어의 80%(SONG_THREADS 로 덮어씀).
shortcut: 인증 없음(127.0.0.1 바인딩 전제), 작업 기록은 메모리에만 있어 재시작하면 사라진다(결과 파일과 cache/detect 는 남아 재요청이 빠르다), 취소 없음.
자가 테스트: python analyzer_server.py selftest"""
import json, os, queue, sys, threading, time, traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import limits

jobs, order, Q, T0 = {}, [], queue.Queue(), time.time()
tl = threading.local()
STATE = dict(ready=False, device=None, load_s=None)


class Tee:
    """작업 스레드의 stderr(진행 출력)를 그 작업의 로그로 모은다."""
    def __init__(self, real):
        self.real = real

    def write(self, s):
        j = getattr(tl, "job", None)
        if j and s.strip():
            j["log"].append(s.rstrip())
            del j["log"][:-200]
        return self.real.write(s)

    def flush(self):
        self.real.flush()

    def __getattr__(self, k):
        return getattr(self.real, k)


def load_models():
    """시작 시 한 번: YAMNet(torch 는 가중치 변환, tflite 는 인터프리터)과 Demucs 를 올린다."""
    t = time.time()
    os.environ.setdefault("SONG_GPU_LIMIT", str(limits.frac()))
    os.environ.setdefault("SONG_GPU_MEM", str(limits.frac()))
    os.environ.setdefault("SONG_THREADS", str(max(1, limits.cpu_cores() // int(os.environ.get("SONG_JOBS", 1)))))
    import numpy as np, torch
    import detect, yamnet_backend as Y
    from demucs.pretrained import get_model
    dev = Y.resolve()
    torch.set_num_threads(int(os.environ["SONG_THREADS"]))
    if dev == "cuda":
        Y.gpu_init()
        Y._model(dev)
    else:
        Y.scores_windows(np.zeros(detect.WIN * 2, np.int16), [0], "cpu")        # tflite 인터프리터 예열
    detect._model = get_model("htdemucs").eval()                                  # vocal_ratio 가 이 전역을 재사용한다
    if dev == "cuda":
        detect._model.to(dev)
    STATE.update(ready=True, device=dev, load_s=round(time.time() - t, 1))


def do_detect(a):
    import detect
    wav = Path(a["wav"])
    p = {**detect.P, **{k: float(v) for k, v in (a.get("params") or {}).items()}}
    segs = detect.detect(wav, bool(a.get("force")), p, a.get("device"), in_process=True)
    out = Path(a["out"]) if a.get("out") else detect.cache_of(wav, ".segments.json")
    out.write_text(json.dumps(segs, ensure_ascii=False, indent=1))
    return dict(out=str(out), n=len(segs), keep=sum(s["keep"] for s in segs))


def do_refine(a):
    import refine
    refine.refine_file(a["wav"], a["in"], a["out"], **(a.get("params") or {}))
    return dict(out=a["out"])


KINDS = {"detect": do_detect, "refine": do_refine}


def worker():
    while True:
        j = Q.get()
        j.update(status="running", started=time.time())
        tl.job = j
        try:
            j["result"] = KINDS[j["kind"]](j["args"])
            j["status"] = "done"
        except Exception as e:
            j.update(status="error", error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-800:])
        j["ended"] = time.time()
        tl.job = None


def submit(kind, args):
    need = ("wav",) if kind == "detect" else ("wav", "in", "out")
    for k in set(need) | {k for k in ("wav", "in", "out") if k in args}:
        if not str(args.get(k, "")).startswith("/work/"):
            raise ValueError(f"{k} 는 /work/ 아래 경로여야 한다: {args.get(k)}")
    j = dict(id=f"{len(order) + 1:04d}", kind=kind, args=args, status="queued", queued=time.time(), log=[])
    jobs[j["id"]] = j
    order.append(j["id"])
    Q.put(j)
    return j


def view(j, full=True):
    d = {k: v for k, v in j.items() if k not in ("args", "log", "trace") or full}
    d["queue_pos"] = sum(jobs[i]["status"] in ("queued", "running") and i < j["id"] for i in order) if j["status"] == "queued" else None      # 앞에 있는 작업 수(실행 중 포함)
    return d


class H(BaseHTTPRequestHandler):
    def reply(self, code, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/health":
            mem = {}
            if STATE["device"] == "cuda":
                import torch
                mem = dict(vram_peak_mib=torch.cuda.max_memory_reserved() >> 20, vram_cap_mib=int(torch.cuda.get_device_properties(0).total_memory * float(os.environ["SONG_GPU_MEM"])) >> 20)
            self.reply(200 if STATE["ready"] else 503, dict(STATE, **mem, uptime_s=round(time.time() - T0), queued=Q.qsize(), running=sum(j["status"] == "running" for j in jobs.values())))
        elif self.path == "/jobs":
            self.reply(200, [view(jobs[i], False) for i in order[-50:]])
        elif self.path.startswith("/jobs/") and self.path[6:] in jobs:
            self.reply(200, view(jobs[self.path[6:]]))
        else:
            self.reply(404, dict(error="not found"))

    def do_POST(self):
        kind = self.path.strip("/")
        if kind not in KINDS:
            return self.reply(404, dict(error="not found"))
        if not STATE["ready"]:
            return self.reply(503, dict(error="models loading"))
        try:
            j = submit(kind, json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}"))
        except (ValueError, KeyError) as e:
            return self.reply(400, dict(error=str(e)))
        self.reply(202, dict(job=j["id"], queue_pos=view(j)["queue_pos"]))

    def log_message(self, *a):
        pass


def serve(port=8765, host="0.0.0.0"):
    sys.stderr = Tee(sys.stderr)
    srv = ThreadingHTTPServer((host, port), H)              # 포트가 먼저 열려야 모델 로딩 중에도 /health 가 503 으로 답한다
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    load_models()
    n = 1 if STATE["device"] == "cuda" else int(os.environ.get("SONG_JOBS", 1))      # GPU 는 동시에 1개
    for _ in range(n):
        threading.Thread(target=worker, daemon=True).start()
    print(f"analyzer ready device={STATE['device']} workers={n} load={STATE['load_s']}s port={port}", file=sys.stderr, flush=True)
    threading.Event().wait()


def selftest():
    """모델 없이 큐/검증/HTTP 만 확인 (직렬 실행, 대기 순번, 경로 검사)."""
    import urllib.request
    done = []
    KINDS["detect"] = lambda a: (time.sleep(0.3), done.append(a["wav"]))[0] or dict(ok=1)
    STATE["ready"] = True
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    post = lambda p, o: json.load(urllib.request.urlopen(urllib.request.Request(base + p, json.dumps(o).encode(), {"Content-Type": "application/json"})))
    a, b = post("/detect", dict(wav="/work/a.wav", out="/work/o")), post("/detect", dict(wav="/work/b.wav", out="/work/o"))
    assert b["queue_pos"] is not None and b["queue_pos"] >= 0
    try:
        post("/detect", dict(wav="/etc/x", out="/work/o"))
        assert 0
    except urllib.error.HTTPError as e:
        assert e.code == 400
    while json.load(urllib.request.urlopen(f"{base}/jobs/{b['job']}"))["status"] != "done":
        time.sleep(0.1)
    assert done == ["/work/a.wav", "/work/b.wav"] and jobs[a["job"]]["ended"] <= jobs[b["job"]]["started"]       # 두 번째는 첫 번째가 끝난 뒤 시작
    print("selftest ok")


if __name__ == "__main__":
    selftest() if sys.argv[1:] == ["selftest"] else serve(int(os.environ.get("SONG_PORT", 8765)))
