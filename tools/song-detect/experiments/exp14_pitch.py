"""5초 창별 음정 안정도: pyin F0 에서 반음 +-0.5 안 유지 구간(>=0.25초)에 속한 유성 프레임 비율(노래는 높고 말은 낮다), 유성 비율. 사용: python exp14_pitch.py wav t0 t1"""
import sys, numpy as np, librosa
wav, t0, t1 = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
with open(wav, "rb") as f: off = f.read(4096).find(b"data") + 8
pcm = np.memmap(wav, dtype="<i2", mode="r", offset=off)
for t in np.arange(t0, t1, 5):
    y = pcm[int(t*16000):int((t+5)*16000)].astype(np.float32)/32768
    f0, vf, _ = librosa.pyin(y, fmin=80, fmax=800, sr=16000, frame_length=1024, hop_length=160)   # 10ms
    st = np.where(vf & ~np.isnan(f0), 12*np.log2(np.nan_to_num(f0, nan=1)/55), np.nan)
    stable = 0; i = 0
    while i < len(st):
        if np.isnan(st[i]): i += 1; continue
        j = i
        while j+1 < len(st) and not np.isnan(st[j+1]) and abs(st[j+1]-np.median(st[i:j+1])) < 0.5: j += 1
        if j-i+1 >= 25: stable += j-i+1
        i = j+1
    vo = np.sum(~np.isnan(st))
    print("%d voiced=%.2f stable=%.2f" % (t, vo/len(st), stable/max(vo,1)))
