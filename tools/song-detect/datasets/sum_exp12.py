"""data/vods12.json 방송별로 out/<videoNo>/cards 를 모아 cache/exp12_summary.json 으로 요약한다. 사용: python datasets/sum_exp12.py"""
import glob, json
from collections import Counter

out = []
for v in json.load(open("data/vods12.json", encoding="utf8")):
    cs = [json.load(open(p, encoding="utf8")) for p in sorted(glob.glob(f"out/{v['videoNo']}/cards/*.json"))]
    out.append(dict(videoNo=v["videoNo"], name=v["name"], date=v["start"], stratum=v["stratum"], category=v["category"], title=v["title"], dur=v["dur"],
                    processed=bool(cs) or glob.glob(f"out/{v['videoNo']}/3_final.json") != [], tiers=dict(Counter(c["tier"] for c in cs)),
                    cands=[{k: c[k] for k in ("start", "end", "len", "tier", "tier_why", "scene", "multi")} for c in cs]))
json.dump(out, open("cache/exp12_summary.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
T = Counter(t for o in out for t, n in o["tiers"].items() for _ in range(n))
print(sum(o["processed"] for o in out), "방송 처리", sum(T.values()), "후보", dict(T))
