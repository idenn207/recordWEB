"""route 임계의 과적합 위험표: OAT 곡선에서 (라이브 손실 0, N auto 0, N 노출이 기본값 이하) 를 동시에 지키는 연속 구간과 기본값의 위치.
여유 = 기본값에서 구간 끝까지 거리 / |기본값|. 한쪽 여유가 5% 이하면 '절벽 위'(표본 몇 건이 경계를 정함), 구간이 범위 끝까지 이어지면 '열림'.
  python experiments/sweep_route_risk.py -> cache/proto_sweep/route_risk.md"""
import json
from pathlib import Path
import numpy as np
O = Path("cache/proto_sweep")
r = json.load(open(O / "route_oat.json"))
rows = []
for k, d in r.items():
    v = np.array(d["v"]); L = np.array(d["L_loss"]); A = np.array(d["N_auto"]); N = np.array(d["N_all"]); la = np.array(d["L_auto"])
    i0 = int(np.argmin(abs(v - d["default"])))
    ok = (L == 0) & (A == 0) & (N <= N[i0])
    a = b = i0
    while a > 0 and ok[a - 1]: a -= 1
    while b < len(v) - 1 and ok[b + 1]: b += 1
    d0 = d["default"]
    ml = None if a == 0 else (d0 - v[a]) / abs(d0) * 100
    mh = None if b == len(v) - 1 else (v[b] - d0) / abs(d0) * 100
    why_lo = "" if a == 0 else ("라이브 손실" if L[a - 1] else "N auto" if A[a - 1] else "N 증가")
    why_hi = "" if b == len(v) - 1 else ("라이브 손실" if L[b + 1] else "N auto" if A[b + 1] else "N 증가")
    flag = "절벽 위" if any(m is not None and m <= 5 for m in (ml, mh)) else "열림(범위 끝까지)" if (ml is None and mh is None) else "중간"
    rows.append((k, d0, v[a], v[b], ml, mh, why_lo, why_hi, flag, int(la[a:b + 1].min()), int(la[a:b + 1].max())))
out = ["| 임계 | 기본 | 안전 구간(손실0, N auto 0, N<=기본) | 아래쪽 여유(끝 사유) | 위쪽 여유(끝 사유) | 구간 안 auto 라이브 | 판정 |", "|---|---|---|---|---|---|---|"]
f = lambda m, w: "범위 끝까지" if m is None else f"{m:.1f}% ({w})"
for k, d0, lo, hi, ml, mh, wl, wh, fl, amin, amax in sorted(rows, key=lambda t: min(x for x in (t[4], t[5]) if x is not None) if any(x is not None for x in (t[4], t[5])) else 1e9):
    out.append(f"| {k} | {d0:g} | {lo:.4g} ~ {hi:.4g} | {f(ml, wl)} | {f(mh, wh)} | {amin}~{amax} | {fl} |")
(O / "route_risk.md").write_text("\n".join(out), encoding="utf8")
print("\n".join(out))
