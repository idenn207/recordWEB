"""검토 결과(정답)와 data/<날짜>.segments.json 을 비교한다. 사용: python evaluate.py [폴더=data]"""
import json, sys
from pathlib import Path

D = Path(sys.argv[1] if len(sys.argv) > 1 else "data")
hms = lambda t: f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}"
H = lambda h, m, s: h * 3600 + m * 60 + s
# 사용자가 확인한 라이브 곡 (날짜 -> [(시작, 끝)]). 10-18 데뷔는 3곡 모두 라이브라고만 확인되어 KEEP 3개를 정답으로 본다.
LIVE = {"2026-10-21": [(H(5, 53, 52), H(5, 56, 45))], "2026-10-23": [(H(5, 12, 25), H(5, 16, 48))],
        "2026-10-19": [(H(5, 25, 14), H(5, 28, 59))]}
tp = fp = miss = 0
for f in sorted(D.glob("20*.segments.json")):
    date = f.name[:10]
    keeps = [s for s in json.loads(f.read_text(encoding="utf8")) if s["keep"]]
    truth = LIVE.get(date, [])
    for s in keeps:
        hit = next((t for t in truth if min(s["end"], t[1]) - max(s["start"], t[0]) > 0.5 * (t[1] - t[0])), None)
        if date == "2026-10-18" or hit:
            tp += 1
            err = f" start{s['start'] - hit[0]:+.0f}s end{s['end'] - hit[1]:+.0f}s" if hit else ""
            print(f"  TP {date} {hms(s['start'])}-{hms(s['end'])}{err}")
        else:
            fp += 1
            print(f"  FP {date} {hms(s['start'])}-{hms(s['end'])} speech={s.get('speech')} music={s.get('music')}")
    for t in truth:
        if not any(min(s["end"], t[1]) - max(s["start"], t[0]) > 0.5 * (t[1] - t[0]) for s in keeps):
            miss += 1
            print(f"  MISS {date} {hms(t[0])}-{hms(t[1])}")
print(f"TP={tp} FP={fp} MISS={miss}")
