"""exp12 후보(out/<id>/cards)에 정답 근거를 붙여 cache/exp12_review/cands.json 으로 쓴다. 사용: python experiments/review12.py
근거: 재생목록 길이 대응(같은 날짜 클립 길이 +-8%), 위치 정답(refs_마시로/후야, blind5/6 사용자 라벨, blind7·known_negatives). 라벨 없으면 unk.
shortcut: 길이 대응은 위치 확인이 아니라 약한 근거, 위치 정답은 6개 방송 분량뿐."""
import glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
J = lambda p: json.load(open(p, encoding="utf8"))
V = {v["videoNo"]: v for v in J("data/vods12.json")}
pos, neg = [], []                                  # (videoNo, start, end)
for r in J("data/refs_마시로.json"): pos.append((15827672, r["start"], r["end"]))
for r in J("data/refs_후야.json"): pos.append((15761307, r["start"], r["end"]))
L = J("data/labels.json")
for s in ("blind5", "blind6"):
    for k, v in J(f"data/review/{s}/key.json").items():
        (pos if L[s][k]["live"] else neg).append((v["videoNo"], v["start"], v["end"]))
for k in J("data/known_negatives.json"): neg.append((k["videoNo"], k["start"], k["end"]))
neg += [(15827672, 14714, 14822)]                   # blind7 B2 는 사용자가 라이브라 답함 -> 넣지 않음(아래에서 제거)
neg.pop()
pos += [(15831370, 1190 - 5, 1190 + 190), (15827672, 14393, 14714), (15827672, 14714, 14822), (15827672, 15549, 15549 + 229), (15827672, 16661, 16661 + 234), (15827672, 16065, 16163)]   # blind7 사용자 라이브 답
neg += [(15831370, 411, 411 + 200), (15831370, 811, 811 + 200)]                                           # blind7 D1 D2


def lab(vid, s, e):
    for name, S in (("pos", pos), ("neg", neg)):
        for v, a, b in S:
            if v == vid and min(e, b) - max(s, a) >= 0.5 * min(e - s, b - a): return name
    return "unk"


def pl(vid, ln):
    cl = V[vid]["clips"]
    return next((c for c in cl if abs(ln - c) <= 0.08 * c), None)


rows = []
for vid in V:
    for p in sorted(glob.glob(f"out/{vid}/cards/*.json")):
        c = J(p)
        rows.append(dict(vid=vid, name=V[vid]["name"], date=V[vid]["start"], strat=V[vid]["stratum"], cat=V[vid]["category"], dur=V[vid]["dur"], nclips=len(V[vid]["clips"]),
                         s=c["start"], e=c["end"], len=c["len"], tier=c["tier"], why=c["tier_why"], scene=c["scene"], multi=c["multi"], **c["signals"], plm=pl(vid, c["len"]), lab=lab(vid, c["start"], c["end"])))
json.dump(rows, open("cache/exp12_review/cands.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
print(len(rows))
