"""작업대: 두 lab 결과(lab_<이름>.json)의 항목별 오차/통과 차이. python experiments/bl_diff.py <이름> [기준=base]"""
import json, sys
from pathlib import Path
O = Path(__file__).resolve().parent.parent / "cache/proto_boundary"
a = json.load(open(O / f"lab_{sys.argv[2] if len(sys.argv) > 2 else 'base'}.json", encoding="utf8"))
b = json.load(open(O / f"lab_{sys.argv[1]}.json", encoding="utf8"))
for k in sorted(b["items"], key=lambda x: (int(''.join(c for c in x.split(':')[0] if c.isdigit())), x)):
    x, y = a["items"].get(k), b["items"][k]
    if x != y:
        print(f"{k:12s} {x} -> {y}")
print("golden:", b.get("golden_improved"), [g[:2] for g in b["golden"]][:12])
