"""상호작용이 큰 상수 쌍의 2D 격자(경계 평가): 각 축 기본값 +-30% 를 7점. 지표 gold_dev / hit3 / dir_pass / moved2 의 지도를 PNG 로.
  python experiments/sweep_grid2.py [--workers 8]   -> cache/proto_sweep/grid2.json, grid2_*.png"""
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import sweep_core as S

PAIRS = [("snap.LOW", "snap.RUN"), ("snap.E1B_LOUD", "snap.E1B_DROP"), ("snap.B_DB", "snap.B_TAIL"), ("snap.deep_end.depth", "snap.deep_end.nxt_db"),
         ("snap.start_s1.gap", "snap.start_s1.vmax"), ("snap.start_s2.vmin", "snap.start_s2.spmax"), ("refine.refine.bias_start", "refine.refine.bias_end"), ("snap.E1_MU", "snap.E1_GAP")]
FACT = [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3]


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=8); a = ap.parse_args()
    import tune
    cur = tune.listing()
    ev = S.Evaluator(a.workers, wide=True)
    base = ev.evaluate({})
    res, t0 = {}, time.time()
    for ka, kb in PAIRS:
        va = [cur[ka] * f for f in FACT]; vb = [cur[kb] * f for f in FACT]
        if ka == "snap.RUN":
            va = [2, 3, 4]
        if kb == "snap.RUN":
            vb = [2, 3, 4]
        g = {m: np.zeros((len(va), len(vb))) for m in ("gold_dev", "hit3", "hit05", "dir_pass", "moved2", "ok_pass")}
        for i, x in enumerate(va):
            for j, y in enumerate(vb):
                r = ev.evaluate({ka: x, kb: y})
                for m in g:
                    g[m][i, j] = r[m]
        res[f"{ka}|{kb}"] = dict(a=ka, b=kb, va=[float(v) for v in va], vb=[float(v) for v in vb], default=[cur[ka], cur[kb]], **{m: g[m].tolist() for m in g})
        print(ka, kb, f"{time.time() - t0:.0f}s", "gold_dev=0 칸 수", int((g["gold_dev"] == 0).sum()), "/", g["gold_dev"].size, flush=True)
        json.dump(dict(base={k: v for k, v in base.items() if not k.startswith("_")}, grids=res), open("cache/proto_sweep/grid2.json", "w"), ensure_ascii=False)
    ev.close()
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Malgun Gothic"; plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(len(PAIRS), 3, figsize=(15, 4.2 * len(PAIRS)))
    for r, (k, g) in enumerate(res.items()):
        for c, (m, cm) in enumerate((("gold_dev", "Reds"), ("hit3", "Blues"), ("moved2", "Greys"))):
            a_ = ax[r, c]
            im = a_.imshow(np.array(g[m]).T, origin="lower", aspect="auto", cmap=cm)
            a_.set_xticks(range(len(g["va"]))); a_.set_xticklabels([f"{v:.3g}" for v in g["va"]], fontsize=7)
            a_.set_yticks(range(len(g["vb"]))); a_.set_yticklabels([f"{v:.3g}" for v in g["vb"]], fontsize=7)
            a_.set_xlabel(g["a"], fontsize=8); a_.set_ylabel(g["b"], fontsize=8); a_.set_title(m, fontsize=9)
            for i in range(len(g["va"])):
                for j in range(len(g["vb"])):
                    a_.text(i, j, f"{g[m][i][j]:.0f}", ha="center", va="center", fontsize=6)
            if g["default"][0] in g["va"] or True:
                pass
            plt.colorbar(im, ax=a_)
    plt.tight_layout(); plt.savefig("cache/proto_sweep/grid2.png", dpi=60)


if __name__ == "__main__":
    main()
