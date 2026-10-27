"""회귀 감사 3단계(읽기 전용): audit_regress.py 의 행 + 수작업 검증 결과(스펙트로그램/vocal 비율/실험)를 묶어 regression.json 최종본을 쓴다.
순서: python experiments/audit_regress.py  ->  python experiments/audit_regress_final.py"""
import json, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
P = ROOT / "data/review/blind9/audit/regression.json"
rows = json.load(open(P, encoding="utf8"))
if isinstance(rows, dict): rows = rows["rows"]
M = json.load(open(ROOT / "cache/audit/master.json", encoding="utf8"))
by = {(r["vid"], round(r["refine"][0], 1)): r for r in M}
uniq = {}
for x in rows:
    if x["found"]: uniq.setdefault((x["vid"], round(x["refine"][0], 1)), x)
approved_nonB = [x for x in uniq.values() if x["set"] != "blind9-B"]
tstd = [by[(x["vid"], round(x["refine"][0], 1))]["tstd"] for x in approved_nonB]
weak = [t for t in tstd if t is not None and 25 <= t <= 34.5]
motion = [t for t in tstd if t is not None and t > 34.5]
cnt = collections.Counter(x["set"] for x in rows)
nf = [dict(set=x["set"], id=x["id"]) for x in rows if not x["found"]]
dev = [
    dict(id="D1", severity="critical", song="blind5 V15 (후야 15761307 @4692-4933, 사용자 경계 있음, 재생목록 정답)", kind="곡 사라짐(auto -> drop)",
         rule="scene_multi/route 영상 움직임 임계값 40 -> 34.5 (route.tier 의 watch drop)", direction="해당 없음(곡 자체가 사라짐)",
         evidence="4_scene tstd 35.67 > 34.5 라서 route.tier 가 '다중 참조: watch' 로 drop. known_pos 는 review/optional 만 auto 로 올리고 drop 은 유지하므로 승인 곡을 구하지 못함. 경계 자체는 v3 와 동일(이동 0, 정답 오차 시작 -3.0/끝 +0.6 그대로). v3 재현(임계 40)에서는 auto.",
         scope=f"승인 라이브(경계 비B 고유 {len(approved_nonB)}곡) 중 tstd>34.5 는 {len(motion)}곡(V15), 25~34.5(weak 대역)는 {len(weak)}곡(마시로 15827672 전부). HANDOFF 25절의 '라이브는 전부 tstd<25' 는 blind9 70곡 표본에만 맞고 승인 전체에는 틀림.",
         fix="drop 이전에 known_pos 승인 목록을 보거나(승인 구간은 움직임 drop 면제), 임계를 승인 최대치(35.7) 위로. weak 대역은 새 방송의 마시로형 라이브를 완성본에서 빼므로 같이 재검토. V15 를 회귀 테스트로 고정."),
    dict(id="D2", severity="high", song="후야 15761307 @726-1083 (재생목록 위치 정답)", kind="끝 이동 -25.4초, 정답에서 멀어짐(끝 오차 -1.5 -> -26.9), 등급 auto -> review(BD)",
         rule="E3 깊은 무음(끝 앞 40초 안 마지막 무음 뒤 4초가 조용하면 무음 시작에서 끝)", direction="정답(사용자 재생목록 끝) 반대 방향",
         evidence="스펙트로그램(cache/audit/reg/v726_end.png): 1056.1 에 깊은 무음, 1060~1068 에 조용한 피아노 코다(Music>=0.9, Singing 0, 곡 대비 -20dB), 1069 이후 말소리. E3 는 코다 앞 무음에서 끊어 코다 8초를 잃음. v3 끝(1081.5)은 코다 뒤 말 13초가 붙은 상태라 이상 끝은 약 1068. 사용자 정답 끝은 1083. 단일 임계 변경 실험(experiments/audit_e3_variant.py): 뒤 4초 기준 12->20dB 는 #60/#112(좋은 이동)까지 꺼짐, 25dB 이상은 #60 도 꺼짐 -> 임계만으로 못 가름. 코다 보존 변형도 #60 이 -33.3 -> -22.6 으로 퇴색해 미해결. 같은 유형(뒤가 조용한 음악, Singing 0)의 25초 이상 큰 E3 이동이 라벨 없는 곡에 6개 더 있음.",
         fix="E3 이동량 상한/코다 검사 + 726 을 회귀 케이스로. 라벨 없는 큰 E3 이동 6개는 사용자 청취 필요."),
    dict(id="D3", severity="medium", song="blind6 V16 (마시로 15324941 @21027-21247)", kind="끝 +38.0초 이동, 등급 auto -> review(경계 어긋남 +0/+38)",
         rule="E1 간주 뒤 이어지는 노래로 끝 연장", direction="개선으로 추정(미확인): v3 끝이 곡 중간 순간 끊김이었음",
         evidence="vocal 비율(Demucs 5초 창) 21200-21247 0.51, 21247-21285 0.82(노래 계속), 21286 이후 에너지 급락(cache/audit/reg/v21027_end.png). v3 끝 21247.1 은 곡 중간의 순간 Music 하락(rms -37dB) 한 점. 승인 경계는 사용자 정답이 아니라 탐지 당시 값(blind6 은 라이브 여부만 판정)이라 BD>10 검사가 개선된 경계를 어긋남으로 오판 -> 등급만 하락.",
         fix="known_pos 의 BD 비교는 경계 정답이 있는 항목(재생목록 위치, boundary_ok=True, USER)에만 적용. 이 곡은 사용자 1회 청취로 확인."),
    dict(id="D4", severity="medium", song="blind9 L 25곡(경계 좋음 판정) 중 9곡", kind="클립 끝에 곡 끝 직후 말소리 포함(컷 >= 곡 끝 + 1.0초 규칙), 곡 시작/끝 이동은 0",
         rule="make_final TAIL=1.0 (끝 여유 강제) + 페이드", direction="사용자 L 승인 상태에서 이탈(이동/길이 기준 초과는 아님)",
         evidence="L 25곡 모두 곡 시작/끝 이동 0.0초, 클립 길이 +0.0~+1.0초(3초 기준 미달). 그러나 v3 에서 끝 여유 0~0.28초라 말소리를 피했던 L 9곡(#14 #36 #70 #105 #126 #130 #132 #138 #143)이 v4 에서는 추가 구간에 Speech>=0.3 프레임을 포함하고, 6곡(#14 #70 #105 #126 #130 #138)은 곡 끝 0.3초 안에 말이 시작함(cache/audit/reg/tail.json). 페이드(1.0~1.5초)가 가리지만 완전 제거는 안 됨. HANDOFF 25절의 '41%' 와 같은 현상이 승인 L 곡에서도 발생.",
         fix="말이 곡 끝 1초 안에 시작하면 컷을 말 직전으로 하고 페이드를 짧게(사용자 청취 비교 필요)."),
    dict(id="D5", severity="medium", song="blind9 #45 (나나 10-16 @20396, L)", kind="L(경계 좋음) 인데 v3/v4 모두 review (회귀 아님, 기준 불일치)",
         rule="route.known_pos 첫 일치 항목 우선(재생목록 정답 시작이 16초 앞 -> BD +16)", direction="해당 없음",
         evidence="approved.json 에 같은 곡이 재생목록(경계 정답, 시작 16초 앞)과 blind9 L(boundary_ok True, 현재 경계) 두 항목으로 있고, 앞의 재생목록 항목에서 return 하여 '경계 어긋남 +16/-2' review. 사용자가 L 로 승인했는데 auto 가 아님. 등록 순서에 따라 결과가 달라지는 잠복 버그(B 와 재생목록이 겹치는 #23/#47/#48 은 재생목록이 앞이라 auto).",
         fix="known_pos 가 겹치는 모든 항목을 보고 boundary_ok=True 또는 BD<=10 항목이 하나라도 있으면 auto."),
    dict(id="D6", severity="low", song="경계 정답 없는 승인 곡 5곡: 마시로 15324941 @19945(S2 -5.1), 히나 15831370 @1190 D3 버스킹(S2 -6.6), 마시로 @19298(E2 끝 -3.5), 15805276 @8675(E3 끝 -2.2, out 폴더 없어 승인 경계에서 재계산), 재생목록 15713736 @20149(S2 -5.5)",
         kind="이동 > 2초, 사용자 정답 없음", rule="S2 / E2 / E3", direction="개선 추정(미확인)",
         evidence="@19945: 시작 앞 5초가 vocal 0.83 의 무반주/희박한 전주(스펙트로그램 하모닉), 그 앞은 말소리. @1190: 앞 6.6초가 MR 전주+vocal 0.71, 그 앞은 말소리. @19298: 끝 3.5초 앞이 자연스러운 감쇠 구간. @8675: 곡이 자연 페이드(rms -50 -> -60dB)로 끝난 뒤 8944 의 클릭 한 점을 잘라냄(무해). @20149: 정답 시작 대비 +32.3 -> +26.8 로 방향은 맞으나 여전히 26.8초 늦음(메모 '전주 MR 과 멘트하듯한 부분 잘림').",
         fix="코드 변경 불필요, 청취 우선순위는 @1190, @19945."),
]
improved = [dict(song=x["id"], set=x["set"], d=x["d"], err_s=x.get("err_s"), err_e=x.get("err_e"), cause=x["cause"], tier=[x["v3"]["tier"], x["v4"]["tier"]])
            for x in uniq.values() if (("err_s" in x and abs(x["err_s"][1]) < abs(x["err_s"][0]) - 0.5) or ("err_e" in x and abs(x["err_e"][1]) < abs(x["err_e"][0]) - 0.5))]
