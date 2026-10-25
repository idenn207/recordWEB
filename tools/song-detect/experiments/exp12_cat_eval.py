"""exp12 카테고리/층별 평가 -> cache/exp12_cat_eval.json (실행: python experiments/exp12_cat_eval.py).
정답: playlist2 (이름+날짜+길이; 위치 정답 refs 가 있으면 위치).
shortcut: 같은 이름+날짜 방송이 여러 개면 후보를 합쳐 대응(방송 구분 안 함), 날짜 불일치(자정 넘김)는 무시, 곡명 키워드로 어려운 종류를 거칠게 찾음."""
import json, re, collections, sys, os
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, ".")
from category_prior import wilson, group

J = lambda f: json.load(open(f, encoding="utf8"))
S = J("cache/exp12_summary.json")
META = J("data/vod_meta.json")
PL = collections.defaultdict(list)
for e in J("data/playlist2.json")["entries"]:
    m = re.match(r"(.+?) (\d\d) (\d\d) (\d\d) (.*)", e["title"])
    if m:
        PL[(m[1], f"20{m[2]}-{m[3]}-{m[4]}")].append(dict(song=m[5], dur=e["duration"]))
REF = collections.defaultdict(list)                       # 위치 정답: (이름,날짜) -> [(start,end)]
for r in J("data/refs.json"):
    t = r["title"].split("-")
    REF[(t[0] + " " + t[1], r["date"])].append((r["start"], r["end"]))
for f, n in (("마시로", "네네코 마시로"), ("후야", "사키하네 후야")):
    for r in J(f"data/refs_{f}.json"):
        REF[(n, r["date"])].append((r["start"], r["end"]))


def hit_pos(c, s, e):                                     # 후보가 정답 구간의 절반 이상을 덮음
    return max(0, min(c["end"], e) - max(c["start"], s)) >= 0.5 * (e - s)


def hit_len(c, d):
    return abs(c["len"] - d) <= 0.15 * d


groups = collections.defaultdict(list)
for v in S:
    if v["processed"]:
        groups[(v["name"], v["date"])].append(v)
TIERS = {"any": ("auto", "review", "drop"), "auto+review": ("auto", "review"), "auto": ("auto",)}
out = {"recall": {}, "volume": {}}
for st in ("game", "song", "talk", "piano", "ALL"):
    o = {}
    for tn, tiers in TIERS.items():
        n = h = ch = pn = ph = 0
        for k, vs in groups.items():
            if st != "ALL" and vs[0]["stratum"] != st:
                continue
            cs = [c for v in vs for c in v["cands"] if c["tier"] in tiers]
            if REF.get(k):                                # 위치 정답 그룹: 위치로
                for s, e in REF[k]:
                    pn += 1
                    ph += any(hit_pos(c, s, e) for c in cs)
            else:                                         # 길이 대응 + chance(무작위 후보가 길이창에 들 확률로 기대 우연 대응 수)
                for cl in PL.get(k, []):
                    f = sum(hit_len(c, cl["dur"]) for c in cs) / max(1, len(cs))
                    n += 1
                    h += any(hit_len(c, cl["dur"]) for c in cs)
                    ch += 1 - (1 - f) ** len(cs)
        o[tn] = dict(len_n=n, len_hit=h, len_wilson=wilson(h, n), len_chance_expected=round(ch, 1), pos_n=pn, pos_hit=ph, pos_wilson=wilson(ph, pn))
    out["recall"][st] = o
for st in ("game", "song", "talk", "piano"):
    vs = [v for v in S if v["stratum"] == st and v["processed"]]
    hrs = sum(v["dur"] for v in vs) / 3600
    t = collections.Counter(c["tier"] for v in vs for c in v["cands"])
    out["volume"][st] = dict(videos=len(vs), hours=round(hrs, 1), cands=sum(t.values()), tiers=dict(t), per_hour={k: round(x / hrs, 2) for k, x in t.items()}, all_per_hour=round(sum(t.values()) / hrs, 2))


def matched(v, c):
    k = (v["name"], v["date"])
    if REF.get(k):
        return any(hit_pos(c, s, e) for s, e in REF[k])
    return any(hit_len(c, cl["dur"]) for cl in PL.get(k, []))


