"""축 (c) 추가: Conformal Risk Control(Angelopoulos 외, arXiv 2208.02814; 원문 HTML 에서 읽은 정의: lambda_hat = inf{lambda : n/(n+1) * R_n(lambda) + B/(n+1) <= alpha}, 단조 손실이면 E[L_(n+1)(lambda_hat)] <= alpha)
로 '학습 라이브의 보지 않은 p' 분포에서 임계를 정해 라이브 손실률을 alpha 로 묶을 수 있는지 그룹 hold-out 에서 시험한다. 손실 L = 1[라이브 p < 임계] (임계가 낮을수록 작아지는 단조 손실, B=1).
라이브 k 개까지 놓쳐도 되는 조건: (k+1)/(n+1) <= alpha  ->  k = floor(alpha(n+1)) - 1, 임계 = 라이브 p 의 (k+1)번째로 작은 값(그 값 미만이 k 개).
주의: 보장은 학습 그룹과 시험 그룹이 교환 가능할 때만이다. 방송/스트리머 hold-out 은 교환 가능성이 깨져서 실측으로 확인한다.
사용: C:/_tools/wt/venv/Scripts/python.exe harness/exp_crc.py"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.ranker import *

def crc_thr(lv, alpha):
    lv = np.sort(lv); n = len(lv)
    k = int(np.floor(alpha * (n + 1))) - 1
    return 0.0 if k < 0 else float(lv[k])          # k+1 번째로 작은 값 이상이면 노출: 그 미만이 k 개

df = LR.load(); df["streamer"] = df.name
y = df.live.to_numpy(); out = {}
for by in ("group", "streamer"):
    rres, _ = LR.holdout(df, by, "D", 0.1); rule_vis = rres == "ok"
    for model in ("lr", "lgb"):
        H = holdout_rank(df, by, model, FULL)
        for alpha in (0.02, 0.05, 0.10, 0.20):
            thr = np.zeros(len(df))
            tf = []
            for grp, lv in H["lvs"].items():
                t = crc_thr(lv, alpha); thr[(df[by] == grp).to_numpy()] = t; tf.append(t)
            vis = ~H["veto"] & (H["p"] >= thr)
            live_all = (y == 1)
            miss_rate = float((live_all & ~vis).sum() / live_all.sum())
            sc = score(df, by, vis, 300); sa = score(df, by, vis & rule_vis, 300)
            out[f"{by}/{model}/a={alpha}"] = dict(miss_rate=round(miss_rate, 3), N_expose_b9=sc["blind9"]["N_expose"], L_loss_b9=sc["blind9"]["L_loss"], L_loss_all=sc["전체"]["L_loss"], AND_N_b9=sa["blind9"]["N_expose"], AND_L_all=sa["전체"]["L_loss"], thr_mean=round(float(np.mean(tf)), 3), thr_sd=round(float(np.std(tf)), 3))
            print(f"{by:8} {model:3} alpha {alpha:4}: 라이브 놓침률 {miss_rate:.3f} (목표 <= {alpha}) | blind9 N 노출 {sc['blind9']['N_expose']}/55 손실 {sc['blind9']['L_loss']}/49 | 전체 손실 {sc['전체']['L_loss']}/88 | 규칙과 AND: N {sa['blind9']['N_expose']}/55 손실(전체) {sa['전체']['L_loss']}/88 | 임계 {np.mean(tf):.3f} sd {np.std(tf):.3f}")
json.dump(out, open(PH / "exp_crc.json", "w"), ensure_ascii=False, indent=1)
