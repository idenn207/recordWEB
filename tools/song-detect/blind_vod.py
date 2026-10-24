"""다시보기 데이터셋 검토용 블라인드 클립(층화 추출). 자동 등급 전부 + 검토 대기 중 재생목록에 대응 안 된 것(위험) + 대응된 것(대조군).
영상은 144p 에서 필요한 구간만 읽는다(5MB/클립). 영상이 멈추는 방송은 로컬 오디오(wav)로 대체한다.
파일명: YYMMDD_스트리머_HHMMSS-HHMMSS__ID.mp4 (시각 = 다시보기 영상 기준, 클립 전체 범위). 사용: python blind_vod.py <segments 폴더> <출력 폴더> [패딩초=20]"""
import csv, json, random, subprocess, sys
from collections import defaultdict
from pathlib import Path
from vod import url144

IN, OUT = Path(sys.argv[1]), Path(sys.argv[2])
PAD = float(sys.argv[3]) if len(sys.argv) > 3 else 20.0
OUT.mkdir(parents=True, exist_ok=True)
vods = json.load(open("data/vods.json", encoding="utf8"))
hm = lambda t: f"{int(t // 3600):02d}{int(t % 3600 // 60):02d}{int(t % 60):02d}"

groups = defaultdict(list)
for v in vods:
    groups[(v["name"], v["date"])].append(v)
pool = {"auto": [], "review_unmatched": [], "control": []}
for (name, date), vs in groups.items():
    cand = [(v, s) for v in vs if (IN / f"{v['videoNo']}.segments.json").exists()
            for s in json.load(open(IN / f"{v['videoNo']}.segments.json", encoding="utf8")) if s["tier"] in ("auto", "review")]
    used = set()
    for c in sorted(vs[0]["clips"]):
        b = min(((abs(s["len"] - c) / c, i) for i, (_, s) in enumerate(cand) if i not in used), default=None)
        if b and b[0] <= 0.15:
            used.add(b[1])
    for i, (v, s) in enumerate(cand):
        item = dict(videoNo=v["videoNo"], name=name, date=date, **{k: s[k] for k in ("start", "end", "len", "tier", "tier_why")}, scene=s.get("scene"), matched=i in used)
        if s["tier"] == "auto":
            pool["auto"].append(item)
        elif i in used:
            pool["control"].append(item)
        else:
            pool["review_unmatched"].append(item)

rng = random.Random(11)
def pick(lst, n):                                         # 스트리머가 고르게 섞이도록 스트리머별 라운드로빈
    by = defaultdict(list)
    for x in lst:
        by[x["name"]].append(x)
    for v in by.values():
        rng.shuffle(v)
    out = []
    while len(out) < n and any(by.values()):
        for k in sorted(by):
            if by[k] and len(out) < n:
                out.append(by[k].pop())
    return out

sel = pool["auto"] + pick(pool["review_unmatched"], 14) + pick(pool["control"], 4)
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
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-t", str(b - a), "-i", f"data/vod/{c['videoNo']}.wav", "-c:a", "aac", "-b:a", "96k", str(OUT / f"{name}(오디오만).m4a")], check=True)
    key[bid] = {**c, "clip_start": a, "clip_end": b, "video": ok}
    print(bid, "영상" if ok else "오디오만", flush=True)
(OUT / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf8")
with open(OUT / "review.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["id", "verdict(live/not_song/boundary/merged)", "memo"])
    w.writerows([[b, "", ""] for b in key])
print({k: len(v) for k, v in pool.items()}, "->", len(sel), "개 선택")
