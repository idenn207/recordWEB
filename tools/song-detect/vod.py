"""치지직 다시보기의 144p 영상 주소(장면 확인과 검토용 클립 생성에 쓴다)."""
import json, re, urllib.request

UA = {"User-Agent": "Mozilla/5.0"}
_url = {}


def url144(vno):
    if vno not in _url:
        c = json.load(urllib.request.urlopen(urllib.request.Request(f"https://api.chzzk.naver.com/service/v3/videos/{vno}", headers=UA), timeout=20))["content"]
        mpd = urllib.request.urlopen(urllib.request.Request(f"https://apis.naver.com/neonplayer/vodplay/v2/playback/{c['videoId']}?key={c['inKey']}",
                                                            headers={**UA, "Accept": "application/dash+xml"}), timeout=20).read().decode()
        _url[vno] = re.search(r'<Representation id="PD_144P[^"]*".*?<BaseURL>([^<]+)</BaseURL>', mpd, re.S).group(1).replace("&amp;", "&")
    return _url[vno]
