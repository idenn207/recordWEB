"""재생목록 클립 길이와 후보 길이의 1대1 대응(탐욕, 상대 오차 작은 쌍부터, 클립 하나는 한 번만). 사용: python experiments/match12.py [tol=0.04]
같은 날짜 방송이 둘(후야 10-19)이면 두 방송 모두 같은 클립 목록을 가져 서로 같은 클립을 쓸 수 있다는 점은 무시한다.
shortcut: 길이 대응은 위치 확인이 아니다. 클립 수 대비 후보 수가 많으면 우연 대응이 늘어 정밀도가 떨어진다(아래 평가로 측정)."""
import collections, json, os, sys
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
tol = float((sys.argv[1:] or ["0.04"])[0])
R = json.load(open("cache/exp12_review/cands.json", encoding="utf8"))
V = {v["videoNo"]: v for v in json.load(open("data/vods12.json", encoding="utf8"))}


def match(cands, clips, tol):
    pairs = sorted((abs(c["len"] - k) / k, i, j) for i, c in enumerate(cands) for j, k in enumerate(clips) if abs(c["len"] - k) <= tol * k)
    ui, uj, out = set(), set(), {}
    for _, i, j in pairs:
        if i not in ui and j not in uj: ui.add(i); uj.add(j); out[i] = clips[j]
    return out


for r in R: r.pop("m1", None)
for vid, v in V.items():
    cs = [r for r in R if r["vid"] == vid and r["tier"] != "drop"]       # drop 은 대응 대상 아님(대기/같이보기)
    for i, k in match(cs, v["clips"], tol).items(): cs[i]["m1"] = k
json.dump(R, open("cache/exp12_review/cands.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
M = [r for r in R if r["tier"] != "drop" and r.get("m1")]
print("tol", tol, "대응", len(M), collections.Counter((r["tier"], r["lab"]) for r in M))
