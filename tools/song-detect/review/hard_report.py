"""어려운 표본 종류별 요약: cache/exp11s(scene_hard.py 출력) + data/vods11.json -> 방송 종류(game/song/talk)별 route 등급, 의심 유형, 재생목록 약한 대응.
의심 유형(모두 휴리스틱, 정답 아님): 1절=길이<110초, 반복=같은 방송에서 길이가 +-6% 비슷한 다른 후보가 20분 안(연습/MR 반복), 게임화면=game 방송인데 multi=watch/idle(OST/리듬게임/게임 영상).
약한 정답: 같은 (스트리머,날짜) 재생목록 클립과 길이 +-15% 일치. 일치 후보가 여럿이면(chance>1) 우연일 수 있다.
uncertain: 신호가 충돌하는 후보(재생목록 길이 대응 + 장면 drop, 또는 game 방송 + 장면 live/review + 반복/1절 의심 + 음악 점수 높음) 상위 N개.
사용: python hard_report.py [exp11s 폴더] [uncertain 개수=5]"""
import json, sys
from collections import Counter, defaultdict
from pathlib import Path

D = Path(sys.argv[1] if len(sys.argv) > 1 else "cache/exp11s")
N = int(sys.argv[2]) if len(sys.argv) > 2 else 5
V = {v["videoNo"]: v for v in json.load(open("data/vods11.json", encoding="utf8"))}
LAB = json.load(open("data/labels.json", encoding="utf8"))   # 사용자 라벨(blind5/6): 같은 VOD, 시작 5초 이내면 같은 후보로 본다
UL = [(k["videoNo"], k["start"], "live" if LAB[b][i]["live"] else LAB[b][i]["tag"]) for b in ("blind5", "blind6") for i, k in json.load(open(f"data/review/{b}/key.json", encoding="utf8")).items()]
rows = []
for f in sorted(D.glob("*.segments.json")):
    v = V[int(f.name.split(".")[0])]
    segs = json.load(open(f, encoding="utf8"))
    for s in segs:
        r = dict(s, vid=v["videoNo"], name=v["name"], date=v["date"], kind=v["kind"], cat=v["category"])
        near = [t for t, L in v["playlist"] if abs(s["len"] - L) <= 0.15 * L]
        r["weak"], r["chance"] = (near[0] if near else None), sum(abs(g["len"] - L) <= 0.15 * L for t, L in v["playlist"] for g in segs if t == (near[0] if near else None))
        r["flags"] = [k for k, c in (("1절", s["len"] < 110), ("반복", any(g is not s and abs(g["len"] - s["len"]) <= 0.06 * s["len"] and abs(g["start"] - s["start"]) < 1200 for g in segs)),
                                    ("게임화면", v["kind"] == "game" and s.get("multi") in ("watch", "idle"))) if c]
        r["pl_rule"] = v.get("pl_rule")
        r["label"] = next((l for vn, st, l in UL if vn == v["videoNo"] and abs(st - s["start"]) < 5), None)
        rows.append(r)

print(f"후보 {len(rows)}개, 방송 {len({r['vid'] for r in rows})}개 (표본이 작아 비율은 경향일 뿐)")
for kind in ("game", "song", "talk"):
    R = [r for r in rows if r["kind"] == kind]
    print(f"\n[{kind}] 방송 {len({r['vid'] for r in R})}개, 후보 {len(R)}개  등급 {dict(Counter(r['tier'] for r in R))}")
    print("  의심 유형", dict(Counter(f for r in R for f in r["flags"])), " multi", dict(Counter(r.get("multi") for r in R)))
    print("  drop 사유", dict(Counter(r["tier_why"].split(" ")[0] + " " + r["tier_why"].split(" ")[1] if len(r["tier_why"].split(" ")) > 1 else r["tier_why"] for r in R if r["tier"] == "drop")))
    print("  review/auto 후보 중 의심 유형 있음:", sum(1 for r in R if r["tier"] != "drop" and r["flags"]), "/", sum(1 for r in R if r["tier"] != "drop"))
L = [r for r in rows if r["label"]]
print(f"\n사용자 라벨(blind5/6)과 겹치는 후보 {len(L)}개: 등급별 라벨 (live 외는 전부 오탐 유형)")
for kind in ("game", "song", "talk"):
    print(f"  {kind}:", {t: dict(Counter(r["label"] for r in L if r["kind"] == kind and r["tier"] == t)) for t in ("auto", "review", "drop")})
