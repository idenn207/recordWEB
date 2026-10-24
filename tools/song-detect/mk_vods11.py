"""어려운 표본 메타(data/vods11.json): data/vod 의 받은 방송(+인자로 준 videoNo)의 치지직 제목/카테고리를 받아 game/song/talk 로 분류하고 재생목록 클립(곡명,길이)을 붙인다.
kind: 카테고리 categoryType=GAME 이면 game, 제목/카테고리가 노래/음악이면 song, 그 외 talk. 카테고리는 방송 '마지막' 값이라 중간에 바뀐 구간은 모른다.
사용: python mk_vods11.py [videoNo...]"""
import json, re, sys, time, urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0"}
CH = {x["channel"]: x["name"] for x in json.load(open("data/vods.json", encoding="utf8"))}
PL = {}   # (이름,날짜) -> [(곡명,길이)]
for e in json.load(open("data/playlist2.json", encoding="utf8"))["entries"]:
    m = re.match(r"^(.+?) (\d\d) (\d\d) (\d\d) (.+)$", e["title"])
    if m:
        PL.setdefault((m.group(1), "20%s-%s-%s" % m.group(2, 3, 4)), []).append((m.group(5), int(e["duration"])))


def kind(c):
    if c.get("categoryType") == "GAME":
        return "game"
    return "song" if re.search(r"노래|음악|singing", c.get("videoCategoryValue") or "", re.I) or re.search(r"싱크룸|노래방", c.get("videoTitle") or "") else "talk"


def meta(vid):
    for _ in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(f"https://api.chzzk.naver.com/service/v3/videos/{vid}", headers=UA), timeout=20))["content"]
        except Exception:
            time.sleep(2)
    raise RuntimeError(vid)


if __name__ == "__main__":
    ids = sorted({int(p.stem) for p in Path("data/vod").glob("*.wav")} | {int(a) for a in sys.argv[1:]})
    out = []
    for vid in ids:
        c = meta(vid)
        nm = CH.get(c["channel"]["channelId"]) or c["channel"]["channelName"]
        d, rule = c["publishDate"][:10], "publish"
        if (nm, d) not in PL and (nm, (c.get("liveOpenDate") or d)[:10]) in PL:   # 재생목록 날짜가 시작일/업로드일 어느 쪽인지 불명 -> 둘 다 시도
            d, rule = c["liveOpenDate"][:10], "liveOpen"   # 방송이 자정을 넘긴 경우의 추정 대응이라 더 약함
        out.append(dict(name=nm, date=d, videoNo=vid, title=c["videoTitle"] or "", dur=c["duration"], categoryType=c.get("categoryType"),
                        category=c.get("videoCategoryValue"), kind=kind(c), playlist=PL.get((nm, d), []), pl_rule=rule))
        print(d, nm, vid, round(c["duration"] / 3600, 1), out[-1]["kind"], out[-1]["category"], "|", out[-1]["title"][:30], "|", [t for t, _ in out[-1]["playlist"]][:4], flush=True)
    json.dump(out, open("data/vods11.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