risk = collections.defaultdict(collections.Counter)       # (c) 층/tier 별 위험 프로필
for v in S:
    if not v["processed"]:
        continue
    k = (v["name"], v["date"])
    for c in v["cands"]:
        if c["tier"] == "drop":
            continue
        r = risk[(v["stratum"], c["tier"])]
        r["정답있는날-대응" if k in PL and matched(v, c) else ("정답있는날-미대응" if k in PL else "정답없는날")] += 1
        r["짧음<90" if c["len"] < 90 else ("긺>420" if c["len"] > 420 else "보통")] += 1
        r["scene있음" if c.get("scene") is not None else "scene없음(새채널,review전용)"] += 1
out["risk"] = {f"{a}/{b}": dict(c) for (a, b), c in sorted(risk.items())}

cat = collections.defaultdict(lambda: [0, 0, 0])          # (d) 후보 수준: 정답 있는 날 방송의 non-drop 후보 대응률
for v in S:
    if v["processed"] and (v["name"], v["date"]) in PL:
        g = cat[group(v["category"])]
        g[2] += 1
        for c in v["cands"]:
            if c["tier"] != "drop":
                g[0] += 1
                g[1] += matched(v, c)
out["cand_level"] = {g: dict(videos=x[2], nondrop=x[0], matched=x[1], rate=round(x[1] / max(1, x[0]), 3), wilson=wilson(x[1], x[0])) for g, x in cat.items()}
names = {k[0] for k in PL}
days = sorted({k[1] for k in PL})
cell = collections.defaultdict(list)                      # 방송 수준: 재생목록 날짜 창 안 방송 중 재생목록 클립이 있는 비율
for m in META:
    if m["name"] in names and days[0] <= m["start"] <= days[-1]:
        cell[(m["name"], m["start"])].append(m)
vl = collections.defaultdict(lambda: [0, 0])
for k, ms in cell.items():
    if len(ms) == 1:                                      # 같은 날 여러 방송이면 어느 방송의 클립인지 모름 -> 제외
        g = vl[group(ms[0]["category"])]
        g[0] += 1
        g[1] += k in PL
out["video_level"] = {g: dict(videos=n, with_playlist=h, rate=round(h / n, 3), wilson=wilson(h, n)) for g, (n, h) in vl.items()}
out["window"] = days[0], days[-1]

HARD = {"리듬게임": ["리듬", "디제이맥스", "뮤즈 대쉬", "헤드뱅어스", "리듬 닥터", "리듬 천국"], "OST": ["ost"], "힙합/랩": ["랩", "rap", "힙합"], "시티팝": ["시티팝", "city pop", "plastic love", "황혼의 bay city"], "연습": ["연습"], "1절": ["1절"]}
hard = []
for v in S:                                               # 방송 제목/카테고리 키워드
    hay = (v["title"] + " " + v["category"]).lower()
    for t, kws in HARD.items():
        if v["processed"] and any(w in hay for w in kws):
            hard.append(dict(type=t, via="방송제목/카테고리", video=v["videoNo"], name=v["name"], date=v["date"], title=v["title"], category=v["category"], nondrop=sum(c["tier"] != "drop" for c in v["cands"])))
for k, cls in PL.items():                                 # 재생목록 곡명 키워드 + 현재 후보로 잡혔는지
    for cl in cls:
        for t, kws in HARD.items():
            if t != "리듬게임" and any(w in cl["song"].lower() for w in kws):
                hard.append(dict(type=t, via="재생목록 곡명", name=k[0], date=k[1], song=cl["song"], dur=cl["dur"], videos=[v["videoNo"] for v in groups.get(k, [])],
                                 found_nondrop=any(hit_len(c, cl["dur"]) and c["tier"] != "drop" for v in groups.get(k, []) for c in v["cands"])))
for v in S:                                               # 게임 중 라이브: 게임 카테고리 방송의 non-drop 후보
    if v["processed"] and group(v["category"]) == "game":
        for c in v["cands"]:
            if c["tier"] != "drop":
                hard.append(dict(type="게임중", via="게임 카테고리 non-drop", video=v["videoNo"], name=v["name"], date=v["date"], category=v["category"], start=round(c["start"]), len=round(c["len"]), tier=c["tier"], scene=c.get("scene")))
out["hard"] = hard
json.dump(out, open("cache/exp12_cat_eval.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1).split('"hard"')[0])
print(collections.Counter((h["type"], h["via"]) for h in hard))