print("\n재생목록 약한 대응(길이 +-15%, 우연 가능):")
W = [r for r in rows if r["weak"]]
print(f"  대응 후보 {len(W)}개 중 chance>2(우연 가능성 큼) {sum(r['chance'] > 2 for r in W)}개는 생략. 등급 분포 {dict(Counter(r['tier'] for r in W))}")
for r in W:
    if r["chance"] <= 2 and r["pl_rule"] == "publish":
        print(f"  {r['date']} {r['name']} vod {r['vid']} [{r['kind']}/{r['cat']}] {r['start']:.0f}-{r['end']:.0f}초 len {r['len']:.0f} tier {r['tier']}({r['tier_why']}) multi {r.get('multi')} 곡 '{r['weak']}' chance {r['chance']}{' (liveOpen 날짜 추정 대응, 더 약함)' if r['pl_rule'] == 'liveOpen' else ''}")
miss = [(v["name"], v["date"], t, L, v["videoNo"]) for v in V.values() if any(r["vid"] == v["videoNo"] for r in rows) for t, L in v["playlist"]
        if not any(r["vid"] == v["videoNo"] and abs(r["len"] - L) <= 0.15 * L for r in rows)]
print(f"\n재생목록 클립 중 길이 대응 후보가 없음(미탐 또는 다른 VOD 소속) {len(miss)}개:", [f"{a} {b} '{c}' {d}초 vod {e}" for a, b, c, d, e in miss])


# 강한 정답: 사용자가 자른 클립 위치(data/refs_*.json, 녹화 시각 = VOD 시각이 맞는 방송만). 겹침 50% 이상이면 적중
STRONG = {15827672: "data/refs_마시로.json", 15761307: "data/refs_후야.json"}
print("\n강한 정답(사용자 클립 위치):")
for vid, rf in STRONG.items():
    ref = json.load(open(rf, encoding="utf8"))
    R = [r for r in rows if r["vid"] == vid]
    ov = lambda g, x: max(0, min(g["end"], x["end"]) - max(g["start"], x["start"]))
    hit = [x for x in ref if any(ov(g, x) > 0.5 * (x["end"] - x["start"]) for g in R)]
    for r in R:
        r["strong"] = any(ov(r, x) > 0.5 * (x["end"] - x["start"]) for x in ref)
    ex = [r for r in R if not r["strong"]]
    mean = lambda L, k: sum(r[k] for r in L) / max(len(L), 1)
    print(f"  vod {vid} {R[0]['name']} [{R[0]['kind']}/{R[0]['cat']}]: 정답 {len(ref)}개 중 적중 {len(hit)}개, 적중 후보 등급 {dict(Counter(r['tier'] for r in R if r['strong']))}, 정답 아닌 후보 {len(ex)}개 등급 {dict(Counter(r['tier'] for r in ex))}")
    print(f"    정답 후보 vocal 평균 {mean([r for r in R if r['strong']], 'vocal'):.2f} vs 정답 아닌 후보 {mean(ex, 'vocal'):.2f} (표본 {len(R) - len(ex)} vs {len(ex)}, 한 스트리머, 정답 아님이 곧 오탐은 아님: 사용자가 안 자른 라이브일 수 있음)")


def conflict(r):   # 클수록 시스템이 판단 못함 (사용자 라벨이 있는 후보는 제외하고 부른다)
    sc = 0
    if r.get("strong") is False and r["tier"] == "auto":                       # auto 인데 사용자가 자른 목록에 없음: 가장 아픈 충돌
        sc += 4
    if r["weak"] and r["chance"] == 1 and r["pl_rule"] == "publish" and r["tier"] == "drop" and r.get("multi") in ("watch", "idle"):   # 길이는 재생목록 곡과 1:1인데 장면이 watch
        sc += 3
    if r["weak"] and r["chance"] == 1 and r["kind"] == "game" and r["tier"] != "drop" and r.get("scene") is not None and r["scene"] < 0.03:   # 정지 화면 의심인데 길이는 1:1
        sc += 3
    if r.get("strong") is False and r["tier"] != "drop" and r.get("multi") == "live" and 125 <= r["len"] <= 340 and r["music"] >= 0.85:   # 정답처럼 보이는데 정답 목록에 없음
        sc += 2
    return sc


U = sorted((r for r in rows if conflict(r) and r["start"] >= 300 and not r["label"]), key=lambda r: -conflict(r))
cnt, keep = Counter(), []
for r in U:                                                                      # 한 방송이 목록을 다 채우지 않게 방송당 최대 3개
    if cnt[r["vid"]] < 3 and len(keep) < N:
        cnt[r["vid"]] += 1
        keep.append(r)
U = keep
print(f"\nuncertain 후보(충돌 점수 순, 최대 {N}):")
for r in U:
    print(f"  {r['date']} {r['name']} vod {r['vid']} [{r['kind']}/{r['cat']}] {r['start']:.0f}-{r['end']:.0f}초 len {r['len']:.0f} tier {r['tier']}({r['tier_why']}) multi {r.get('multi')} 의심 {r['flags']} 약한대응 {r['weak']} music {r['music']}")
