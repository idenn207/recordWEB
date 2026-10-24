"""신규 표본 메타(data/vods10.json) 생성: 치지직 v3/videos/<no> 의 제목/카테고리를 받아 합방 키워드((w., 같이, 합방)가 있으면 collab=true. 사용: python mk_vods10.py <videoNo>..."""
import json, sys, time, urllib.request

UA = {"User-Agent": "Mozilla/5.0"}
CH = {n: c["channel"] for n, c in {x["name"]: x for x in json.load(open("data/vods.json", encoding="utf8"))}.items()}
CH_BY_ID = {}
out = []
for vid in sys.argv[1:]:
    for _ in range(4):
        try:
            c = json.load(urllib.request.urlopen(urllib.request.Request(f"https://api.chzzk.naver.com/service/v3/videos/{vid}", headers=UA), timeout=20))["content"]
            break
        except Exception:
            time.sleep(2)
    nm = next(n for n, ch in CH.items() if ch == c["channel"]["channelId"])
    t = c["videoTitle"] or ""
    out.append(dict(name=nm, channel=c["channel"]["channelId"], date=(c.get("liveOpenDate") or c["publishDate"])[:10], videoNo=int(vid), title=t, dur=c["duration"],
                    clips=[], category=c.get("videoCategoryValue"), collab=any(k in t for k in ("(w.", "같이", "합방"))))
    print(out[-1]["name"], out[-1]["date"], vid, round(c["duration"] / 3600, 1), out[-1]["category"], out[-1]["collab"], t[:40])
json.dump(out, open("data/vods10.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
assert all(v["name"] for v in out)
