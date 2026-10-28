"""n_visual 보정: 저장된 프레임 204곡을 n_visual.components 로 점수화 -> 세트별 mu/sd, 임계(전체 라이브 최댓값 + 0.1 x 범위) -> n_visual_cal.json.
같은 경로(n_visual)로 만든 점수가 run_ablate 의 sig2b16 앙상블 점수와 일치하는지(상관 > 0.99) assert. python experiments/visual/calibrate.py"""
import json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments" / "visual")); os.chdir(ROOT)
import numpy as np
from PIL import Image
import n_visual, prompts
from evlib import manifest, PV
for k, v in n_visual.SETS.items():
    assert prompts.SETS[k] == v, k                                  # 실험 프롬프트와 배포 프롬프트가 같다
m = manifest(); C, keys = [], []
for r in m.itertuples():
    fs = sorted((PV / "frames" / r.key.replace("/", "__")).glob("*.jpg"), key=lambda p: int(p.stem))
    if len(fs) < 3:
        continue
    C.append(n_visual.components([Image.open(f) for f in fs])); keys.append(r.key)
C = np.array(C); mu, sd = C.mean(0), C.std(0)
z = ((C - mu) / sd).mean(1)
live = m.set_index("key").loc[keys].live.to_numpy() == 1
lv = z[live]; thr = float(lv.max() + 0.1 * (lv.max() - lv.min()))
Z = np.load(PV / "zs_scores.npz", allow_pickle=True)
ref = np.mean([Z[k] for k in Z.files if k.startswith("sig2b16|") and k.endswith("|max")], 0)
assert (Z["keys"] == np.array(keys)).all() and np.corrcoef(z, ref)[0, 1] > 0.99, np.corrcoef(z, ref)[0, 1]
json.dump(dict(mu=mu.tolist(), sd=sd.tolist(), thr=thr, n=len(keys), n_live=int(live.sum()), live_max=float(lv.max()), live_min=float(lv.min()), model=list(n_visual.MODEL)), open("n_visual_cal.json", "w"), indent=1)
print(f"보정 {len(keys)}곡, 라이브 {live.sum()}: 임계 {thr:.3f} (라이브 범위 {lv.min():.2f}~{lv.max():.2f}), 상관 {np.corrcoef(z, ref)[0,1]:.4f}, 임계 초과 N {int(((z>thr)&~live).sum())}/{int((~live).sum())}, 라이브 {int(((z>thr)&live).sum())}")
