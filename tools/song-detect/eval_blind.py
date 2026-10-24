"""블라인드 세트 평가: route 등급별 정밀도/재현율(Wilson 95%), 스트리머 단위 leave-one-streamer-out, 경계 오차.
세트 폴더 data/<세트>/key.json 이 있어야 하고 라벨은 data/labels.json (labels.py).
등급은 key.json 의 저장값이 아니라 현재 route.tier 로 다시 계산한다(has_refs 는 tier_why 의 '새 채널' 여부로 복원).
LOSO: scene_idle 임계값을 한 스트리머를 뺀 나머지로 고르고(auto 오탐 최소 -> auto 라이브 최대) 뺀 스트리머에 적용.
사용: python eval_blind.py [세트 ...]   (기본: labels.json 의 모든 세트)"""
import json, sys
from math import sqrt
from pathlib import Path
import route
from labels import load


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    c = (p + z * z / 2 / n) / (1 + z * z / n)
    h = z * sqrt(p * (1 - p) / n + z * z / 4 / n / n) / (1 + z * z / n)
    return (c - h, c + h)


def fmt(k, n):
    lo, hi = wilson(k, n)
    return f"{k}/{n}" + (f" = {k / n:.0%} [{lo:.0%}-{hi:.0%}]" if n else "")


def rows(sets):
    R = []
    for s in sets:
        key = json.load(open(f"data/{s}/key.json", encoding="utf8"))
        for v, l in load()[s].items():
            g = dict(key[v], keep=True)
            R.append(dict(id=f"{s}/{v}", name=key[v]["name"], g=g, has_refs="새 채널" not in key[v]["tier_why"], **l))
    return R


def tiers(R, p=route.P):
    return [route.tier(r["g"], r["has_refs"], p)[0] for r in R]


def report(R, T, title):
    print(f"[{title}] 라이브 {sum(r['live'] for r in R)} / 전체 {len(R)}")
    L = sum(r["live"] for r in R)
    for t in ("auto", "review", "drop"):
        n = sum(x == t for x in T)
        tp = sum(x == t and r["live"] for r, x in zip(R, T))
        print(f"  {t:6} 정밀도 {fmt(tp, n)}  재현율 {fmt(tp, L)}")
    print(f"  auto+review 합 재현율 {fmt(sum(x != 'drop' and r['live'] for r, x in zip(R, T)), L)}")


def best_idle(R):
    """scene_idle 후보(관측 장면값 사이 중간점)에서 auto 오탐 최소 -> auto 라이브 최대 -> 값이 큰 쪽(보수적)."""
    ds = sorted({r["g"]["scene"] for r in R if r["g"].get("scene") is not None})
    cand = [0.0] + [(a + b) / 2 for a, b in zip(ds, ds[1:])] + [ds[-1] + 1e-6]
    def score(c):
        T = tiers(R, dict(route.P, scene_idle=c))
        fp = sum(x == "auto" and not r["live"] for r, x in zip(R, T))
        tp = sum(x == "auto" and r["live"] for r, x in zip(R, T))
        return (-fp, tp, c)
    return max(cand, key=score)


def loso(R):
    names = sorted({r["name"] for r in R})
    held, chosen = [], {}
    for n in names:
        tr = [r for r in R if r["name"] != n]
        c = best_idle(tr)
        chosen[n] = round(c, 4)
        p = dict(route.P, scene_idle=c)
        for r in R:
            if r["name"] == n:
                held.append((r, route.tier(r["g"], r["has_refs"], p)[0]))
    report([h[0] for h in held], [h[1] for h in held], "LOSO scene_idle (뺀 스트리머에 적용한 합산)")
    print("  접은 값별 scene_idle:", chosen, " 고정값", route.P["scene_idle"])
    print("  주의: 고정값은 이 표본을 보고 정했으므로 낙관적, LOSO 가 일반화에 가까움")


def boundary(R):
    B = [r for r in R if r["live"] and r["boundary_ok"] and r["user"]]
    es, ee = [], []
    for r in B:
        g = r["g"]
        pad = g["start"] - g["clip_start"]  # 클립 안에서 탐지 시작 위치(패딩, 0 으로 잘렸으면 20 보다 작음)
        es.append(pad - r["user"][0])
        ee.append(pad + g["len"] - r["user"][1])
    n = len(B)
    print(f"[경계] 라이브(병합 실패 제외) {n}개  오차 = 탐지 - 사용자(초)")
    print("  시작", [round(x, 1) for x in es], " 끝", [round(x, 1) for x in ee])
    print(f"  시작 +-2초 적중 {fmt(sum(abs(x) <= 2 for x in es), n)}  끝 +-2초 적중 {fmt(sum(abs(x) <= 2 for x in ee), n)}")
    print(f"  끝이 2초 넘게 일찍 잘림 {fmt(sum(x < -2 for x in ee), n)}  늦게 남음 {fmt(sum(x > 2 for x in ee), n)}")
    bad = [r["id"] for r in R if r["live"] and not r["boundary_ok"]]
    if bad:
        print("  경계 불량(제외):", bad)
    return es, ee


def main(sets):
    R = rows(sets)
    report(R, tiers(R), "현재 route.P 고정값")
    for t in sorted({r["tag"] for r in R if r["tag"]}):
        T = tiers(R)
        print(f"  오탐 {t}: auto {sum(x == 'auto' and r['tag'] == t for r, x in zip(R, T))} / review {sum(x == 'review' and r['tag'] == t for r, x in zip(R, T))} / drop {sum(x == 'drop' and r['tag'] == t for r, x in zip(R, T))} (전체 {sum(r['tag'] == t for r in R)})")
    loso(R)
    return R, boundary(R)


if __name__ == "__main__":
    sets = sys.argv[1:] or list(load())
    R, (es, ee) = main(sets)
    # 한 줄 자가검증: blind5 에서 라이브 8, 경계 평가 7개
    if sets == ["blind5"]:
        assert sum(r["live"] for r in R) == 8 and len(es) == 7
