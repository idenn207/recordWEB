"""사용자 판정용 csv/xlsx 생성: out/final(auto)와 out/final_review(review) 의 v4 완성본마다 한 줄. 사용: python experiments/mk_review_csv.py <출력폴더>
판정 열(L 라이브/N 아님/B 라이브지만 경계 문제)과 메모만 채우면 된다. Excel 에서 열리도록 utf-8-sig + 전체 인용."""
import csv, glob, json, os, sys
out = sys.argv[1]
os.makedirs(out, exist_ok=True)
H = ["tier", "file", "folder", "streamer", "date", "start_in_broadcast", "len_sec", "code", "likely", "tier_why", "판정(L/N/B)", "메모"]
rows = []
for tier, d in (("review", "out/final_review"), ("auto", "out/final")):
    for p in sorted(glob.glob(f"{d}/*/*.json")):
        j = json.load(open(p, encoding="utf8"))
        if j.get("rule") != "v5-bounds" or not j.get("ok") or p.endswith("_ctx20.json"):
            continue
        slug = os.path.basename(os.path.dirname(p)).split("_")
        t = int(j["src_start"])
        rows.append([tier, j["files"]["final"], os.path.basename(os.path.dirname(p)), slug[1], slug[2], f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}", round(j["clip_len"]), j.get("code", ""), "likely" if j.get("likely") else "", (j.get("tier_why") or "").replace("\n", " "), "", ""])
with open(f"{out}/review.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f, quoting=csv.QUOTE_ALL)
    w.writerow(H)
    w.writerows(rows)
try:
    import openpyxl
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(H)
    for r in rows: ws.append(r)
    wb.save(f"{out}/review.xlsx")
except ImportError:
    print("openpyxl 없음: xlsx 생략")
print(len(rows), {t: sum(r[0] == t for r in rows) for t in ("review", "auto")})
