"""작업대: lab_<이름>.json 들을 기준선 대비 표로. python experiments/bl_table.py 이름1 이름2 ... (접두 일치: 's3_*' 처럼 * 사용)"""
import json, sys, glob
from pathlib import Path
O = Path(__file__).resolve().parent.parent / "cache/proto_boundary"
def load(n): return json.load(open(O / f"lab_{n}.json", encoding="utf8"))
b = load("base")["memo"]
names = []
for a in sys.argv[1:]:
    names += sorted(Path(p).stem[4:] for p in glob.glob(str(O / f"lab_{a}.json")))
print("| 설정 | hit@0.5/3/10 | 중앙 | 방향 | ok | 길이>5 | golden 이탈(진짜/정답쪽) |")
print("|---|---|---|---|---|---|---|")
print(f"| base | {b['hit@0.5']}/{b['hit@3']}/{b['hit@10']} | {b['median_abs_err']} | {b['dir_pass']}/{b['dir_n']} | {b['ok_pass']}/{b['ok_n']} | {b['len_err_gt5']} | 0 |")
for n in names:
    r = load(n); m = r["memo"]
    print(f"| {n} | {m['hit@0.5']}/{m['hit@3']}/{m['hit@10']} | {m['median_abs_err']} | {m['dir_pass']}/{m['dir_n']} | {m['ok_pass']}/{m['ok_n']} | {m['len_err_gt5']} | {r['golden_dev']}({r.get('golden_real','?')}/{len(r.get('golden_improved') or [])}) |")