out = dict(
    method=dict(
        baseline="v3 = snap 규칙 E1 E2 E3 S1 S2 전부 끄고 컷 여유 v3(곡 끝 TAIL 없음)로 재계산(experiments/audit_engine.py). 실제 v3-pad json 117개와 v4-faithful json 63개의 곡/클립 경계를 0.06초 안에서 모두 재현(불일치 0).",
        engine="out/<id>/2_refine.json keep 구간 -> finalize.fix -> make_final.snap_quiet -> lead_pad/trail_pad. 840개 후보 전부 v3/v4 재계산(cache/audit/master.json), 변한 후보는 규칙별 only/loo 로 원인 규명.",
        tier="v3 등급 = v3 코드 재현(움직임 임계 40, 예전 4_scene, 현재 승인 목록): 승인 곡은 auto 가 기준 상태. v4 등급 = NAS 는 실제 카드(191개 전부 재현과 일치), VOD 는 4_scene(예전 장면 점수, 새 풀로 재계산 안 함)으로 현재 route 재현.",
        criteria="시작 또는 끝 이동 >2초, 클립 길이 변화 >3초, 곡 사라짐(drop), 등급 하락, 이웃 후보와 겹침(병합)",
        sets="blind9 L/B(boundary_truth.json), blind5 USER 7곡, blind6 시작 3곡, blind8 Q2-Q4, 재생목록 위치 정답 VOD 36+NAS 23, approved.json 의 blind5/6/7/8/blind9(L) 승인(boundary_ok False 제외)"),
    counts=dict(rows=len(rows), by_set=dict(cnt), unique_songs_found=len(uniq), not_found=len(nf), approved_nonB_unique=len(approved_nonB),
                flagged_unique=len([x for x in uniq.values() if x["flags"]])),
    headline=dict(
        blind9_L="25곡 곡 시작/끝 이동 0, 클립 길이 +0~1.0초, 전부 auto(#45 1곡만 review: D5), 사라진 곡 0.",
        truth_error="경계 정답이 있는 121점(나나는 VOD/NAS 중복 포함): 평균 |오차| 5.31 -> 3.29초, 2초 이내 84 -> 92, 오차가 바뀐 14점 중 개선 13 / 악화 1(D2).",
        tier_flips_NAS="NAS 191후보: review -> drop 55(전부 blind9 N 등록), review -> auto 27(L 24, B 3은 재생목록 정답과 v4 경계 일치), drop -> review 1(2026-10-21 랑 @21381, 장면 풀 변화 + E1 +50.6, 무라벨), L/B 손실 0.",
        approved_lost="승인 곡이 의도치 않게 바뀐 것: D1(곡 사라짐), D2(끝 -25초), D3(등급 하락, 경계는 개선 추정), D4(L 9곡 끝 말소리), D5(L 1곡 review 유지). 나머지 승인 곡은 변화 없음."),
    deviations=dev, improvements=improved, not_found=nf,
    supplementary=dict(
        v12_v13=json.load(open(ROOT / "cache/audit/reg/v1213.json", encoding="utf8")),
        no_out_dir=json.load(open(ROOT / "cache/audit/reg/noout.json", encoding="utf8")),
        merge_overlap=["2곳만 이웃과 겹침, 둘 다 승인 곡 아님: 13676831 @6159(E1 +81초가 다음 후보 6342 로 파고듦, 둘 다 watch drop), 15840388 @12348(E2 +22.9, v3 에도 3초 겹침)",
                       "재생목록 15761307@2377-2954(577초)는 사용자가 두 곡(탐지 2377-2684, 2703-2952)을 한 클립으로 합친 정답이라 경계 비교에서 제외"],
        limits=["VOD 곡의 v4 등급은 장면 점수를 새 풀로 재계산하지 않았다(VOD 주소 없음)", "정답 없는 이동(S2/E1/E3)의 방향은 스펙트로그램/vocal 비율 근거이며 사용자 청취가 아님", "NAS 클립 영상 프레임은 이번 회귀 점검에서 보지 않았다(곡 경계 소리 판단이 목적)"]),
    artifacts=["experiments/audit_load.py", "experiments/audit_engine.py", "experiments/audit_master.py", "experiments/audit_regress.py", "experiments/audit_regress_final.py", "experiments/audit_e3_variant.py",
               "cache/audit/master.json", "cache/audit/reg/*.png", "cache/audit/reg_*.py"],
    rows=rows)
P.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf8")
print("written", P, len(rows), "rows;", len(dev), "deviations;", len(improved), "improvements")
print(out["counts"]); print("weak/motion", len(weak), len(motion))
