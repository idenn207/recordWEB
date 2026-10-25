"""같은 wav 안의 두 구간이 같은 곡(같은 MR)인지: 크로마 DTW 정규화 비용(낮을수록 같음). 대조로 임의 구간 2개와도 잰다. 도커 song-detect 안에서 실행.
사용: python same12.py <wav> <s1> <e1> <s2> <e2> [<s3> <e3> ...]   (첫 구간과 나머지 각각의 비용)"""
import sys
import numpy as np, librosa
w, a = sys.argv[1], [float(x) for x in sys.argv[2:]]
def ch(s, e):
    y, _ = librosa.load(w, sr=16000, offset=s, duration=e - s)
    return librosa.feature.chroma_stft(y=y, sr=16000, n_fft=4096, hop_length=4000)
A = ch(a[0], a[1])
for s, e in zip(a[2::2], a[3::2]):
    B = ch(s, e)
    D, wp = librosa.sequence.dtw(A, B, metric="cosine")
    print(f"{a[0]:.0f}-{a[1]:.0f} vs {s:.0f}-{e:.0f}: dtw {D[-1, -1] / len(wp):.3f}")
