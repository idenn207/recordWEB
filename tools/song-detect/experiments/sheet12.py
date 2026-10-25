"""후보 구간의 144p 프레임 6장을 3x2 로 이어 붙인다(눈으로 화면 확인용). 사용: python experiments/sheet12.py <영상번호> <시작초> <끝초> [...반복]  -> cache/exp12_review/sheets/
shortcut: CDN 이 멈추면 해당 장을 검은 칸으로 둔다(타임아웃 20초)."""
import os, subprocess, sys
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); sys.path.insert(0, os.getcwd())
from vod import url144
os.makedirs("cache/exp12_review/sheets", exist_ok=True)
a = sys.argv[1:]
for vid, s, e in zip(a[0::3], a[1::3], a[2::3]):
    s, e, u, fs = float(s), float(e), url144(int(vid)), []
    for i in range(6):
        f = f"cache/exp12_review/sheets/_{vid}_{i}.png"
        t = s + (e - s) * (i + 0.5) / 6
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-rw_timeout", "20000000", "-ss", f"{t:.1f}", "-i", u, "-frames:v", "1", "-vf", "scale=256:144", f], timeout=60)
        fs.append(f)
    ok = [f for f in fs if os.path.exists(f)]
    out = f"cache/exp12_review/sheets/{vid}_{int(s)}.png"
    if ok:
        subprocess.run(["ffmpeg", "-v", "error", "-y"] + sum([["-i", f] for f in ok], []) + ["-filter_complex", f"xstack=inputs={len(ok)}:layout=" + "|".join(f"{(i%3)*256}_{(i//3)*144}" for i in range(len(ok))), out])
    for f in ok: os.remove(f)
    print(out, len(ok))
