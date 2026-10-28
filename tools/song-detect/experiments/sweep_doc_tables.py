"""cache/proto_sweep 의 원시 결과 json -> experiments_log/sweep_tables.md (전체 표). 본문(sweep.md)에는 요약만 둔다.
  python experiments/sweep_doc_tables.py"""
import json
from pathlib import Path
import numpy as np
O = Path("cache/proto_sweep")
out = ["# sweep 트랙 전체 표 (자동 생성: experiments/sweep_doc_tables.py)", "", "원시 json 은 cache/proto_sweep/ (커밋 안 함). 지표 약어: h@ = 메모 숫자 정답 hit(0.5/3/10초), 방향 = early/late 지적 방향 통과(27), 좋음 = 경계 좋음 유지(67), 길이>5초 = 곡 길이 오차 5초 초과 곡 수, moved2 = 전 방송 840구간 중 곡 경계가 2초 넘게 움직인 수.", ""]


def jl(n):
    return json.load(open(O / n, encoding="utf8"))


# 1 경계 OAT 굵은 격자
if (O / "oat.md").exists():
    out += ["## T1. 경계 규칙 상수 OAT (기본값 x 0.25~3 배, 통과 = 게이트 무회귀)", "", (O / "oat.md").read_text(encoding="utf8"), ""]
# 2 fine
if (O / "oat_fine.table.json").exists():
    rows = jl("oat_fine.table.json")
    out += ["## T2. 경계 규칙 상수 OAT 촘촘(기본값 +-20%, 2% 간격): 실제 절벽까지 거리", "", "| 상수 | 기본 | 통과 연속 구간 | 아래 첫 실패(%, 사유) | 위 첫 실패(%, 사유) | 개선(무회귀) 값 | 유형 |", "|---|---|---|---|---|---|---|"]
    key = lambda r: min([abs(x) for x in (r["margin_lo"], r["margin_hi"]) if x is not None] or [999])
    for r in sorted(rows, key=key):
        f = lambda m, w: "-" if w is None else f"{w[0]:.4g} ({m:+.0f}%): {w[1]}"
        out.append(f"| {r['key']} | {r['default']:g} | {r['lo']:.4g} ~ {r['hi']:.4g} | {f(r['margin_lo'], r['fail_lo'])} | {f(r['margin_hi'], r['fail_hi'])} | {', '.join(f'{x:.4g}' for x in r['better'][:4]) or '-'} | {r['kind']} |")
    out.append("")
# 3 route risk
if (O / "route_risk.md").exists():
    out += ["## T3. route/N 신호 임계 과적합 위험표 (GPU OAT 241점, 라이브 136 + N 75, 등록부 없음)", "", (O / "route_risk.md").read_text(encoding="utf8"), ""]
# 4 detect
if (O / "detect_oat.json").exists():
    d = jl("detect_oat.json")
    out += ["## T4. detect 파라미터 재탐지(점수 캐시 재사용, 상류 평가)", "", "지표: gold = golden 113곡 중 같은 곡 KEEP 매칭 / L = 메모 라이브 49 매칭 / N = 메모 N 55 중 여전히 KEEP(낮을수록 상류 노출 적음) / keep = 전 방송 KEEP 수 / new = 기준에 없던 KEEP / lost = 기준에 있던 KEEP 소실 / dr8 = 경계가 8초 넘게 변한 golden / unev = 보컬 캐시가 덮지 못해 평가 못 한 후보(편향 주의)", "",
            "| 파라미터 | 값 | gold | L | N | keep | new | lost | dr8 | unev |", "|---|---|---|---|---|---|---|---|---|---|"]
    for k, rows in d["params"].items():
        for r in rows:
            out.append(f"| {k.replace('detect.P.', '')} | {r['v']:g} | {r['gold']} | {r['L']} | {r['N']} | {r['keep_n']} | {r['new']} | {r['lost']} | {r['drift8']} | {r['unev']} |")
    out.append("")
# 5 ablate
if (O / "ablate.json").exists():
    out += ["## T5. 규칙 끄기와 끝 규칙 순서", "", "| 변형 | golden 이탈 | h@0.5/3/10 | 방향 | 좋음 | 길이>5초 | moved2 |", "|---|---|---|---|---|---|---|"]
    for r in jl("ablate.json"):
        out.append(f"| {r['name']} | {r['gold_dev']} | {r['hit05']}/{r['hit3']}/{r['hit10']} | {r['dir_pass']}/{r['dir_n']} | {r['ok_pass']}/{r['ok_n']} | {r['len_gt5']} | {r.get('moved2')} |")
    out.append("")
# 6 morris
if (O / "morris.json").exists():
    m = jl("morris.json")["out"]
    out += ["## T6. Morris 스크리닝 (SALib, r=8, 기본값 +-30%)", "", "mu_star = 기본 효과 절댓값 평균(영향), sigma = 표준편차(상호작용/비선형). 상위 15.", ""]
    for resp, v in m.items():
        o = sorted(zip(v["names"], v["mu_star"], v["sigma"]), key=lambda t: -t[1])[:15]
        out += [f"### 응답 {resp}", "", "| 상수 | mu_star | sigma |", "|---|---|---|"] + [f"| {n} | {a:.2f} | {b:.2f} |" for n, a, b in o] + [""]
# 7 route robust + holdout
if (O / "route_robust.json").exists():
    r = jl("route_robust.json")
    out += ["## T7. route 후보 설정: 이웃 안정성(범위 +-d 교란 4096개 중 가능률)과 그룹 부트스트랩", "", "| 설정 | N 노출(75) | blind9 N | 손실 | auto N | auto 라이브 | 가능률 1% | 2% | 5% | 10% | N 노출률 [95% 구간] |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in r.items():
        out.append(f"| {k} | {v['N_all']} | {v['N_b9']} | {v['L_loss']} | {v['N_auto']} | {v['L_auto']} | " + " | ".join(f"{n['feas']:.2f}" for n in v["nbhd"]) + f" | {v['boot']['N_rate'][0]:.1%} [{v['boot']['N_rate'][1][0]:.1%}-{v['boot']['N_rate'][1][1]:.1%}] |")
    out.append("")
if (O / "route_holdout.json").exists():
    h = jl("route_holdout.json")
    out += ["## T8. route 중첩 hold-out (뺀 그룹 표본으로 설정 선택 -> 뺀 그룹에서 평가)", "", "| 단위/선택 규칙 | hold-out N 노출 | hold-out 라이브 손실 |", "|---|---|---|"]
    for k, v in h.items():
        t = v["total"]
        out.append(f"| {k} | {t['N_hold']}/{t['nN']} | {t['L_hold']}/{t['nL']} |")
    out.append("")
Path("experiments_log").mkdir(exist_ok=True)
Path("experiments_log/sweep_tables.md").write_text("\n".join(out), encoding="utf8")
print("experiments_log/sweep_tables.md", len(out), "줄")
