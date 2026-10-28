"""보컬 스템(asr_stem.py)에서 torchcrepe 피치 특징을 곡 구간 [base] 안에서 계산 -> cache/proto_asr/pitch.csv (따라 부르기/원곡 보컬 겹침 판별 실험).
  active_frac : 스템 0.01초 프레임 rms >= -45dB 비율        voiced_frac : active 중 periodicity >= 0.5 비율
  poly_frac   : active 중 periodicity < 0.35 비율(화음/이중 음성이면 높아짐)     jump_rate : 인접 프레임 음정 차 > 600센트 비율(옥타브 점프)
  stem_rel_db : 스템 중앙값 dB - 혼합 중앙값 dB (보컬이 혼합에서 차지하는 정도)
  python experiments/asr_pitch.py [--set all]"""
import sys, os, json, argparse
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT); sys.path.insert(0, str(ROOT / "experiments"))
import numpy as np, soundfile as sf, torch, torchcrepe, pandas as pd
from asr_run import groups, pick, load_audio


def feats(stem, mix, s_rel, e_rel):
    x = torch.from_numpy(stem[int(s_rel * 16000):int(e_rel * 16000)])[None].cuda()
    pitch, per = torchcrepe.predict(x, 16000, 160, 65.0, 1000.0, "tiny", batch_size=1024, device="cuda", return_periodicity=True, decoder=torchcrepe.decode.viterbi)
    pitch, per = pitch[0].cpu().numpy(), per[0].cpu().numpy()
    n = min(len(per), len(stem[int(s_rel * 16000):int(e_rel * 16000)]) // 160)
    sx = stem[int(s_rel * 16000):int(e_rel * 16000)][:n * 160].reshape(n, 160)
    db = 20 * np.log10(np.sqrt((sx ** 2).mean(1)) + 1e-7)
    act = db >= -45
    pitch, per = pitch[:n], per[:n]
    cents = 1200 * np.log2(np.maximum(pitch, 1e-3) / 55.0)
    v = act & (per >= 0.5)
    jump = np.abs(np.diff(cents)) > 600
    both = act[1:] & act[:-1]
    mx = mix[int(s_rel * 16000):int(e_rel * 16000)]
    m = len(mx) // 800
    mdb = 20 * np.log10(np.sqrt((mx[:m * 800].reshape(m, 800) ** 2).mean(1)) + 1e-7)
    sdb = 20 * np.log10(np.sqrt((sx[:n // 5 * 5].reshape(-1, 800) ** 2).mean(1)) + 1e-7) if n >= 5 else mdb
    return dict(active_frac=act.mean(), voiced_frac=v.sum() / max(act.sum(), 1), poly_frac=(act & (per < 0.35)).sum() / max(act.sum(), 1),
                jump_rate=(jump & both).sum() / max(both.sum(), 1), stem_rel_db=float(np.median(sdb) - np.median(mdb[:len(sdb)])))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--set", default="all"); a = ap.parse_args()
    rows = []
    for g in pick(a.set, groups()):
        f = ROOT / "cache/proto_asr/stem" / f"{g['gid']}.wav"
        if not f.exists():
            continue
        t0 = max(0.0, g["base"][0] - 60.0)
        stem, _ = sf.read(f, dtype="float32")
        mix = load_audio(g, t0, g["base"][1] + 60.0, "wav", None)
        r = feats(stem, mix, g["base"][0] - t0, g["base"][1] - t0)
        rows.append(dict(gid=g["gid"], lab=g["lab"], tag=g["tag"], vno=g["vno"], **r))
    pd.DataFrame(rows).to_csv(ROOT / "cache/proto_asr/pitch.csv", index=False)
    print(pd.DataFrame(rows).groupby("tag")[["active_frac", "voiced_frac", "poly_frac", "jump_rate", "stem_rel_db"]].median().round(3))
