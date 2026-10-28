"""Demucs(htdemucs) 로 곡 구간 전후(asr_run 과 같은 창)를 분리해 보컬 스템을 16kHz mono 로 저장: cache/proto_asr/stem/<gid>.wav  (asr_run.py --src vocal 의 입력).
  python experiments/asr_stem.py --set pilot|all|g1,g2 [--margin 60]
shortcut: 원본이 16kHz mono 라 44.1kHz 로 올려 분리하므로 8kHz 위 대역은 비어 있다(분리 품질 하한). 방송 마이크(스트리머 목소리)와 노래 보컬은 구분하지 못한다."""
import sys, os, json, time, argparse
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT); sys.path.insert(0, str(ROOT / "experiments"))
import numpy as np, soundfile as sf, torch, torchaudio
from asr_run import groups, pick, load_audio

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--set", default="pilot"); ap.add_argument("--margin", type=float, default=60.0); ap.add_argument("--model", default="htdemucs")
    a = ap.parse_args()
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    m = get_model(a.model).cuda().eval()
    out = ROOT / "cache/proto_asr/stem"; out.mkdir(parents=True, exist_ok=True)
    rs_up, rs_dn = torchaudio.transforms.Resample(16000, 44100).cuda(), torchaudio.transforms.Resample(44100, 16000).cuda()
    vi = m.sources.index("vocals")
    tot = t_all = 0.0
    for g in pick(a.set, groups()):
        f = out / f"{g['gid']}.wav"
        if f.exists():
            continue
        t0 = max(0.0, g["base"][0] - a.margin)
        x = load_audio(g, t0, g["base"][1] + a.margin, "wav", None)
        t = time.time()
        with torch.no_grad():
            w = rs_up(torch.from_numpy(x).cuda())[None].repeat(2, 1)[None]          # 1 x 2 x T
            ref = w.mean(1, keepdim=True).std()
            y = apply_model(m, (w - w.mean()) / (ref + 1e-8), device="cuda", split=True, overlap=0.25, segment=7, progress=False)[0, vi]
            v = rs_dn(y.mean(0, keepdim=True) * (ref + 1e-8))[0].cpu().numpy()
        sf.write(f, v, 16000)
        tot += len(x) / 16000; t_all += time.time() - t
        print(g["gid"], f"{time.time() - t:.1f}s/{len(x) / 16000:.0f}s", flush=True)
        torch.cuda.empty_cache()
    print(f"RTF {t_all / max(tot, 1):.4f} 최대 VRAM {torch.cuda.max_memory_allocated() / 1e6:.0f}MB")
