"""X: 기존 E1b(끝 연장) 상수 격자 - 끝 이른 곡(#22 #63 #65 #71 #82 #142 #54e)을 푸는 설정이 있는지. snap 상수를 잠깐 바꿔 lab 지표를 잰다(코드는 안 바뀜)."""
import sys; sys.path.insert(0, 'experiments')
from bound_lab import *
grid = {"E1B_VOC": (0.0, 0.2, 0.3, 0.7), "E1B_GAP": (3.0, 8.0, 12.0), "E1B_DROP": (10.0, 20.0, 25.0), "E1B_LOUD": (8.0, 16.0, 20.0), "E1B_GUARD": (-3.0, 0.0, 3.0), "E1B_MU": (0.3, 0.7)}
for k, vals in grid.items():
    orig = getattr(snap, k)
    for v in vals:
        setattr(snap, k, v)
        VAR[0] = f"{k}={v}"
        try:
            r, line = run(f"e1b_{k}={v}", None)
        finally:
            setattr(snap, k, orig); VAR[0] = ""
        with open(LOG, "a", encoding="utf8") as f:
            f.write(json.dumps(dict(name=r["name"], memo=r["memo"], golden_dev=r["golden_dev"], golden_real=r["golden_real"], golden_improved=r["golden_improved"]), ensure_ascii=False) + chr(10))
