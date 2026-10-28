"""앙상블 절제 (E): 프롬프트 세트별 / 프레임 수 / 시간 집계 / 모델 수 / 스트리머별 이질성. python run_ablate.py [by=streamer] [mode=squash]"""
import sys, json, warnings
warnings.filterwarnings("ignore")
import torch
from evlib import *
import prompts
from embed import load
by = sys.argv[1] if len(sys.argv) > 1 else "streamer"; MODE = sys.argv[2] if len(sys.argv) > 2 else "squash"
MS = ["b32", "l14", "sigb16", "sig2b16"]; D = {}
for a in MS:
    df, E = dataset(a, MODE); m, _, tok = load(a)
    for sn, st in prompts.SETS.items():
        with torch.no_grad():
            tn, tl = [torch.nn.functional.normalize(m.encode_text(tok(t).cuda()).float(), dim=-1).cpu().numpy() for t in (st["N"], st["L"])]
        D[(a, sn)] = (E @ tn.T).max(2) - (E @ tl.T).max(2)        # (n, 8)
    del m
z = lambda f: (f - f.mean()) / f.std()
def ens(models=MS, sets=None, frames=slice(None), agg="max"):
    sets = sets or list(prompts.SETS)
    f = {"max": lambda d: d.max(1), "mean": lambda d: d.mean(1), "top2": lambda d: np.sort(d, 1)[:, -2:].mean(1), "p75": lambda d: np.percentile(d, 75, 1), "med": lambda d: np.median(d, 1)}[agg]
    return np.mean([z(f(D[(a, s)][:, frames])) for a in models for s in sets], 0)
def ev(name, s):
    r = veto(df, lambda tr, te: (s[tr], s[te]), by, ms=(0.0, 0.1)); print(line(name, r), "|", line("", r, 0.1)[-60:], flush=True); return r
out = {}
for s in prompts.SETS:
    out[f"set {s}"] = ev(f"세트 {s}만(4모델 max)", ens(sets=[s]))
for k, fr in (("2장(0,4)", [0, 4]), ("4장(0,2,5,7)", [0, 2, 5, 7]), ("4장(1,3,5,7)", [1, 3, 5, 7]), ("8장", slice(None)), ("1장(3)", [3])):
    out[f"frames {k}"] = ev(f"프레임 {k} (4모델 전세트 max)", ens(frames=fr))
for agg in ("max", "top2", "p75", "mean", "med"):
    out[f"agg {agg}"] = ev(f"집계 {agg} (4모델 전세트)", ens(agg=agg))
for ms in (["b32"], ["l14"], ["sigb16"], ["sig2b16"], ["l14", "sig2b16"], ["b32", "sigb16"], ["l14", "sigb16", "sig2b16"]):
    out["models " + "+".join(ms)] = ev(f"모델 {'+'.join(ms)} (전세트 max)", ens(models=ms))
s = ens()
r = veto(df, lambda tr, te: (s[tr], s[te]), by, ms=(0.1,)); h = r["hit0.1"]; y = (df.live == 0).to_numpy()
print("== 스트리머별 (4모델 전세트 max, m=0.1)")
for st in sorted(df.streamer.unique()):
    mk = (df.streamer == st).to_numpy()
    print(f"  {st:10} N {int((y&mk).sum()):2} 거름 {int((h&y&mk).sum()):2} | 라이브 {int((~y&mk).sum()):2} 손실 {int((h&~y&mk).sum())}")
json.dump({k: {kk: vv for kk, vv in v.items() if kk not in ("oof",) and not str(kk).startswith("hit")} for k, v in out.items()}, open(PV / f"res_ablate_{by}_{MODE}.json", "w", encoding="utf8"), ensure_ascii=False, indent=1, default=str)
