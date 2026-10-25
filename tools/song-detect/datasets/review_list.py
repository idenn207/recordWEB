"""cache/nas_summary.json -> data/nas_review_list.md (review/optional 후보 목록. 완성본은 만들지 않음)."""
import json
d = json.load(open("cache/nas_summary.json", encoding="utf8"))["broadcasts"]
t = lambda s: f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{int(s % 60):02d}"
L = ["# NAS 10월 review/optional 후보 (완성본은 out/final_review, out/final_optional 에 사람이 듣고 판단하도록 전부 제작)", "", "시각은 NAS 원본 녹화 파일 기준. 카테고리는 제목 키워드 추정. auto 만 정식 완성본이고 review/optional 은 미검증이다. 유력 = likely 조건(다중 참조 live, 125~340초, 몰림 없음) 통과, 참고용 표시.", "",
     "| 방송 | 스트리머 | 카테고리 | 등급 | 유력 | 시작 | 끝 | 길이(초) | 근거 |", "|---|---|---|---|---|---|---|---|---|"]
n = 0
for s, b in d.items():
    for c in b["cands"]:
        if c["tier"] in ("review", "optional"):
            n += 1
            L.append(f"| {s} | {b['streamer']} | {b['category']} | {c['tier']} | {'likely' if c.get('likely') else ''} | {t(c['start'])} | {t(c['end'])} | {c['len']:.0f} | {c['why']} |")
open("data/nas_review_list.md", "w", encoding="utf8").write("\n".join(L) + "\n")
print(n)
