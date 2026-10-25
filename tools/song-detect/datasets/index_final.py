"""out/final/ 점검 + INDEX.md. 점검: 0바이트, 곡 길이 125~340초, 컷 오차, 무음(내부 3초 이상)/클리핑(max_volume>=-0.1dB), 같은 스트리머/날짜에서 겹치는 구간(중복 녹화)."""
import json, re, subprocess, sys
from collections import defaultdict
from pathlib import Path
F = Path("out/final")
rows, issues = [], []
for js in sorted(F.glob("*/*.json")):
    if js.name.endswith("_ctx20.json"):
        continue
    m = json.loads(js.read_text(encoding="utf8"))
    d = js.parent
    mp4, ctx = d / m["files"]["final"], d / m["files"]["ctx20"]
    k, tag = m["check"], f"{d.name}/{mp4.stem}"
    for p in (mp4, ctx):
        if not p.exists() or p.stat().st_size == 0:
            issues.append((tag, f"0바이트/없음 {p.name}"))
    if not m["ok"]:
        issues.append((tag, f"점검 실패 {k}"))
    if not 125 <= m["song_len"] <= 340:
        issues.append((tag, f"곡 길이 {m['song_len']:.0f}s 범위 밖"))
    for e in ("start_err", "end_err"):
        if abs(k.get(e, 0)) > 0.1:
            issues.append((tag, f"{e} {k[e]:+.3f}"))
    r = subprocess.run(["ffmpeg", "-nostats", "-i", str(mp4), "-af", "volumedetect,silencedetect=n=-45dB:d=3", "-vn", "-f", "null", "-"], capture_output=True, text=True).stderr
    mx = float(re.search(r"max_volume: (-?[\d.]+) dB", r)[1])
    sil = re.findall(r"silence_duration: ([\d.]+)", r)
    if mx >= -0.1:
        issues.append((tag, f"클리핑 의심 max {mx}dB"))
    if sil:
        issues.append((tag, f"무음 3초 이상 {sil}"))
    rows.append(dict(tag=tag, who=d.name.split("_")[1], date=d.name[:6], slug=d.name.split("_", 2)[2], s=m["src_start"], e=m["src_end"], len=m["song_len"], path=str(mp4), mb=mp4.stat().st_size / 1e6,
                     tier=m["tier"], end_db=k.get("end_rel_db"), start_db=k.get("start_rel_db")))
by = defaultdict(list)
for r in rows:
    by[r["who"], r["date"]].append(r)
for g in by.values():            # 중복 녹화: 다른 녹화(slug)끼리 길이가 3초 안이고 곡 길이만 같은 경우를 의심(시각은 녹화마다 다름)
    for i, a in enumerate(g):
        for b in g[i + 1:]:
            if a["slug"] != b["slug"] and abs(a["len"] - b["len"]) < 3:
                issues.append((a["tag"], f"중복 의심 {b['tag']}"))
L = ["# 완성본 라이브 클립 INDEX (NAS 10월, auto 등급만)", "", f"곡 {len(rows)}개, 총 {sum(r['len'] for r in rows)/60:.1f}분, {sum(r['mb'] for r in rows)/1000:.2f}GB (ctx20 제외). 파일명의 시각은 NAS 원본 녹화 안의 위치.", ""]
for w in sorted({r["who"] for r in rows}):
    g = [r for r in rows if r["who"] == w]
    L += [f"## {w}: {len(g)}곡, {sum(r['len'] for r in g)/60:.1f}분", "", "| 날짜 | 원본 구간 | 길이 | 시작/끝 음량(곡 중앙값 대비 dB) | 파일 |", "|---|---|---|---|---|"]
    for r in sorted(g, key=lambda r: (r["date"], r["slug"], r["s"])):
        L.append(f"| {r['date']} | {int(r['s']//3600)}:{int(r['s']%3600//60):02d}:{int(r['s']%60):02d}-{int(r['e']//3600)}:{int(r['e']%3600//60):02d}:{int(r['e']%60):02d} | {r['len']:.0f}s | {r['start_db']:.0f} / {r['end_db']:.0f} | `{r['path']}` |")
    L.append("")
L += ["## 점검에서 걸린 항목", ""] + ([f"- {t}: {w}" for t, w in issues] or ["- 없음"])
Path(F / "INDEX.md").write_text("\n".join(L) + "\n", encoding="utf8")
print(len(rows), "곡", len(issues), "건 이슈")
for t, w in issues:
    print(" ", t, w)
