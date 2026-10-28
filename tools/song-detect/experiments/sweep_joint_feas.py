"""경계 상수 전체를 동시에 +-span 교란했을 때 golden 이탈 0 을 유지하는 비율(span 별 무작위 N회). 단독 절벽이 2~10% 인 상수가 수십 개라 동시 이동은 거의 항상 이탈한다 = 현재 조합의 안정 영역이 좁다.
  python experiments/sweep_joint_feas.py [--n 60] -> cache/proto_sweep/joint_feas.json"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import sweep_core as S
from sweep_oat import KEYS, INT
from sweep_bsearch import DEAD

ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=60); ap.add_argument("--base", default="{}", help="기준 설정 JSON(예: 재중심화 설정)"); ap.add_argument("--out", default="cache/proto_sweep/joint_feas.json"); ap.add_argument("--spans", default="0.01,0.02,0.04,0.06,0.10"); a = ap.parse_args()
if __name__ == "__main__":
    import tune
    cur = tune.listing(); base = json.loads(a.base); cur.update(base)
    keys = [k for k in KEYS if k not in DEAD and k not in INT]
    ev = S.Evaluator(6, wide=True)
    ev.evaluate(base)
    rng = np.random.default_rng(0)
    out = {}
    for span in [float(x) for x in a.spans.split(",")]:
        ok = h = 0; devs = []
        for _ in range(a.n):
            cfg = {k: cur[k] * (1 + rng.uniform(-span, span)) for k in keys}
            r = ev.evaluate(cfg)  # cfg 는 base 값을 중심으로 교란
            ok += r["gold_dev"] == 0; devs.append(r["gold_dev"]); h += r["gold_dev"] == 0 and r["hit3"] >= 9 and r["dir_pass"] >= 13 and r["ok_pass"] == 67
        out[span] = dict(feasible=ok / a.n, gate_all=h / a.n, gold_dev_median=float(np.median(devs)), n=a.n)
        print(f"span {span:.0%}: golden 이탈 0 {ok}/{a.n}, 모든 게이트 무회귀 {h}/{a.n}, 이탈 중앙 {np.median(devs):.0f}", flush=True)
    json.dump(out, open(a.out, "w"))
    ev.close()
