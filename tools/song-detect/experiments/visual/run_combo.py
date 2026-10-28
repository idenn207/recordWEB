"""오디오 규칙 hold-out(logo_route 행 D: tstd 재추정 + 신호 선택, 스트리머 제외) 위에 시각 veto 를 얹었을 때의 노출 N / 라이브 손실 (E: 게이트 배치 비교의 veto 열).
시각 veto = 제로샷 앙상블(run_ens.py 점수)의 스트리머 hold-out 임계(m 지정). python run_combo.py"""
import sys, warnings
warnings.filterwarnings("ignore")
from evlib import *
import logo_route as LR
Z = np.load(PV / "zs_scores.npz", allow_pickle=True)
df, _ = dataset("b32")
assert (Z["keys"] == df.key.to_numpy()).all()
sc = {k: Z[k] for k in Z.files if k != "keys"}
pick = lambda f: np.mean([sc[k] for k in sc if f(k)], 0)
VIS = {"4모델 전세트 max": pick(lambda k: k.endswith("|max")), "l14+sig2 전세트 max": pick(lambda k: k.endswith("|max") and k.split("|")[0] in ("l14", "sig2b16")),
       "4모델 레이아웃 세트 제외": pick(lambda k: k.endswith("|max") and "|E_layout|" not in k)}
sig = LR.load(); sig["streamer"] = sig.name
base_out, _ = LR.holdout(sig, "streamer", "D", 0.1)
a_out, _ = LR.holdout(sig, "streamer", "A", 0.0)
b = pd.DataFrame(dict(key=sig.key, live=sig.live, set=sig.set, tag=sig.tag, D=base_out, A=a_out))
for vn, s in VIS.items():
    for by in ("streamer", "group"):
        for m in (0.0, 0.1, 0.2):
            r = veto(df, lambda tr, te: (s[tr], s[te]), by, ms=(m,))
            h = pd.DataFrame(dict(key=df.key, vhit=r[f"hit{m}"]))
            x = b.merge(h, on="key", how="left"); x["vhit"] = x.vhit.fillna(False).astype(bool)
            for sub, mk in (("blind9", x.set == "blind9"), ("전체", x.set != "")):
                z = x[mk]; N = z[z.live == 0]; L = z[z.live == 1]
                f = lambda col: (int(((N[col] == "ok") & ~N.vhit).sum()), int(((L[col] != "ok") | L.vhit).sum()))
                n0 = {c: (int((N[c] == "ok").sum()), int((L[c] != "ok").sum())) for c in ("D", "A")}
                dN, dL = f("D"); aN, aL = f("A")
                print(f"{vn:18} {by:8} m={m} [{sub:6}] N={len(N)} L={len(L)} | 행 D(hold-out) 노출 {n0['D'][0]} 손실 {n0['D'][1]} -> +시각 노출 {dN} 손실 {dL} | 행 A(표본내) 노출 {n0['A'][0]} 손실 {n0['A'][1]} -> +시각 노출 {aN} 손실 {aL}", flush=True)
