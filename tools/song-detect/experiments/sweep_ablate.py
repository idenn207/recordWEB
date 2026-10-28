"""규칙 끄기(ablation)와 끝 규칙 순서 변경 실험 (판정을 바꿔보는 실험). 규칙 = E1 E1b E2 E3 S1 S2 (blind9_bounds.patched), 순서 = E1,E1b,E3 의 6가지 중 원본 제외 5개.
  python experiments/sweep_ablate.py -> cache/proto_sweep/ablate.json"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sweep_core as S

CFGS = [("기준", {})] + [(f"{r} 끔", {"_off": [r]}) for r in ("E1", "E1b", "E2", "E3", "S1", "S2")] + [("끝 규칙 전부 끔(E1,E1b,E3)", {"_off": ["E1", "E1b", "E3"]}), ("시작 규칙 전부 끔(S1,S2)", {"_off": ["S1", "S2"]}),
        ("전부 끔(v3 snap)", {"_off": ["E1", "E1b", "E2", "E3", "S1", "S2"]})] + [(f"순서 {o}", {"_order": o}) for o in S.ORDERS]
if __name__ == "__main__":
    ev = S.Evaluator(8, wide=True)
    base = ev.evaluate({})
    out = []
    for name, c in CFGS:
        r = ev.evaluate(c)
        m = {k: v for k, v in r.items() if not k.startswith("_")}
        out.append(dict(name=name, cfg=c, **m))
        print(f"{name:28} golden {m['gold_dev']:3} {sorted({f[1] for f in m['gold_flags']})[:3]}  h@0.5/3/10 {m['hit05']}/{m['hit3']}/{m['hit10']}  방향 {m['dir_pass']}/{m['dir_n']}  좋음 {m['ok_pass']}/{m['ok_n']}  길이>5초 {m['len_gt5']}  moved2 {m.get('moved2')}", flush=True)
    json.dump(out, open("cache/proto_sweep/ablate.json", "w"), ensure_ascii=False)
    ev.close()
