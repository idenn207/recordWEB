"""다시보기 데이터셋 장면 게이트 + 라우팅 (별도 모듈). 영상은 받지 않고 144p 영상에서 필요한 구간의 키프레임만 읽는다.
기준 프레임 = 같은 채널의 '다른 날짜' 방송에서 재생목록 클립과 길이(+-15%)로 일대일 대응된 탐지 구간 (leave-one-date-out).
주의: 길이 대응은 약한 라벨이라 우연히 맞은 오탐이 기준을 오염시킬 수 있다(결과를 읽을 때 감안).
사용: python scene_dataset.py <입력 segments 폴더(exp8r)> <출력 폴더>   (파일명 <videoNo>.segments.json)"""
import json, re, sys, urllib.request
from collections import defaultdict
from pathlib import Path
import numpy as np
from scene import thumbs, dist
from route import tier
from vod import url144

UA = {"User-Agent": "Mozilla/5.0"}
IN, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
vods = json.load(open("data/vods.json", encoding="utf8"))
_bad = set()


def th(vno, s, e):
    """144p 영상이 응답하지 않는 방송이 있어(CDN 정지), 한 번 실패한 방송은 이후 구간을 건너뛴다(= 장면 못 읽음 -> 검토 대기)."""
    if vno in _bad:
        return np.zeros((0, 1))
    f = thumbs(url144(vno), s, e)
    if not len(f):
        _bad.add(vno)
        print(f"  방송 {vno} 144p 읽기 실패 -> 이후 건너뜀", flush=True)
    return f


segs = {}
for v in vods:
    f = IN / f"{v['videoNo']}.segments.json"
    if f.exists():
        segs[v["videoNo"]] = [s for s in json.load(open(f, encoding="utf8")) if s["keep"]]

# 날짜 그룹(스트리머, 날짜)마다 클립 길이와 탐지 길이를 일대일 매칭
by_group = defaultdict(list)
for v in vods:
    by_group[(v["name"], v["date"])].append(v)
matched = defaultdict(list)                              # (name, date) -> [(videoNo, seg)]
for key, vs in by_group.items():
    pool = [(v["videoNo"], s) for v in vs for s in segs.get(v["videoNo"], [])]
    used = set()
    for c in sorted(vs[0]["clips"]):
        b = min(((abs(s["len"] - c) / c, i) for i, (_, s) in enumerate(pool) if i not in used), default=None)
        if b and b[0] <= 0.15:
            used.add(b[1])
            matched[key].append(pool[b[1]])

refs_cache = {}
for key, vs in by_group.items():
    name, date = key
    other = [m for k, ms in matched.items() if k[0] == name and k[1] != date for m in ms]
    R = []
    for vno, s in other:
        f = th(vno, s["start"], s["end"])
        if len(f):
            R.append(f[np.linspace(0, len(f) - 1, min(60, len(f))).astype(int)])
    refs = np.concatenate(R) if R else None
    for v in vs:
        out = []
        for s in segs.get(v["videoNo"], []):
            s = dict(s)
            if refs is not None:
                s["scene"] = dist(th(v["videoNo"], s["start"], s["end"]), refs)
            s["tier"], s["tier_why"] = tier(s, refs is not None)
            out.append(s)
        json.dump(out, open(OUT / f"{v['videoNo']}.segments.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print(f"{date} {name} 기준 {'없음(새 채널/단일 날짜)' if refs is None else str(len(refs)) + '프레임'} -> 방송 {len(vs)}개 처리", flush=True)
