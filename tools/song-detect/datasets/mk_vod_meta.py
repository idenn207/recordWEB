"""data/vod_meta.json: NAS 등록 치지직 스트리머 전원의 다시보기 전체 목록 + data/vod 에 받은 방송의 메타(카테고리 포함).
항목: name, channel, videoNo, title, dur, publish(업로드 KST), start(추정 시작일=업로드-길이), categoryType, category(videoCategoryValue), have(data/vod 에 wav 있음), clips(재생목록 클립 길이들).
shortcut: 목록 API 에 liveOpenDate 가 없어 시작일을 업로드-길이로 추정(자정 근처 방송은 하루 오차), 정확히 필요하면 v3/videos 로 보강.
사용: python datasets/mk_vod_meta.py"""
import json, re, sys, time, urllib.request
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
UA = {"User-Agent": "Mozilla/5.0"}
KST = timezone(timedelta(hours=9))


def get(u):
    for _ in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20))
        except Exception:
            time.sleep(2)
    raise RuntimeError(u)


PL = {}
for e in json.load(open("data/playlist2.json", encoding="utf8"))["entries"]:
    m = re.match(r"^(.+?) (\d\d) (\d\d) (\d\d) (.+)$", e["title"])
    if m:
        PL.setdefault((m.group(1), "20%s-%s-%s" % m.group(2, 3, 4)), []).append(int(e["duration"]))
have = {int(p.stem) for p in Path("data/vod").glob("*.wav")}


def row(v, name):
    pub = datetime.fromtimestamp(v["publishDateAt"] / 1000, KST)
    start = pub - timedelta(seconds=v["duration"])
    r = dict(name=name, channel=v["channel"]["channelId"], videoNo=v["videoNo"], title=(v.get("videoTitle") or "").strip(), dur=v["duration"],
             publish=pub.strftime("%Y-%m-%d %H:%M"), start=start.strftime("%Y-%m-%d"), categoryType=v.get("categoryType"),
             category=v.get("videoCategoryValue"), have=v["videoNo"] in have)
    r["clips"] = sorted(PL.get((name, r["start"])) or PL.get((name, pub.strftime("%Y-%m-%d"))) or [])
    return r


chs = [c for c in get("http://192.168.0.10:5080/api/channels") if c["platform"] == "chzzk" and c["name"] != "강지"]
out = {}
for c in chs:
    for page in range(40):
        d = get(f"https://api.chzzk.naver.com/service/v1/channels/{c['id']}/videos?sortType=LATEST&pagingType=PAGE&page={page}&size=50")["content"]
        for v in d["data"]:
            if v.get("videoType") == "REPLAY":
                out[v["videoNo"]] = row(v, c["name"])
        if page + 1 >= d["totalPages"]:
            break
    print(c["name"], sum(1 for r in out.values() if r["name"] == c["name"]), flush=True)
for vn in sorted(have - set(out)):                      # 목록에서 빠진(오래된/삭제) 받은 방송은 v3 로
    try:
        c = get(f"https://api.chzzk.naver.com/service/v3/videos/{vn}")["content"]
        out[vn] = row(c, c["channel"]["channelName"])
    except Exception as e:
        print("v3 실패", vn, e)
missing = sorted(have - set(out))
print("목록에 없는 받은 방송:", missing)
json.dump(sorted(out.values(), key=lambda r: (r["name"], r["publish"])), open("data/vod_meta.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
print(len(out), "개 저장")
