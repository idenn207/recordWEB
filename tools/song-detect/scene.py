"""장면 게이트: KEEP 후보의 키프레임 썸네일이 '라이브 노래 장면' 기준 프레임과 비슷해야 통과 (같이 보기/영상 시청 화면을 거른다).
기준 프레임 = 확인된 라이브 구간(data/refs.json)의 썸네일. 기준이 없는 채널은 호출하지 말고 검토 대기로 보낸다.
사용: python scene.py <날짜> <채널명 일부> <기준 날짜,...> <segments.json 입력> <출력>  [thr=0.18] [refs=<json: [{date,start,end}]>]"""
import json, os, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path
import numpy as np

API = "http://192.168.0.10:5080/api/files"
W, H = 48, 27
_cf = dict(creationflags=0x4000) if os.name == "nt" else {}       # 낮은 우선순위(BELOW_NORMAL): 사용자가 같은 PC 로 다른 작업을 한다
q = lambda p: urllib.parse.quote(p, safe="")


def url_of(date, who):
    local = sorted(Path("data/vod/legacy").glob(f"{date}_{who}.mp4"))      # 내려받은 다시보기가 있으면 그것을 쓴다
    if local:
        return str(local[0])
    items = json.load(urllib.request.urlopen(f"{API}/ls?path={q('/app/chzzk')}"))["items"]
    f = next(i for i in items if date in i["name"] and who in i["name"] and not i["locked"])
    return f"{API}/download?path={q(f['path'])}"


def thumbs(url, s, e):
    """[s,e) 초의 키프레임을 48x27 회색으로. 키프레임만 디코딩하므로 1080p60 도 수 초면 된다.
    원격 파일이 응답 없이 멈추는 경우가 있어 읽기 제한(rw_timeout)과 전체 타임아웃을 두고, 실패하면 빈 배열(= 장면을 못 읽음)을 돌려준다."""
    try:
        raw = subprocess.run(["ffmpeg", "-v", "error", "-threads", "2", "-rw_timeout", "15000000", "-skip_frame", "nokey", "-ss", str(s), "-t", str(e - s), "-i", url, "-an",
                              "-vf", f"scale={W}:{H},format=gray", "-fps_mode", "vfr", "-f", "rawvideo", "-"], capture_output=True, check=True, timeout=60, **_cf).stdout
    except (subprocess.SubprocessError, OSError):
        return np.zeros((0, W * H), np.float32)
    return np.frombuffer(raw, np.uint8).reshape(-1, W * H).astype(np.float32) / 255


def dist(frames, refs):
    """프레임마다 가장 가까운 기준 프레임과의 평균 절대차 -> 중앙값."""
    return float(np.median([np.abs(refs - f).mean(1).min() for f in frames])) if len(frames) else None


def build_refs(who, dates, cap=400, refs_file="data/refs.json"):
    out = []
    for d in dates:
        u = url_of(d, who)
        for r in json.load(open(refs_file, encoding="utf8")):
            if r["date"] == d:
                out.append(thumbs(u, r["start"], r["end"]))
    R = np.concatenate(out)
    return R[np.linspace(0, len(R) - 1, min(cap, len(R))).astype(int)]


if __name__ == "__main__":
    date, who, ref_dates, seg_in, seg_out = sys.argv[1:6]
    thr = float(next((a[4:] for a in sys.argv if a.startswith("thr=")), 0.18))
    refs_file = next((a[5:] for a in sys.argv if a.startswith("refs=")), "data/refs.json")
    refs, url = build_refs(who, ref_dates.split(","), refs_file=refs_file), url_of(date, who)
    segs = json.load(open(seg_in, encoding="utf8"))
    for s in segs:
        if not s["keep"]:
            continue
        s["scene"] = d = dist(thumbs(url, s["start"], s["end"]), refs)
        if d is None or d > thr:                      # 장면을 못 읽어도 통과시키지 않는다 (오탐이 더 나쁘다)
            s["keep"], s["why"] = False, "scene"
        print(f"  {int(s['start'] // 3600)}:{int(s['start'] % 3600 // 60):02d}:{int(s['start'] % 60):02d} len={s['len']:.0f} scene={d if d is None else round(d, 3)} {'KEEP' if s['keep'] else 'drop'}", flush=True)
    json.dump(segs, open(seg_out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
