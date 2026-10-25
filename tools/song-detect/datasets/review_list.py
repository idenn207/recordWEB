"""cache/nas_summary.json -> data/nas_review_list.md (review/optional 후보 목록. 완성본은 만들지 않음)."""
import json
d = json.load(open("cache/nas_summary.json", encoding="utf8"))["broadcasts"]
t = lambda s: f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{int(s % 60):02d}"
L = ["# NAS 10월 review/optional 후보 (완성본 미제작)", "", "시각은 NAS 원본 녹화 파일 기준. 카테고리는 제목 키워드 추정. 오탐이 미탐보다 나쁘므로 auto 만 완성본으로 만들었다.", "",
     "| 방송 | 스트리머 | 카테고리 | 등급 | 시작 | 끝 | 길이(초) | 근거 |", "|---|---|---|---|---|---|---|---|"]
n = 0
for s, b in d.items():
    for c in b["cands"]:
        if c["tier"] in ("review", "optional"):
            n += 1
            L.append(f"| {s} | {b['streamer']} | {b['category']} | {c['tier']} | {t(c['start'])} | {t(c['end'])} | {c['len']:.0f} | {c['why']} |")
open("data/nas_review_list.md", "w", encoding="utf8").write("\n".join(L) + "\n")
print(n)
