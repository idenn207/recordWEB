"""visual 트랙 2단계: manifest 의 곡마다 구간을 8등분한 중앙 시각의 프레임 8장을 398x224 jpg 로 cache/proto_visual/frames/<key>/<i>.jpg 에 저장(이미 있으면 건너뜀).
NAS URL 은 nas_auth 세션 쿠키로 읽고 401 이면 중단(로그인 시도 안 함). 사용: python experiments/visual/grab_frames.py [N=8]"""
import json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
import nas_auth

N = int(sys.argv[1]) if len(sys.argv) > 1 else 8
FR = Path("cache/proto_visual/frames")


def one(r):
    d = FR / r["key"].replace("/", "__")
    d.mkdir(parents=True, exist_ok=True)
    fails = 0
    for i in range(N):
        o = d / f"{i}.jpg"
        if o.exists():
            continue
        t = r["t0"] + (r["t1"] - r["t0"]) * (i + 0.5) / N
        cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", *nas_auth.ffargs(r["src"]), "-i", r["src"], "-frames:v", "1", "-vf", "scale=398:224", "-q:v", "3", str(o)]
        try:
            subprocess.run(cmd, check=True, timeout=120, creationflags=0x4000 if os.name == "nt" else 0, capture_output=True)
        except Exception as e:
            fails += 1
            if "401" in str(getattr(e, "stderr", b""))[:400]:
                print("401: 세션 만료, 중단", flush=True); os._exit(2)
    n = len(list(d.glob("*.jpg")))
    print(r["key"], n, flush=True)
    return n


if __name__ == "__main__":
    rows = json.load(open("cache/proto_visual/manifest.json", encoding="utf8"))
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(one, rows))
    print("완료", sum(res), "장", sum(n < N for n in res), "곡 부족")
