"""세 방송의 '우사기 랩'(같은 곡의 MR)은 크로마가 같다는 가정으로 위치를 찾는다. 세 방송의 짧은 구간(keep 무관, 20~130초)끼리 크로마 유사도를 교차 비교.
도커: python exp12_rapmatch.py cache/exp12_rap/c35/40 -> 방송 쌍별 상위 일치"""
import json, sys, itertools
from pathlib import Path
import numpy as np, librosa
sys.path.insert(0, "/work")
T = {"15636718": 45, "15696319": 41, "15827672": 72}
FR = 0.25
def chroma(wav, s, e):
    off = open(wav, "rb").read(4096).find(b"data") + 8
    pcm = np.memmap(wav, dtype="<i2", mode="r", offset=off)
    y = pcm[int(s * 16000):int(e * 16000)].astype(np.float32) / 32768
    c = librosa.feature.chroma_stft(y=y, sr=16000, hop_length=4000)  # 0.25s
    c = c / (np.linalg.norm(c, axis=0, keepdims=True) + 1e-9)
    return c
segs = {}
for v in T:
    wav = f"data/vod/{v}.wav"
    for g in json.load(open(f"{sys.argv[1]}/{v}.segments.json", encoding="utf8")):
        if 20 <= g["len"] <= 130:
            segs.setdefault(v, []).append((g, chroma(wav, g["start"], g["end"])))
def sim(a, b, w=80):  # a 의 20초 창들을 b 위에서 미끄러뜨려 최대 평균 코사인
    best = 0
    for i in range(0, max(1, a.shape[1] - w + 1), 20):
        q = a[:, i:i + w]
        for j in range(0, b.shape[1] - q.shape[1] + 1, 4):
            best = max(best, float((q * b[:, j:j + q.shape[1]]).sum(0).mean()))
    return best
res = []
for u, v in itertools.combinations(T, 2):
    for (g1, c1), (g2, c2) in itertools.product(segs[u], segs[v]):
        res.append((sim(c1, c2), u, round(g1["start"]), round(g1["len"]), g1["keep"], v, round(g2["start"]), round(g2["len"]), g2["keep"]))
res.sort(reverse=True)
print(len(res), "pairs; 상위 15")
for r in res[:15]: print(r)
print("중앙값", np.median([r[0] for r in res]), "95%", np.percentile([r[0] for r in res], 95))
