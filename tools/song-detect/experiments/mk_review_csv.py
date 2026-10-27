"""사용자 판정용 csv/xlsx 생성: out/final(auto)와 out/final_review(review) 의 v4 완성본마다 한 줄. 사용: python experiments/mk_review_csv.py <출력폴더>
판정 열(L 라이브/N 아님/B 라이브지만 경계 문제)과 메모만 채우면 된다. Excel 에서 열리도록 utf-8-sig + 전체 인용."""
import csv, glob, json, os, sys
out = sys.argv[1]
os.makedirs(out, exist_ok=True)
H = ["priority", "tier", "file", "folder", "streamer", "date", "start_in_broadcast", "len_sec", "code", "likely", "tier_why",
     "self_screen", "self_start", "self_end", "self_confidence", "self_note", "prev_clip_len", "shift_start", "shift_end", "deviation", "판정(L/N/B)", "메모"]
SC = {v["clip"]: v for v in json.load(open("data/review/blind11/self_check.json", encoding="utf8")).values()}  # 자체 시청 검수(self_check_build)
PREV = {}  # 이전 규칙(v4) 클립: (방송 슬러그 뒷부분, 카드번호) -> json
for d in ("out/stale_v4/final", "out/stale_v4/final_review"):
    for p in glob.glob(f"{d}/*/*.json"):
        if not p.endswith("_ctx20.json"):
            q = json.load(open(p, encoding="utf8")); PREV[("_".join(os.path.basename(os.path.dirname(p)).split("_")[2:]), q["card_idx"])] = q
rows = []
for tier, d in (("review", "out/final_review"), ("auto", "out/final")):
    for p in sorted(glob.glob(f"{d}/*/*.json")):
        j = json.load(open(p, encoding="utf8"))
        if j.get("rule") != "v5-bounds" or not j.get("ok") or p.endswith("_ctx20.json"):
            continue
        slug = os.path.basename(os.path.dirname(p)).split("_")
        t = int(j["src_start"])
        sc = SC.get(os.path.basename(p)[:-5], {})
        pv = PREV.get(("_".join(slug[2:]), j["card_idx"]))
        ss = se = dl = dev = ""
        if pv:
            ss, se, dl = round(j["song_start"] - pv["song_start"], 2), round(j["song_end"] - pv["song_end"], 2), round(j["clip_len"] - pv["clip_len"], 2)
            # 이탈 = 곡 경계 2초 이상 이동 또는 클립 길이 3초 이상 변화(golden_gate 와 같은 기준). 승인 곡이면 '승인 이탈'.
            if abs(ss) >= 2 or abs(se) >= 2 or abs(dl) >= 3:
                dev = "승인 이탈" if tier == "auto" else "이동"
        else:
            dev = "이전 없음"
        rows.append(["", tier, j["files"]["final"], os.path.basename(os.path.dirname(p)), slug[1], slug[2], f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}", round(j["clip_len"]), j.get("code", ""), "likely" if j.get("likely") else "", (j.get("tier_why") or "").replace("\n", " "),
                     sc.get("screen", ""), sc.get("start", ""), sc.get("end", ""), sc.get("conf", ""), sc.get("reason", ""), round(pv["clip_len"], 1) if pv else "", ss, se, dev, "", ""])
# 위험 점수: 이탈 > 화면 other > 확신도 low > 시작/끝 지적(ok 아님) > mid. 점수 높은 순, 상위 10곡만 priority=1(사용자 지침: 최대 10곡)
def risk(r):
    return (r[19] in ("승인 이탈", "이동")) * 8 + (r[11] not in ("live", "")) * 6 + (r[14] == "low") * 4 + (r[12] not in ("ok", "")) * 1.5 + (r[13] not in ("ok", "")) * 1.5 + (r[14] == "mid") * 1
rows.sort(key=lambda r: -risk(r))
for i, r in enumerate(rows):
    r[0] = 1 if i < 10 and risk(r) > 0 else ""
    assert r[0] == "" or i < 10
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
print(sum(r[0] == 1 for r in rows), "priority=1;", len(rows), {t: sum(r[1] == t for r in rows) for t in ("review", "auto")})
