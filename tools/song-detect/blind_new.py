"""신규 표본(data/vods10.json)의 검토용 블라인드 클립 최대 30개. blind_vod.py 와 같은 파일명/review.csv/key.json 형식 + key 에 title, collab 추가.
선택: auto 전부 -> 토아 싱크룸(다인 곡 자료) 최대 10개 -> 나머지 review 를 방송별 라운드로빈. drop(장면/오디오 게이트 탈락)은 뽑지 않는다(싱크룸 제외).
사용: python blind_new.py <segments 폴더(exp10s)> <출력 폴더(data/blind6)> [최대=30] [패딩초=20]"""
import csv, json, random, subprocess, sys
from collections import defaultdict
from pathlib import Path
from vod import url144

IN, OUT = Path(sys.argv[1]), Path(sys.argv[2])
MAX = int(sys.argv[3]) if len(sys.argv) > 3 else 30
PAD = float(sys.argv[4]) if len(sys.argv) > 4 else 20.0
SYNC = 15837908                                           # 토아 10-24 싱크룸
OUT.mkdir(parents=True, exist_ok=True)
vods = {v["videoNo"]: v for v in json.load(open("data/vods10.json", encoding="utf8"))}
hm = lambda t: f"{int(t // 3600):02d}{int(t % 3600 // 60):02d}{int(t % 60):02d}"
cand = []
for no, v in vods.items():
    f = IN / f"{no}.segments.json"
    if f.exists():
        cand += [dict(videoNo=no, name=v["name"], date=v["date"], title=v["title"], collab=v["collab"], **{k: s[k] for k in ("start", "end", "len", "tier", "tier_why")}, scene=s.get("scene"))
                 for s in json.load(open(f, encoding="utf8")) if s["tier"] in ("auto", "review") or no == SYNC]   # 싱크룸은 장면이 달라 전부 drop 이어도 타인 라이브 구분 시험 자료라 포함
rng = random.Random(6)
sel = [c for c in cand if c["tier"] == "auto"][:MAX]
sync = [c for c in cand if c["videoNo"] == SYNC and c not in sel]
rng.shuffle(sync)
sel += sync[:max(0, min(10, MAX - len(sel)))]
by = defaultdict(list)
for c in cand:
    if c not in sel:
        by[c["videoNo"]].append(c)
for v in by.values():
    rng.shuffle(v)
while len(sel) < MAX and any(by.values()):
    for k in sorted(by):
        if by[k] and len(sel) < MAX:
            sel.append(by[k].pop())
rng.shuffle(sel)
key = {}
for n, c in enumerate(sel, 1):
    bid = f"V{n:02d}"
    a, b = max(0, c["start"] - PAD), c["end"] + PAD
    name = f"{c['date'][2:].replace('-', '')}_{c['name']}_{hm(a)}-{hm(b)}__{bid}"
    ok = False
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-rw_timeout", "15000000", "-ss", str(a), "-i", url144(c["videoNo"]), "-t", str(b - a), "-vf", "scale=-2:360", "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "30", "-c:a", "aac", "-b:a", "96k", "-map_metadata", "-1", str(OUT / f"{name}.mp4")], check=True, capture_output=True, timeout=120)
        ok = True
    except Exception:
        pass
    if not ok:                                            # 영상이 멈추면 로컬 오디오만이라도
        (OUT / f"{name}.mp4").unlink(missing_ok=True)       # 타임아웃으로 잘린 mp4 조각
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-t", str(b - a), "-i", f"data/vod/{c['videoNo']}.wav", "-c:a", "aac", "-b:a", "96k", str(OUT / f"{name}(오디오만).m4a")], check=True)
    key[bid] = {**c, "clip_start": a, "clip_end": b, "video": ok}
    print(bid, "영상" if ok else "오디오만", flush=True)
(OUT / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf8")
with open(OUT / "review.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["id", "verdict(live/not_song/boundary/merged)", "memo"])
    w.writerows([[b, "", ""] for b in key])
assert len(key) <= MAX and len({k for k in key}) == len(key)
print(f"후보 {len(cand)}개 -> {len(sel)}개 선택, collab 방송 클립 {sum(k['collab'] for k in key.values())}개")
