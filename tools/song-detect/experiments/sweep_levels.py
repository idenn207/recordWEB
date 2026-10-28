"""점수 양자화 기반 임계 재중심화. YAMNet tflite 출력이 int8 이라 모든 캐시(147개)의 Speech/Music 점수는 32개 값(0.0039 간격 ~ 0.3 간격)만 갖는다.
프레임 점수와 직접 비교하는 임계(`x >= t`, `x < t`)는 t 가 (아래 레벨, 위 레벨] 안이면 결과가 완전히 같다(동치 구간). 현재 값이 그 구간의 가장자리에 붙어 있으면 +0.5% 만 움직여도 곡 경계가 튄다(머리카락 방아쇠).
이 도구가 (1) 각 상수의 동치 구간과 현재 위치, (2) 구간 중앙값으로 옮긴 설정이 전 방송 840구간 결과를 하나도 안 바꾸는지(경계 완전 동일), (3) 옮긴 뒤 +-1% 교란 안정성을 잰다.
  python experiments/sweep_levels.py"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import sweep_core as S

Z = np.load("cache/proto_sweep/score_levels.npz")
# (상수, 점수 열, 비교 연산): 코드에서 프레임 점수와 직접 비교하는 것만(평균/비율 값과 비교하는 임계는 해당 없음)
SPEC = [("snap.LOW", "music", "<"), ("snap.MU", "music", "<"), ("snap.SPEECH", "speech", ">="), ("snap.E1_MU", "music", ">="), ("snap.E1_SP", "speech", "<"),
        ("snap.E1B_MU", "music", ">="), ("snap.E1B_SP", "speech", "<")]


def klass(t, levels, op):
    """t 와 같은 결과를 내는 구간 (lo, hi, lo_open, hi_open). >= 와 < 는 (아래 레벨, 위 레벨], > 와 <= 는 [아래 레벨, 위 레벨)."""
    i = int(np.searchsorted(levels, t, side="left"))
    lo, hi = (levels[i - 1] if i > 0 else -np.inf), (levels[i] if i < len(levels) else np.inf)
    return float(lo), float(hi)


def recenter():
    import tune
    cur = tune.listing()
    rows, cfg = [], {}
    for k, col, op in SPEC:
        t = cur[k]
        lo, hi = klass(t, Z[col], op)
        mid = (lo + hi) / 2
        rows.append(dict(key=k, col=col, op=op, now=t, lo=lo, hi=hi, to_lo=(t - lo) / t, to_hi=(hi - t) / t, mid=mid, to_lo_mid=(mid - lo) / mid, to_hi_mid=(hi - mid) / mid))
        cfg[k] = round(mid, 4)
    return rows, cfg


if __name__ == "__main__":
    rows, cfg = recenter()
    print("상수 | 현재 | 동치 구간 (lo, hi] | 현재->아래 | 현재->위 | 중앙값 | 중앙값 기준 여유")
    for r in rows:
        print(f"{r['key']:12} {r['now']:<6g} ({r['lo']:.4f}, {r['hi']:.4f}]  {r['to_lo']:+.1%} / {r['to_hi']:+.1%}  -> {r['mid']:.4f}  ({-r['to_lo_mid']:.1%} / {r['to_hi_mid']:+.1%})")
    ev = S.Evaluator(8, wide=True)
    base = ev.evaluate({})
    new = ev.evaluate(cfg)
    diff = sum(1 for v in base["_R"] for k, c in base["_R"][v].items() if max(abs(c[x] - new["_R"][v][k][x]) for x in ("song_s", "song_e", "clip_s", "clip_e")) > 1e-6)
    print("재중심화 설정", cfg)
    print("기준", {k: base[k] for k in ("gold_dev", "hit05", "hit3", "hit10", "dir_pass", "ok_pass", "len_gt5")}, "| 재중심화", {k: new[k] for k in ("gold_dev", "hit05", "hit3", "hit10", "dir_pass", "ok_pass", "len_gt5")}, f"| 840구간 중 경계 달라진 곡 {diff}")
    assert diff == 0 and new["gold_dev"] == 0
    # +-1%, +-2%, +-4% 교란 단독 안정성(현재 vs 재중심화)
    out = {}
    for name, c0 in (("현재", {}), ("재중심화", cfg)):
        import tune
        cu = tune.listing()
        res = []
        for k, col, op in SPEC:
            t = c0.get(k, cu[k])
            row = {}
            for f in (-0.04, -0.02, -0.01, 0.01, 0.02, 0.04):
                r = ev.evaluate({**c0, k: t * (1 + f)})
                row[f] = (r["gold_dev"], r["moved2"])
            res.append((k, row))
        out[name] = res
        print(f"[{name}] 단독 교란 시 golden 이탈(-4/-2/-1/+1/+2/+4%):")
        for k, row in res:
            print(f"   {k:12} " + " ".join(f"G{v[0]}/m{v[1]}" for v in row.values()))
    json.dump(dict(rows=rows, cfg=cfg, diff=diff, pert={n: [(k, {str(f): v for f, v in r.items()}) for k, r in res] for n, res in out.items()}), open("cache/proto_sweep/levels.json", "w"), ensure_ascii=False)
    ev.close()
