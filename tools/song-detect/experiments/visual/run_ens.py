"""제로샷 앙상블 (E): 모델 x 프롬프트 세트 x 집계 점수를 z 정규화(라벨 안 씀) 후 평균/최대. 곡 점수 벡터는 cache/proto_visual/zs_scores.npz 로 저장해 이후 스태킹이 쓴다.
python run_ens.py [by]"""
import json, sys, warnings
warnings.filterwarnings("ignore")
import torch
from evlib import *
import prompts
from embed import load
by = sys.argv[1] if len(sys.argv) > 1 else "streamer"; MODE = sys.argv[2] if len(sys.argv) > 2 else "squash"
MS = ["b32", "l14", "sigb16", "sig2b16"]
SC, df0 = {}, None
for a in MS:
    df, E = dataset(a, MODE); df0 = df if df0 is None else df0
    m, _, tok = load(a)
    for sn, st in prompts.SETS.items():
        with torch.no_grad():
            tn, tl = [torch.nn.functional.normalize(m.encode_text(tok(t).cuda()).float(), dim=-1).cpu().numpy() for t in (st["N"], st["L"])]
        d = (E @ tn.T).max(2) - (E @ tl.T).max(2)
        for agg, f in (("max", d.max(1)), ("mean", d.mean(1))):
            SC[f"{a}|{sn}|{agg}"] = (f - f.mean()) / f.std()
    del m
np.savez(PV / ("zs_scores.npz" if MODE == "squash" else f"zs_scores_{MODE}.npz"), keys=df0.key.to_numpy(), **SC)
df = df0; y = (df.live == 0).to_numpy()
def ev(name, s, ms=(0.0, 0.1, 0.2)):
    r = veto(df, lambda tr, te: (s[tr], s[te]), by, ms=ms); print(line(name, r), "|", line("", r, 0.1)[-62:], flush=True); return {k: v for k, v in r.items() if k != "oof" and not str(k).startswith("hit")}
out = {}
pick = lambda keys: np.mean([SC[k] for k in keys], 0)
out["ens4 best-per-model max"] = ev("ens: b32 B_desc, l14 E_layout, sigb16 B_desc, sig2 A_basic (max)", pick(["b32|B_desc|max", "l14|E_layout|max", "sigb16|B_desc|max", "sig2b16|A_basic|max"]))
out["ens all sets max, 4 models"] = ev("ens: 전 세트 x 4모델 (max) 평균", pick([k for k in SC if k.endswith("|max")]))
out["ens all sets mean, 4 models"] = ev("ens: 전 세트 x 4모델 (mean) 평균", pick([k for k in SC if k.endswith("|mean")]))
out["ens l14+sig2 all sets max"] = ev("ens: l14+sig2 전 세트 max", pick([k for k in SC if k.endswith("|max") and k.split("|")[0] in ("l14", "sig2b16")]))
out["ens sig only"] = ev("ens: sigb16+sig2b16 전 세트 max", pick([k for k in SC if k.endswith("|max") and k.split("|")[0].startswith("sig")]))
out["ens A_basic 4 models"] = ev("ens: A_basic 4모델 max", pick([f"{a}|A_basic|max" for a in MS]))
out["ens B_desc 4 models"] = ev("ens: B_desc 4모델 max", pick([f"{a}|B_desc|max" for a in MS]))
out["ens max-of-z best4"] = ev("ens: 같은 4개의 max(z)", np.max([SC[k] for k in ["b32|B_desc|max", "l14|E_layout|max", "sigb16|B_desc|max", "sig2b16|A_basic|max"]], 0))
json.dump(out, open(PV / f"res_ens_{by}{'' if MODE == 'squash' else '_' + MODE}.json", "w", encoding="utf8"), ensure_ascii=False, indent=1, default=str)
