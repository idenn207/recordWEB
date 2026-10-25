"""끝 구간 분석: [t0,t1) 을 Demucs 로 분리해 5초 창별 믹스/보컬/반주(믹스-보컬) dBFS. 사용: python exp14_stems.py wav t0 t1"""
import sys, numpy as np, torch, torchaudio
sys.path.insert(0, "/work")
from detect import SR
from snap import pcm_of
from demucs.apply import apply_model
from demucs.pretrained import get_model
wav, t0, t1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
pcm = pcm_of(wav)
m = get_model("htdemucs").eval().cuda(); vi = m.sources.index("vocals")
x = torch.from_numpy(pcm[int(t0 * SR):int(t1 * SR)].astype(np.float32) / 32768)
x = torchaudio.functional.resample(x, SR, 44100)[None].repeat(2, 1)
with torch.no_grad():
    v = apply_model(m, x[None], device="cuda")[0][vi].cpu()
db = lambda y: 10 * np.log10(float(y.pow(2).mean()) + 1e-12)
n = 5 * 44100
for i in range(0, x.shape[1] - n + 1, n):
    X, V = x[:, i:i + n], v[:, i:i + n]
    print("%d mix=%.0f voc=%.0f acc=%.0f" % (t0 + i / 44100, db(X), db(V), db(X - V)))
