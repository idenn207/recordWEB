"""제로샷 (E01~E06): python run_zs.py <별칭> [모드] -- 프롬프트 세트 x 집계(mean/max/med/min)"""
import json, sys, warnings
warnings.filterwarnings("ignore")
import torch
from evlib import *
import probes as P, prompts
from embed import load, MODELS
alias, mode = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "squash"
df, E = dataset(alias, mode)
m, _, tok = load(alias)
def tx(ts):
    with torch.no_grad():
        return torch.nn.functional.normalize(m.encode_text(tok(ts).cuda()).float(), dim=-1).cpu().numpy()
out = {}
for sn, st in prompts.SETS.items():
    Tn, Tl = tx(st["N"]), tx(st["L"])
    for agg in ("mean", "max", "med"):
        r = veto(df, P.zeroshot(E, Tn, Tl, agg), "streamer", ms=(0.0, 0.1))
        out[f"{sn}/{agg}"] = {k: v for k, v in r.items() if k != "oof" and not str(k).startswith("hit")}
        print(line(f"{alias} {sn}/{agg}", r), flush=True)
json.dump(out, open(PV / f"res_zs_{alias}_{mode}.json", "w", encoding="utf8"), ensure_ascii=False, indent=1, default=str)
