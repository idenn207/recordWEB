"""곡 시작 직전(프리롤)에 허밍이 있는지 본다. 허밍 = 한 음에 머무는 유성음(음정 변화 작음). 말하기 = 음정이 계속 흐른다.
사용: python hum.py <wav> <t0> <t1>   -> 구간 안 '안정 유성음' 최장 길이(초)와 위치"""
import sys, numpy as np, librosa
from pathlib import Path

SR, HOP = 16000, 160   # 10ms 프레임


def stable_runs(wav, t0, t1, max_semi=0.6, min_voiced=0.5):
    with open(wav, "rb") as f:
        off = f.read(4096).find(b"data") + 8
    pcm = np.memmap(wav, dtype="<i2", mode="r", offset=off)
    y = pcm[int(t0 * SR):int(t1 * SR)].astype(np.float32) / 32768
    f0, vf, vp = librosa.pyin(y, fmin=80, fmax=1000, sr=SR, frame_length=1024, hop_length=HOP)
    midi = 12 * np.log2(np.where(vf & (vp > 0.6), f0, np.nan) / 440) + 69
    runs, i, n = [], 0, len(midi)
    while i < n:
        if np.isnan(midi[i]):
            i += 1
            continue
        j = i + 1
        while j < n and not np.isnan(midi[j]) and abs(midi[j] - midi[j - 1]) < max_semi:
            j += 1
        if (j - i) * HOP / SR >= min_voiced:
            runs.append((t0 + i * HOP / SR, (j - i) * HOP / SR, float(np.nanmedian(midi[i:j]))))
        i = j
    return runs


if __name__ == "__main__":
    for s, l, m in stable_runs(Path(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])):
        print(f"  {int(s // 60)}:{s % 60:05.2f} len={l:.2f}s midi={m:.1f}")
