"""임시 GPU 사용률 제한기(상주 분석기 서비스에 내장 스로틀이 들어가기 전까지): song-detect 컨테이너를 주기적으로 일시정지해 평균 GPU 사용률을 LIMIT(기본 80%) 이하로 묶는다.
관리자 권한(nvidia-smi -pl)이 없어서 전력 제한을 못 쓰는 환경용. 일시정지(docker pause)는 컨테이너 프로세스를 얼려 작업 결과에는 영향이 없다.
사용: python gpu_governor.py [상한 %=80] [주기 초=4]    종료: Ctrl+C (일시정지된 컨테이너는 자동으로 풀고 끝낸다)
shortcut: 주기 안에서 0.2*주기를 일시정지하는 고정 듀티 + 사용률이 상한을 넘을 때만 동작(적응형 PID 아님)."""
import subprocess, sys, time

LIMIT = float(sys.argv[1]) if len(sys.argv) > 1 else 80.0
CYCLE = float(sys.argv[2]) if len(sys.argv) > 2 else 4.0
sh = lambda *a: subprocess.run(a, capture_output=True, text=True).stdout.split()
util = lambda: float(sh("nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits")[0])
names = lambda: sh("docker", "ps", "--filter", "ancestor=song-detect-gpu", "--filter", "status=running", "--format", "{{.Names}}")
paused = []
try:
    while True:
        n = names()
        if n and util() > LIMIT:                       # 상한을 넘을 때만 1주기에서 (1-LIMIT/100) 만큼 얼린다
            subprocess.run(["docker", "pause", *n], capture_output=True)
            paused = n
            time.sleep(CYCLE * (1 - LIMIT / 100) * 2)  # 평균 사용률이 확실히 내려가도록 2배
            subprocess.run(["docker", "unpause", *paused], capture_output=True)
            paused = []
        time.sleep(CYCLE * LIMIT / 100)
except KeyboardInterrupt:
    pass
finally:
    if paused:
        subprocess.run(["docker", "unpause", *paused], capture_output=True)
