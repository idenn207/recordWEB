"""python run_probe.py <별칭> <모드> <by group|streamer> : 프로브 변형 일괄 (E07~E11 계열). 결과 JSON 은 cache/proto_visual/res_probe_<별칭>_<모드>_<by>.json"""
import json, sys, warnings
warnings.filterwarnings("ignore")
from evlib import *
import probes as P
alias, mode, by = sys.argv[1], sys.argv[2], sys.argv[3]
df, E = dataset(alias, mode)
y = (df.live == 0).astype(int).to_numpy(); g = df[by].to_numpy()
out = {}
cfg = [("LR song mean C=1", P.lr_song(E, y, g, 1.0)), ("LR song mean C=0.1", P.lr_song(E, y, g, 0.1)), ("LR song mean C=10", P.lr_song(E, y, g, 10.0)),
       ("LR song meanstd C=1", P.lr_song(E, y, g, 1.0, "meanstd")), ("LR frame mean C=1", P.lr_frame(E, y, g, 1.0, "mean")), ("LR frame max C=1", P.lr_frame(E, y, g, 1.0, "max")),
       ("LR frame p75 C=1", P.lr_frame(E, y, g, 1.0, "p75")), ("kNN k=5", P.knn(E, y, g, 5)), ("kNN k=1", P.knn(E, y, g, 1))]
for name, fn in cfg:
    r = veto(df, fn, by, ms=(0.0, 0.1, 0.2))
    out[name] = {k: v for k, v in r.items() if k != "oof" and not str(k).startswith("hit")}
    print(line(f"{alias}/{mode}/{by} {name}", r), "|", line("", r, 0.2)[-62:], flush=True)
json.dump(out, open(PV / f"res_probe_{alias}_{mode}_{by}.json", "w", encoding="utf8"), ensure_ascii=False, indent=1, default=str)
