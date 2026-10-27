"""끝 경계 자체 검수용 그림: wav 의 [t0,t1] 스펙트로그램 + 0.25초 rms + 점수(Singing/Speech/Music) 위에 표식(시각:이름)을 세로선으로 그린다.
사용: python experiments/end_view.py <wav> <t0> <t1> <출력.png> [시각:이름 ...]     (예: ... 10464.0:old 10483.5:new)
점검 순서: 그림을 Read 로 열어 (1) 표식 앞 소리가 곡(MR/노래)인지, (2) 표식 뒤가 끊김/멘트/무음인지 본다. 귀로 듣는 것은 아니다(파형 수준)."""
import sys, wave
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from paths import cache_of


def plot(wav, t0, t1, marks, out, title=""):
    w = wave.open(wav); sr = w.getframerate(); t0 = max(0.0, t0); w.setpos(int(t0 * sr))
    x = np.frombuffer(w.readframes(int((t1 - t0) * sr)), dtype=np.int16).astype(np.float32) / 32768
    S = np.load(cache_of(wav, ".scores.npy"))
    fig, ax = plt.subplots(3, 1, figsize=(16, 8.5), sharex=True, gridspec_kw={"height_ratios": [3, 1.2, 1.2]})
    ax[0].specgram(x, NFFT=1024, Fs=sr, noverlap=512, cmap="magma", vmin=-130, vmax=-40, xextent=(t0, t1)); ax[0].set_ylim(0, 6000); ax[0].set_title(title)
    h = int(sr * 0.25); n = len(x) // h
    ax[1].plot(t0 + np.arange(n) * 0.25, 20 * np.log10(np.sqrt((x[:n * h].reshape(n, h) ** 2).mean(1)) + 1e-6), "k", lw=.8); ax[1].set_ylabel("rms dB"); ax[1].set_ylim(-70, 0)
    i0 = int(t0 * 2); tt = np.arange(i0, min(int(t1 * 2), len(S))) / 2
    for k, (nm, c) in enumerate([("Singing", "r"), ("Speech", "b"), ("Music", "g")]):
        ax[2].plot(tt, S[i0:i0 + len(tt), k], c, lw=.8, label=nm)
    ax[2].legend(loc="upper right", ncol=3, fontsize=7); ax[2].set_ylim(0, 1)
    for i, (t, l) in enumerate(marks):
        if t0 <= t <= t1:
            for a in ax:
                a.axvline(t, color="cyan" if i % 2 else "lime", ls="--", lw=1.2)
            ax[0].text(t, 6100 + (i % 3) * 350, l, fontsize=8, clip_on=False)
    plt.tight_layout(); plt.savefig(out, dpi=60); plt.close()


if __name__ == "__main__":
    wav, t0, t1, out = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
    plot(wav, t0, t1, [(float(m.split(":")[0]), m.split(":")[1]) for m in sys.argv[5:]], out, Path(wav).stem)
