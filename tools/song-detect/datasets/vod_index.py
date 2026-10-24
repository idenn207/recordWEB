"""NAS 에 등록된 치지직 스트리머의 다시보기 목록을 모아 라이브 클립 재생목록(data/playlist2.json)의 (스트리머, 날짜)와 맞춘다.
결과: data/vods.json = [{name, channel, date, videoNo, title, dur, clips:[클립 길이(초)...]}]. 사용: python vod_index.py"""
import json, re, urllib.request
from concurrent.futures import ThreadPoolExecutor

UA = {"User-Agent": "Mozilla/5.0"}
get = lambda u: json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20))
chs = [c for c in get("http://192.168.0.10:5080/api/channels") if c["platform"] == "chzzk"]
clips = {}
for e in json.load(open("data/playlist2.json", encoding="utf8"))["entries"]:
    m = re.match(r"^(.+?) (\d\d) (\d\d) (\d\d) (.+)$", e["title"])
    if m:
        clips.setdefault((m.group(1), "20%s-%s-%s" % m.group(2, 3, 4)), []).append(int(e["duration"]))


def videos(c):
    out = []
    for page in range(3):                                # 최근 ~150개
        try:
            d = get(f"https://api.chzzk.naver.com/service/v1/channels/{c['id']}/videos?sortType=LATEST&pagingType=PAGE&page={page}&size=50")["content"]["data"]
        except Exception:
            break
        out += d
        if len(d) < 50:
            break
    return [dict(name=c["name"], channel=c["id"], date=(v.get("liveOpenDate") or v["publishDate"])[:10], videoNo=v["videoNo"],
                 title=v["videoTitle"], dur=v["duration"]) for v in out]


with ThreadPoolExecutor(8) as ex:
    allv = [v for r in ex.map(videos, chs) for v in r]
res = []
for v in allv:
    k = (v["name"], v["date"])
    if k in clips:
        res.append({**v, "clips": sorted(clips[k])})
json.dump(res, open("data/vods.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
print(f"등록 스트리머 {len(chs)}명, 다시보기 {len(allv)}개 조회, 재생목록과 맞는 (스트리머,날짜) 방송 {len(res)}개 / 재생목록 조합 {len(clips)}개")
for v in sorted(res, key=lambda v: (v["date"], v["name"])):
    print(f"  {v['date']} {v['name']:8} {v['dur']/3600:5.2f}h 클립 {len(v['clips']):2}곡  vod {v['videoNo']}  {v['title'][:28]}")
