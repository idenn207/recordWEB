"""머리카락 방아쇠 상수: 각 상수를 기본값에서 +-0.5%, +-1% 만 움직여도 golden 이탈이 생기는지. (joint 교란에서 +-1% 만으로 이탈 중앙 10 이 나온 원인 분해)
  python experiments/sweep_hair.py -> cache/proto_sweep/hair.json"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sweep_core as S
from sweep_oat import KEYS, INT
if __name__ == "__main__":
    import tune
    cur = tune.listing()
    ev = S.Evaluator(8, wide=True)
    ev.evaluate({})
    out = {}
    for k in KEYS:
        if k in INT:
            continue
        d = cur[k]
        row = {}
        for f in (-0.01, -0.005, 0.005, 0.01):
            r = ev.evaluate({k: d * (1 + f)})
            row[f] = (r["gold_dev"], r.get("moved2"), r["hit3"], r["dir_pass"])
        out[k] = row
        bad = [f for f, v in row.items() if v[0]]
        print(f"{k:28} " + " ".join(f"{f:+.1%}:G{v[0]}/m{v[1]}" for f, v in row.items()) + ("  <== 방아쇠" if bad else ""), flush=True)
    json.dump({k: {str(f): v for f, v in r.items()} for k, r in out.items()}, open("cache/proto_sweep/hair.json", "w"))
    ev.close()
