"""통합 단계 점검: 두 3_final.json 모음(방송별 <루트>/<slug>/3_final.json)에서 후보 경계(start/end)와 그 밖의 필드가 달라진 구간 수를 센다.
  python experiments/integ_final_diff.py <기준 루트> [<비교 루트=cache/harness/out_m>]
기준 루트는 단계 시작 전에 cache/harness/out_m 의 3_final.json 을 복사해 둔 것(cache/proto_integrate/final_base 등). 종료코드 1 = start/end 가 1e-6초 넘게 다른 구간이 있음.
alt_start 처럼 새로 생긴 키는 경계 변화로 세지 않고 따로 센다. shortcut: 후보 짝은 같은 방송의 같은 순번(2_refine 순서가 안 바뀌는 경우만 유효)."""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
a_root = Path(sys.argv[1]); b_root = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "cache/harness/out_m"
moved, other, newkey, n = [], 0, 0, 0
for f in sorted(a_root.glob("*/3_final.json")):
    A = json.load(open(f, encoding="utf8")); B = json.load(open(b_root / f.parent.name / "3_final.json", encoding="utf8"))
    assert len(A) == len(B), (f.parent.name, len(A), len(B))
    for i, (x, y) in enumerate(zip(A, B)):
        n += 1
        if abs(x["start"] - y["start"]) > 1e-6 or abs(x["end"] - y["end"]) > 1e-6:
            moved.append((f.parent.name, i, round(x["start"], 1), round(x["end"], 1), round(y["start"] - x["start"], 2), round(y["end"] - x["end"], 2), bool(x.get("keep"))))
        elif {k: v for k, v in x.items() if k in y} != {k: v for k, v in y.items() if k in x}:
            other += 1
        if set(y) - set(x):
            newkey += 1
print(f"구간 {n}개: 경계(start/end) 변화 {len(moved)} (keep {sum(m[-1] for m in moved)}), 경계 외 필드 변화 {other}, 새 키가 생긴 구간 {newkey}")
for m in moved[:20]:
    print("  ", m)
sys.exit(1 if moved else 0)
