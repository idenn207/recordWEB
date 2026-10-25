"""data/vods12.json(표본 선정)과 data/vod_strata.txt(층별 요약). 입력: data/vod_meta.json (datasets/mk_vod_meta.py).
층: piano(히나 등 음악/노래 카테고리+제목에 피아노류) / song(음악/노래 카테고리, 또는 제목에 노래방·싱크룸) / game(카테고리 GAME) / talk / other.
순서: 재생목록 클립이 있는 방송 먼저(받은 것 우선) -> 층별 정원까지 (받은 것 우선, 스트리머 라운드로빈, 최근순). 합계 300시간 상한, 단건 10시간 초과 제외.
새로 받을 방송은 재생(401 등) 가능한지 mpd 까지 확인해 불가면 건너뛴다.
shortcut: 층 분류는 카테고리(방송 마지막 값)와 제목 키워드뿐 - 중간에 바뀐 구간은 모른다.
사용: python datasets/mk_vods12.py"""
import collections, json, re, sys, urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0"}
CAP_H, CLIP_H, MAX_H, MIN_H = 300, 160, 10, 0.7
QUOTA = dict(piano=12, song=18, game=18, talk=14, other=3)
PIANO = re.compile(r"피아노|피아누|연주|piano|건반", re.I)


def stratum(r):
    c, t = r["category"] or "", r["title"]
    if c == "음악/노래":
        return "piano" if PIANO.search(t) else "song"
    if r["categoryType"] == "GAME":
        return "game"
    if c == "talk":
        return "song" if re.search(r"노래방|싱크룸", t) else "talk"
    return "other"


def playable(vn):
    """v3 + 재생 mpd 에 오디오 전용 또는 144p Representation 이 있으면 True (401 인증 필요 방송은 False)."""
    try:
        c = json.load(urllib.request.urlopen(urllib.request.Request(f"https://api.chzzk.naver.com/service/v3/videos/{vn}", headers=UA), timeout=20))["content"]
        mpd = urllib.request.urlopen(urllib.request.Request(f"https://apis.naver.com/neonplayer/vodplay/v2/playback/{c['videoId']}?key={c['inKey']}",
                                                            headers={**UA, "Accept": "application/dash+xml"}), timeout=20).read().decode()
        return 'mimeType="audio/mp4"' in mpd or "PD_144P" in mpd    # 오디오 전용 또는 144p 대체(fetch_vod.py)
    except Exception:
        return False


def pick():
    meta = json.load(open("data/vod_meta.json", encoding="utf8"))
    pool = [{**r, "stratum": stratum(r)} for r in meta if MIN_H * 3600 <= r["dur"] <= MAX_H * 3600]
    sel, hours, skipped = [], 0.0, []

    def take(r, why):
        nonlocal hours
        h = r["dur"] / 3600
        if hours + h > CAP_H or any(s["videoNo"] == r["videoNo"] for s in sel):
            return False
        if not r["have"] and not playable(r["videoNo"]):
            skipped.append(r["videoNo"])
            return False
        sel.append({**r, "reason": why + ("; 이미 받음" if r["have"] else "; 새로 받음")})
        hours += h
        return True

    # 클립이 많은 방송부터(시간당 정답 밀도), 클립 단계는 CLIP_H 까지만 써서 나머지 층에 시간을 남긴다
    for r in sorted((r for r in pool if r["clips"]), key=lambda r: -len(r["clips"]) / r["dur"]):
        if hours + r["dur"] / 3600 <= CLIP_H:
            take(r, f"재생목록 클립 {len(r['clips'])}곡 날짜 일치")
    for st, q in QUOTA.items():
        have_n = sum(s["stratum"] == st for s in sel)
        cand = [r for r in pool if r["stratum"] == st and not r["clips"] and r["dur"] <= 8 * 3600]
        by = collections.defaultdict(list)                      # 스트리머 라운드로빈: 받은 것 우선, 최근순
        for r in sorted(cand, key=lambda r: r["start"], reverse=True):
            by[r["name"]].append(r)
        for k in by:
            by[k].sort(key=lambda r: not r["have"])           # 안정 정렬: 받은 것 먼저, 그 안에서 최근순
        order = []
        while any(by.values()):
            for k in sorted(by):
                if by[k]:
                    order.append(by[k].pop(0))
        for r in order:
            if have_n >= q:
                break
            have_n += take(r, f"{st} 층 {r['category'] or '?'}")
    return sel, hours, skipped


def selftest():
    r = lambda c, t, ct="ETC": dict(category=c, title=t, categoryType=ct)
    assert stratum(r("음악/노래", "피아노 치는 방송")) == "piano" and stratum(r("음악/노래", "노래방")) == "song"
    assert stratum(r("talk", "자기전에 노래방!")) == "song" and stratum(r("talk", "잡담")) == "talk"
    assert stratum(r("마인크래프트", "x", "GAME")) == "game" and stratum(r("", "x", None)) == "other"


if __name__ == "__main__":
    selftest()
    sel, hours, skipped = pick()
    sel.sort(key=lambda r: (r["stratum"], r["name"], r["start"]))
    json.dump(sel, open("data/vods12.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
    L = [f"선정 {len(sel)}개, 총 {hours:.1f}시간, 새로 받음 {sum(not s['have'] for s in sel)}개 {sum(s['dur'] for s in sel if not s['have'])/3600:.1f}시간 (재생불가로 건너뜀 {skipped})", ""]
    for st in QUOTA:
        g = [s for s in sel if s["stratum"] == st]
        L.append(f"[{st}] {len(g)}개 {sum(s['dur'] for s in g)/3600:.1f}h, 받음 {sum(s['have'] for s in g)}, 클립있음 {sum(bool(s['clips']) for s in g)}")
        L.append("  카테고리: " + ", ".join(f"{k} {v}" for k, v in collections.Counter(s["category"] or "?" for s in g).most_common()))
        L.append("  스트리머: " + ", ".join(f"{k} {v}" for k, v in collections.Counter(s["name"] for s in g).most_common()))
    L += ["", "videoNo 층 스트리머 시작일 시간 카테고리 클립 받음 제목"]
    L += [f"{s['videoNo']} {s['stratum']} {s['name']} {s['start']} {s['dur']/3600:.1f}h {s['category']} {len(s['clips'])} {int(s['have'])} {s['title'][:30]}" for s in sel]
    open("data/vod_strata.txt", "w", encoding="utf8").write("\n".join(L) + "\n")
    print("\n".join(L[:20]))
