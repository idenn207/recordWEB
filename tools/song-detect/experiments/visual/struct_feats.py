"""구조 특징 (E): 프레임 8장에서 OpenCV 로 싼 특징을 뽑아 cache/proto_visual/struct.csv 로. 곡 단위 = 프레임 평균(m_)과 시간축 변화(t_).
  dark/bright : 어두운(<20)/밝은(>215) 픽셀 비율          edge : Canny 에지 밀도(글자/UI 많으면 높음)     sat : 평균 채도
  bot_edge/right_edge : 하단/우측 1/4 에지 밀도          center_sat : 중앙 채도(큰 아바타 얼굴은 높음)    uniq_col : 양자화 색 수(정지/단색 화면은 낮음)
  t_diff : 프레임 간 평균 절대차(레이아웃/장면 변화)       t_hist : 프레임 간 색 히스토그램 거리
python struct_feats.py"""
import json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; os.chdir(ROOT)
import cv2, numpy as np, pandas as pd

FR = Path("cache/proto_visual/frames")
rows = []
for r in json.load(open("cache/proto_visual/manifest.json", encoding="utf8")):
    fs = sorted((FR / r["key"].replace("/", "__")).glob("*.jpg"), key=lambda p: int(p.stem))
    if len(fs) < 3:
        continue
    F = [cv2.imread(str(f)) for f in fs]
    per, H = [], []
    for im in F:
        g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY); hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV); e = cv2.Canny(g, 80, 160) > 0
        h, w = g.shape
        q = (im // 32).reshape(-1, 3); uc = len(np.unique(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]))
        per.append([(g < 20).mean(), (g > 215).mean(), e.mean(), hsv[..., 1].mean() / 255, e[int(h * .75):].mean(), e[:, int(w * .75):].mean(), hsv[h // 4:3 * h // 4, w // 4:3 * w // 4, 1].mean() / 255, uc / 512])
        H.append(cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256]).ravel() / g.size)
    per = np.array(per)
    d = np.mean([np.abs(F[i].astype(np.float32) - F[i + 1].astype(np.float32)).mean() for i in range(len(F) - 1)])
    th = np.mean([np.abs(H[i] - H[i + 1]).sum() for i in range(len(H) - 1)])
    names = ["dark", "bright", "edge", "sat", "bot_edge", "right_edge", "center_sat", "uniq_col"]
    row = dict(key=r["key"], **{f"m_{n}": v for n, v in zip(names, per.mean(0))}, **{f"s_{n}": v for n, v in zip(names, per.std(0))}, t_diff=d, t_hist=th)
    rows.append(row)
pd.DataFrame(rows).to_csv("cache/proto_visual/struct.csv", index=False)
print(len(rows), "곡")
