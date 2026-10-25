"""호스트용 분석기 클라이언트 (표준 라이브러리만). 상주 컨테이너 song-analyzer(analyzer_server.py)를 쓴다.
  ensure_up()  컨테이너가 안 떠 있으면 docker compose 로 한 번만 시작, 이미 떠 있으면 재사용, /health 가 200 일 때까지 대기
  detect(wav, out, **params) / refine(wav, seg_in, seg_out, **params)  호스트 경로를 /work/... 로 바꿔 요청하고 끝날 때까지 기다린다(진행 로그를 stderr 로)
  status()  /health,  jobs()  /jobs
환경변수: SONG_ANALYZER_PORT(8765) SONG_ANALYZER_NAME(song-analyzer) SONG_PROFILE(gpu|cpu, 기본: nvidia-smi 가 있으면 gpu)
서비스를 못 쓰면 Unavailable 을 던진다 - 호출자(pipeline.py)가 docker run 으로 폴백한다. 서버가 작업 도중 죽으면 ensure_up 으로 되살려 1회 다시 요청한다(detect 중간 결과는 cache/detect 에 남아 이어 한다).
shortcut: 프로젝트 폴더(ROOT) 밖의 파일은 컨테이너에 마운트돼 있지 않아 Unavailable(폴백)."""
import json, os, shutil, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = int(os.environ.get("SONG_ANALYZER_PORT", 8765))
NAME = os.environ.get("SONG_ANALYZER_NAME", "song-analyzer")
BASE = f"http://127.0.0.1:{PORT}"


class Unavailable(RuntimeError):
    pass


class JobError(RuntimeError):
    pass


def cpath(p):
    try:
        return "/work/" + Path(p).resolve().relative_to(ROOT).as_posix()
    except ValueError:
        raise Unavailable(f"프로젝트 폴더 밖 경로는 컨테이너에 없다: {p}")


def _req(path, obj=None, timeout=10):
    r = urllib.request.Request(BASE + path, json.dumps(obj).encode() if obj is not None else None, {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as f:
            return json.load(f)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf8", "replace")
        if e.code == 503:
            raise Unavailable("모델 로딩 중")
        raise JobError(f"HTTP {e.code} {body[:300]}")
    except (urllib.error.URLError, OSError, ValueError) as e:       # 연결 거부/끊김/시간 초과
        raise Unavailable(str(e))


def status():
    return _req("/health")


def jobs():
    return _req("/jobs")


def ensure_up(wait=300):
    try:
        return status()
    except Unavailable:
        pass
    profile = os.environ.get("SONG_PROFILE") or ("gpu" if shutil.which("nvidia-smi") else "cpu")
    sys.path.insert(0, str(ROOT))
    import limits
    env = {**os.environ, "SONG_CPU_LIMIT": os.environ.get("SONG_CPU_LIMIT") or str(limits.cpu_cores()), "SONG_PORT": str(PORT), "SONG_ANALYZER_NAME": NAME}
    try:      # 컨테이너가 이미 있으면(정지 상태 포함) 그대로 재사용: up -d 는 있는 것을 다시 만들지 않는다
        subprocess.run(["docker", "compose", "-p", NAME, "-f", str(ROOT / "docker-compose.analyzer.yml"), "--profile", profile, "up", "-d"], env=env, check=True, capture_output=True, text=True, timeout=120)
    except (subprocess.SubprocessError, OSError) as e:
        raise Unavailable(f"docker compose up 실패: {getattr(e, 'stderr', e)}")
    t = time.time()
    while time.time() - t < wait:
        try:
            return status()
        except Unavailable:
            time.sleep(2)
    raise Unavailable("health 대기 시간 초과")


def _run(kind, args, poll=2.0):
    for attempt in (0, 1):
        try:
            ensure_up()
            jid = _req("/" + kind, args)["job"]
            last = 0
            while True:
                j = _req(f"/jobs/{jid}", timeout=30)
                for line in j["log"][last:]:
                    print("  [analyzer]", line, file=sys.stderr, flush=True)
                last = len(j["log"])
                if j["status"] == "done":
                    return j
                if j["status"] == "error":
                    raise JobError(j["error"])
                time.sleep(poll)
        except Unavailable:
            if attempt:
                raise
            time.sleep(5)                                         # restart: unless-stopped 가 되살릴 시간, 그래도 없으면 ensure_up 이 시작


def detect(wav, out, **params):
    return _run("detect", dict(wav=cpath(wav), out=cpath(out), params=params))["result"]


def refine(wav, seg_in, seg_out, **params):
    return _run("refine", dict(wav=cpath(wav), **{"in": cpath(seg_in)}, out=cpath(seg_out), params=params))["result"]


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["selftest"]:
        assert cpath(ROOT / "data" / "x.wav") == "/work/data/x.wav"
        try:
            cpath("/nonexistent/x.wav")
            assert 0
        except Unavailable:
            pass
        print("selftest ok")
    elif a[:1] == ["up"]:
        print(ensure_up())
    else:
        print(json.dumps(status(), ensure_ascii=False), json.dumps(jobs()[-5:], ensure_ascii=False))
