"""리소스 상한을 한 곳에서 정의한다. 사용자가 같은 PC 로 다른 작업을 하므로 CPU, GPU(사용률/VRAM), 네트워크는 항상 최대치의 LIMIT_PCT(80%)를 넘지 않는다.
환경변수: SONG_LIMIT_PCT(80), SONG_INTERNET_MBPS(500, 회선 Mbps), SONG_LAN_MBPS(1000, NAS LAN Mbps).
쓰는 곳: 서비스(torch 스레드, GPU 가동률/VRAM), docker compose cpus(`python limits.py cpus`), fetch_vod.py(인터넷), nas_ingest.py/make_final.py(LAN, ffmpeg -readrate), ffmpeg -threads.
shortcut: GPU 가동률은 배치 사이 휴지(듀티)로 평균만 맞춘다(순간 100% 가능), 네트워크는 앱 수준 상한이라 다른 프로그램의 트래픽은 못 본다."""
import os, sys

LIMIT_PCT = float(os.environ.get("SONG_LIMIT_PCT", 80))
INTERNET_MBPS = float(os.environ.get("SONG_INTERNET_MBPS", 500))
LAN_MBPS = float(os.environ.get("SONG_LAN_MBPS", 1000))


def frac():
    return min(1.0, LIMIT_PCT / 100)


def cpu_cores():
    """논리 코어의 LIMIT_PCT (최소 1)."""
    return max(1, int((os.cpu_count() or 1) * frac()))


def net_MBps(kind="internet"):
    """상한 MB/s: 회선 500Mbps -> 50, LAN 1Gbps -> 100."""
    return (INTERNET_MBPS if kind == "internet" else LAN_MBPS) * frac() / 8


if __name__ == "__main__":
    k = sys.argv[1] if len(sys.argv) > 1 else ""
    if k == "cpus":
        print(cpu_cores())
    elif k == "selftest":
        assert net_MBps("internet") == 50 and net_MBps("lan") == 100 and 1 <= cpu_cores() <= (os.cpu_count() or 1)
        print("selftest ok")
    else:
        print(f"limit={LIMIT_PCT}% cpus={cpu_cores()}/{os.cpu_count()} internet={net_MBps():.0f}MB/s lan={net_MBps('lan'):.0f}MB/s")
