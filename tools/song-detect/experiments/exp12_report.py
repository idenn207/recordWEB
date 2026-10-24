"""exp12_rap 결과 집계 (도커 불필요): python experiments/exp12_report.py cache/exp12_rap/c35
하한(min_len_s)별 KEEP 수, 90초 기준선에 없는 '새' 구간의 분포, 알려진 정/부정 라벨과의 겹침, 노이즈 유형."""
import json, sys
from pathlib import Path
import numpy as np

R = Path(sys.argv[1])
DUP = {"2026-10-17_랑", "2026-10-17_토아", "2026-10-18", "2026-10-18_어비스", "2026-10-19_후야", "2026-10-20", "2026-10-23", "2026-10-23_마시로"}  # vod 와 같은 방송(HANDOFF 12번)
stems = sorted(f.name[:-14] for f in (R / "90").glob("*.segments.json") if f.name[:-14] not in DUP)
L = lambda p: json.loads(Path(p).read_text(encoding="utf8"))
ov = lambda a, b: min(a[1], b[1]) - max(a[0], b[0])

live, neg = {}, {}                                    # 방송 -> [(start,end)]
for b, lab in L("data/labels.json").items():
    for v, k in L(f"data/review/{b}/key.json").items():
        if v in lab:
            (live if lab[v]["live"] else neg).setdefault(str(k["videoNo"]), []).append((k["clip_start"], k["clip_end"]))
for f, vid in (("refs_마시로", "15827672"), ("refs_후야", "15761307")):
    live.setdefault(vid, []).extend((r["start"], r["end"]) for r in L(f"data/{f}.json"))
for k in L("data/known_negatives.json"):
    neg.setdefault(str(k["videoNo"]), []).append((k["start"], k["end"]))
hours = sum(len(np.load(f"cache/detect/{s}.scores.npy")) for s in stems) * 0.5 / 3600
print(f"방송 {len(stems)}개(vod 와 중복되는 legacy 8개 제외), {hours:.0f}시간")

keeps = {m: {s: [g for g in L(R / m / f"{s}.segments.json") if g["keep"]] for s in stems} for m in sorted((p.name for p in R.iterdir() if p.is_dir()), key=float, reverse=True)}
base = keeps["90"]
print("floor  KEEP  new  new/h | new: len중앙 vocal중앙 cover중앙 speech중앙 | start<300 부정겹침(labels+known_neg) 라벨정(조각) 기준선인접 | 노이즈의심(speech>=.08 or cover<.7 or vocal<.4)")
for m, ks in keeps.items():
    new = []
    for s in stems:
        for g in ks[s]:
            if all(ov((g["start"], g["end"]), (b["start"], b["end"])) <= 0 for b in base[s]):
                new.append((s, g))
    if not new:
        print(f"{m:>5} {sum(map(len, ks.values())):5d}    0"); continue
    q = lambda k: np.median([g[k] for _, g in new])
    n300 = sum(g["start"] < 300 for _, g in new)
    nneg = sum(any(ov((g["start"], g["end"]), x) > 0 for x in neg.get(s, [])) for s, g in new)
    nlive = sum(any(ov((g["start"], g["end"]), x) > 0 for x in live.get(s, [])) for s, g in new)
    adj = sum(any(min(abs(g["start"] - b["end"]), abs(b["start"] - g["end"])) <= 20 for b in base[s]) for s, g in new)
    noisy = sum(g["speech"] >= .08 or g["cover"] < .7 or g["vocal"] < .4 for _, g in new)
    print(f"{m:>5} {sum(map(len, ks.values())):5d} {len(new):4d} {len(new)/hours:5.2f} | {q('len'):.0f}s {q('vocal'):.2f} {q('cover'):.2f} {q('speech'):.3f} | {n300} {nneg} {nlive} {adj} | {noisy}")
json.dump({m: [(s, round(g["start"]), round(g["len"]), g["vocal"], g["cover"], g["speech"], g["music"]) for s in stems for g in keeps[m][s] if all(ov((g["start"], g["end"]), (b["start"], b["end"])) <= 0 for b in base[s])] for m in keeps if m != "90"},
          open(R / "new_segments.json", "w", encoding="utf8"), ensure_ascii=False)
