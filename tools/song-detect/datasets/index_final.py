"""완성본 점검 + out/final/INDEX.md (auto=out/final, review=out/final_review, optional=out/final_optional 를 한 문서에 등급별로 정리).
점검: 0바이트, (auto 만) 곡 길이 125~340초, 컷 오차, 무음(내부 3초 이상)/클리핑(max_volume>=-0.1dB), 같은 스트리머/날짜 겹침(중복 녹화), 현재 등급 재판정.
현재 규칙(json.rule == make_final.RULE)으로 만든 것만 싣고, 이전 규칙 파일은 목록만 낸다(삭제 안 함). review 는 방송(날짜, 슬러그) 시간순.
사용: python datasets/index_final.py"""
import json, re, subprocess, sys
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from make_final import RULE
DIRS = [("auto", Path("out/final")), ("review", Path("out/final_review")), ("optional", Path("out/final_optional"))]
rows, issues, old = [], [], []
t3 = lambda s: f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{int(s % 60):02d}"
for tier, F in DIRS:
    for js in sorted(F.glob("*/*.json")):
        if js.name.endswith("_ctx20.json"):
            continue
        m = json.loads(js.read_text(encoding="utf8"))
        d = js.parent
        mp4, ctx = d / m["files"]["final"], d / m["files"]["ctx20"] if m["files"]["ctx20"] else None
        tag = f"{d.name}/{mp4.stem}"
        if m.get("rule") != RULE:
            old.append(str(mp4))
            continue
        k = m["check"]
        for p in (mp4, ctx):
            if p is not None and (not p.exists() or p.stat().st_size == 0):
                issues.append((tag, f"0바이트/없음 {p.name}"))
        if not m["ok"]:
            issues.append((tag, f"점검 실패 {k}"))
        if tier == "auto" and not 125 <= m["song_len"] <= 340:
            issues.append((tag, f"곡 길이 {m['song_len']:.0f}s 범위 밖"))
        for e in ("start_err", "end_err"):
            if abs(k.get(e, 0)) > 0.1:
                issues.append((tag, f"{e} {k[e]:+.3f}"))
        slug = d.name.split("_", 2)[2]
        cur = [json.load(open(c, encoding="utf8")) for c in Path(f"out/{slug}/cards").glob("*.json")]          # 현재 등급(재판정으로 바뀐 완성본 표시)
        now = next((c for c in cur if abs(c["start"] - m["card_start"]) < 1), None)
        if now is None or now["tier"] != tier:
            issues.append((tag, f"현재 등급 {now['tier'] if now else '카드 없음'} (만들 때 {tier})"))
        r = subprocess.run(["ffmpeg", "-nostats", "-i", str(mp4), "-af", "volumedetect,silencedetect=n=-45dB:d=3", "-vn", "-f", "null", "-"], capture_output=True, text=True).stderr
        mx = float(re.search(r"max_volume: (-?[\d.]+) dB", r)[1])
        sil = re.findall(r"silence_duration: ([\d.]+)", r)
        if mx >= -0.1:
            issues.append((tag, f"클리핑 의심 max {mx}dB"))
        if sil:
            issues.append((tag, f"무음 3초 이상 {sil}"))
        rows.append(dict(tag=tag, tier=tier, who=d.name.split("_")[1], date=d.name[:6], slug=slug, s=m["src_start"], e=m["src_end"], len=m["clip_len"], path=str(mp4), mb=mp4.stat().st_size / 1e6,
                         why=m["tier_why"] or "", code=m["code"], likely=m.get("likely"), lp=m["lead"]["pad"], tp=m["trail"]["pad"], mc=m.get("multi"), sc=m.get("scene"), end_db=k.get("end_rel_db")))
by = defaultdict(list)
for r in rows:
    if r["tier"] == "auto":
        by[r["who"], r["date"]].append(r)
for g in by.values():            # 중복 녹화: 다른 녹화(slug)끼리 길이가 3초 안인 경우를 의심
    for i, a in enumerate(g):
        for b in g[i + 1:]:
            if a["slug"] != b["slug"] and abs(a["len"] - b["len"]) < 3:
                issues.append((a["tag"], f"중복 의심 {b['tag']}"))
L = ["# 완성본 라이브 클립 INDEX (NAS 10월)", "",
     f"규칙 {RULE}: 곡 시작 앞/끝 뒤 최대 2초의 음성 없는 공백(가장 긴 공백)을 여유로 둔다(0.3초 미만이면 여유 없음). 길이는 여유 포함 실제 컷, 시각은 NAS 원본 녹화 안의 위치. 여유(앞/뒤)는 초.",
     "auto = 정식 완성본. review/optional 은 사람이 듣고 판단하기 위한 미검증 클립(ctx20 없음), 파일명 끝 R/O + 근거 코드(NEW 새 채널 기준 없음, IDLE 정지 화면 의심, FAR 장면 멀지만 다중 참조 live, AMB 장면 애매, SHORT 짧음, LONG 김, BD 승인 라이브지만 경계 어긋남, PIANO 피아노 의심), -L 은 likely 조건 통과.",
     "클리핑 의심(max_volume 0dB 근처) 곡은 소스(원본 방송) 음량이 큰 것으로 판단했고 인코딩 결함이 아니다.", ""]
for tier, F in DIRS:
    T = [r for r in rows if r["tier"] == tier]
    L += [f"## {tier}: {len(T)}곡, {sum(r['len'] for r in T) / 60:.1f}분, {sum(r['mb'] for r in T) / 1000:.2f}GB ({F})", ""]
    for w in sorted({r["who"] for r in T}):
        g = sorted((r for r in T if r["who"] == w), key=lambda r: (r["date"], r["slug"], r["s"]))
        L += [f"### {tier} / {w}: {len(g)}곡, {sum(r['len'] for r in g) / 60:.1f}분", "", "| 방송 | 원본 구간 | 길이 | 여유 앞/뒤 | 근거 | multi | 파일 |", "|---|---|---|---|---|---|---|"]
        for r in g:
            L.append(f"| {r['slug']} | {t3(r['s'])}-{t3(r['e'])} | {r['len']:.0f}s | {r['lp']:.1f}/{r['tp']:.1f} | {r['code']}{'-L' if r['likely'] else ''} {r['why']} | {r['mc']} | `{r['path']}` |")
        L.append("")
L += ["## 점검에서 걸린 항목", ""] + ([f"- {t}: {w}" for t, w in issues] or ["- 없음"])
L += ["", f"## 이전 규칙(여유 없음) 파일 {len(old)}개 - 새 규칙 파일로 대체됨, 삭제하지 않음", ""] + [f"- `{p}`" for p in old]
Path("out/final/INDEX.md").write_text("\n".join(L) + "\n", encoding="utf8")
print(len(rows), "곡", len(issues), "건 이슈", len(old), "개 구 규칙")
for t, w in issues:
    print(" ", t, w)
