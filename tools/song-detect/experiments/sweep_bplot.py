"""경계 동시 탐색(bsearch.jsonl) 파레토 그림: x = 이동한 곡 수(moved2, 영향 범위), y = 정답 점수(hit 합 + 방향). golden 이탈 0 만 진하게."""
import json
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
plt.rcParams["font.family"] = "Malgun Gothic"; plt.rcParams["axes.unicode_minus"] = False
rows = [json.loads(l) for l in open("cache/proto_sweep/bsearch.jsonl", encoding="utf8")]
m = [r["m"] for r in rows]
y = np.array([x["hit05"] + x["hit3"] + x["hit10"] + x["dir_pass"] for x in m]); xm = np.array([x.get("moved2", 0) for x in m]); g = np.array([x["gold_dev"] for x in m])
fig, ax = plt.subplots(1, 2, figsize=(14, 6))
ax[0].scatter(xm[g > 0], y[g > 0], s=8, c="lightgray", label=f"golden 이탈 있음 {int((g > 0).sum())}")
ax[0].scatter(xm[g == 0], y[g == 0], s=22, c="crimson", label=f"golden 이탈 0 {int((g == 0).sum())}")
ax[0].plot([0], [y[0]], "c*", ms=16, label="현재(기준)")
ax[0].set_xlabel("2초 넘게 움직인 곡 수(전 방송 840구간 중)"); ax[0].set_ylabel("hit@0.5+3+10 + 방향 통과 (기준 38)"); ax[0].legend(); ax[0].set_title("TPE 601시험(기본 +-6%): 영향 범위 대 정답 점수")
ax[1].hist(g, bins=range(0, 40), color="gray"); ax[1].set_xlabel("golden 이탈 곡 수"); ax[1].set_ylabel("시험 수"); ax[1].set_title("시험별 golden 이탈 분포(동시 +-6% 교란)")
plt.tight_layout(); plt.savefig("cache/proto_sweep/bsearch.png", dpi=65)
print("기준 점수", y[0], "골든 0 시험", int((g == 0).sum()), "그 중 점수>기준", int(((g == 0) & (y > y[0])).sum()), "점수>=기준 & 이동<=5", int(((g == 0) & (y >= y[0]) & (xm <= 5)).sum()))
