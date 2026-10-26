"""리뷰 판정(B) 끝 경계 진단: 곡 끝(song_end) 주변 에너지(곡 중앙값 대비 dB)와 YAMNet Singing/Speech/Music 을 2초 간격으로 찍는다. 사용: python experiments/ends_diag.py <labels 번호...>"""
import sys, json, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
from snap import pcm_of, rms_db, HOP
from paths import cache_of
O = json.load(open("data/review/blind9/labels.json"))
for n in map(int, sys.argv[1:]):
    x = O[n - 1]
    wav = f"data/vod/nas/{re.sub(r'^\d+_[^_]+_', '', x['slug'])}.wav"
    pcm, a = pcm_of(wav), np.load(cache_of(wav, ".scores.npy"))
    s, e = x["ss"], x["se"]
    ref = float(np.median(rms_db(pcm, s, e)[1]))
    print(f"#{n} {x['file'][:34]} len={e-s:.0f} {x['lab']} {x['memo'][:40]}")
    row = []
    for d in range(int(__import__("os").environ.get("D0","-8")), int(__import__("os").environ.get("D1","34")), int(__import__("os").environ.get("DS","2"))):
        t = e + d
        db = float(np.median(rms_db(pcm, t, t + 1.0)[1])) - ref
        i = min(int(t / HOP), len(a) - 1)
        row.append(f"{d:+d}:{db:+.0f}/{a[i,0]:.1f}/{a[i,1]:.1f}/{a[i,2]:.1f}")
    print("  (상대초:dB/Sing/Speech/Music) " + " ".join(row))
