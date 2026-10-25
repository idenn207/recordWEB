"""3단계 라우팅 (별도 모듈): KEEP 후보를 auto / review / drop 으로 나눈다. 오탐이 더 나쁘므로 애매하면 review 로 보낸다.
입력은 detect -> scene 을 거친 segments.json(각 구간의 scene 거리, 같은 채널 기준 프레임 유무).
  drop   : 오디오 게이트 실패(keep=False), 또는 장면 거리가 drop 임계 초과(같이 보기/영상 시청/콘서트 화면)
  review : 같은 채널 기준 프레임이 없음, 장면이 애매함, 길이가 1절/짧은 랩(90~125초)이거나 6분 근처, 장면 거리를 못 읽음
  optional: 피아노 연주 의심(직접 연주 라이브는 실수가 기본이라 기본 클립/검증 세트에서 분리, 별도 옵션 대상. 피아노 MR 에 부른 일반 라이브와 오디오로 구분 어려움)
  auto   : 위에 해당하지 않음 (125~340초, 같은 채널 장면과 거의 같음)
임계값 근거: 블라인드 검토(2026-10-24)에서 auto 6개 중 대기 화면 3개가 장면 거리 0.010 이었고 진짜 라이브는 0.059~0.073 이라 0.03 미만은 review.
기존 근거: 같은 채널 기준에서 확인된 라이브 <=0.07, 콘서트/따라 부르기/같이 보기 >=0.08 (마시로, 후야, 나나 3채널).
선택 입력 g['multi'] = scene_multi 의 live/watch/idle/unknown (없으면 기존 동작 그대로).
사용: python route.py <segments.json 입력> <출력> [has_refs=1]"""
import json, sys

P = dict(wait_s=300, scene_idle=0.03, scene_ok=0.075, scene_drop=0.18, len_lo=125, len_hi=340)
# shortcut: 임계값은 3개 채널에서 정함, 새 채널의 같은 채널 기준이 쌓이면 채널별 분포로 다시 보정


def tier(g, has_refs, p=P):
    if not g["keep"]:
        return "drop", g.get("why") or "audio-gate"
    m = g.get("multi")                                   # scene_multi.classify 결과(선택). idle/watch 는 레이아웃 근거라 채널 기준 없이도 drop
    if m in ("idle", "watch"):
        return "drop", f"다중 참조: {m}"
    if g.get("start", 1e9) < p["wait_s"]:
        return "drop", "방송 시작 대기시간(앞 5분)"
    if g.get("piano"):                                   # piano_gate.annotate 가 채운 경우만(없으면 기존 동작). 피아노 직접 연주/피아노 MR 의심: 보컬 스템 낮고 other 높음
        return "optional", f"피아노 연주 의심(vocal {g.get('vocal')}, other {g.get('other')})"   # 직접 연주 라이브는 선택 대상(기본 클립/검증 제외), MR 반주면 일반 라이브라 사람이 승격
    d = g.get("scene")
    if has_refs and d is not None and d > p["scene_drop"]:
        if m in ("live", "unknown"):                     # 게임 레이아웃이 바뀌면 같은 채널 기준과 멀어진다(마시로 정답 라이브 0.27~0.29). 다중 참조가 watch/idle 로 확정하지 않으면 버리지 않는다
            return "review", f"장면 멀지만 다중 참조 {m} {d:.2f}"
        return "drop", f"scene {d:.2f}"
    if not has_refs:
        return "review", "새 채널: 같은 채널 기준 프레임 없음" + (" (다중 참조 live)" if m == "live" else "")   # live 여도 auto 는 안 준다
    if d is None:
        return "review", "장면 거리를 읽지 못함"
    if d < p["scene_idle"]:
        return "review", f"정지 화면(대기 화면) 의심 {d:.3f}"
    if d > p["scene_ok"]:
        return "review", f"장면 애매 {d:.2f}"
    if g["len"] < p["len_lo"]:
        return "review", f"짧음 {g['len']:.0f}초(1절/짧은 랩)"
    if g["len"] > p["len_hi"]:
        return "review", f"김 {g['len']:.0f}초(곡 합쳐짐 의심)"
    return "auto", ""


def mark_likely(segs, p=P, n_max=20, win=3600):
    """'유력(likely)' 표시(등급은 review 그대로, 사람 검수 전 미검증): review 이고 다중 참조가 live, 길이 125~340초, 방송 시작 5분 이후,
    한 방송에서 곡 후보(keep)가 win 초 안에 n_max 개 이상 몰린 구간에 속하지 않음. known_neg/piano 는 이미 drop/optional 이라 걸러진 뒤에 부른다.
    shortcut: 근거는 blind5/6/8 표본(scene_pool.py eval 의 likely 집계)뿐, 새 채널 표본이 쌓이면 재보정"""
    ts = [x["start"] for x in segs if x["keep"]]
    for g in segs:
        dense = any(sum(a <= t < a + win for t in ts) >= n_max for a in ts if a <= g["start"] < a + win)
        g["likely"] = bool(g.get("tier") == "review" and g.get("multi") == "live" and p["len_lo"] <= g["len"] <= p["len_hi"] and g["start"] >= p["wait_s"] and not dense)


def known_neg(vid, g, path="data/known_negatives.json"):
    """사용자가 '클립 대상 아님'으로 확인한 구간(영상번호, 시작/끝초)과 절반 이상 겹치면 drop. 오디오·장면으로 못 거르는 유형(게임 중 우발적 가창 등)용 임시 방어.
    shortcut: 확인된 사례만 막는다, 같은 유형이 쌓이면 규칙(특징)으로 일반화"""
    from pathlib import Path
    if not g["keep"] or not Path(path).exists():
        return
    for k in json.load(open(path, encoding="utf8")):
        ov = min(g["end"], k["end"]) - max(g["start"], k["start"])
        if str(k["videoNo"]) == str(vid) and ov >= 0.5 * min(g["end"] - g["start"], k["end"] - k["start"]):
            g["tier"], g["tier_why"] = "drop", "확인된 비대상: " + k["why"]


def known_pos(vid, g, path="data/approved.json"):
    """사용자 승인/사람 검수(재생목록 위치 정답) 라이브 구간과 절반 이상 겹치는 review/optional 후보는 auto (이미 사람이 확인한 곡이라 다시 검수 불필요). drop 은 유지.
    known_neg 보다 먼저 부른다(둘이 겹치면 비대상이 이긴다). 목록은 cache/exp15/mk_approved.py 가 만든다.
    승인 경계와 후보 경계 차이는 ref_bd 로 남긴다(등급은 겹침만 본다).
    shortcut: 영상번호+구간 일치만 본다(같은 방송 다시 탐지에서 경계가 조금 달라도 절반 겹침이면 됨), 새 방송에는 도움 안 됨"""
    from pathlib import Path
    if not g["keep"] or g.get("tier") not in ("review", "optional") or not Path(path).exists():
        return
    for k in json.load(open(path, encoding="utf8")):
        ov = min(g["end"], k["end"]) - max(g["start"], k["start"])
        if str(k["videoNo"]) == str(vid) and ov >= 0.5 * min(g["end"] - g["start"], k["end"] - k["start"]):
            g["ref_bd"] = bd = [round(g["start"] - k["start"], 1), round(g["end"] - k["end"], 1)]   # 후보 경계 - 승인 경계(초)
            if max(map(abs, bd)) > 10:                       # 라이브인 건 확인됐지만 곡 일부가 잘리거나 앞뒤 말이 붙음: auto 로 올리지 않고 review 에 남겨 사람이 듣게 한다
                g["tier_why"] = f"승인 라이브지만 경계 어긋남 {bd[0]:+.0f}/{bd[1]:+.0f}초"
            else:
                g["tier"], g["tier_why"] = "auto", "승인된 라이브: " + k["src"]
            return


if __name__ == "__main__":
    seg_in, seg_out = sys.argv[1:3]
    has_refs = next((a[9:] for a in sys.argv if a.startswith("has_refs=")), "1") == "1"
    segs = json.load(open(seg_in, encoding="utf8"))
    for g in segs:
        g["tier"], g["tier_why"] = tier(g, has_refs)
    json.dump(segs, open(seg_out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    from collections import Counter
    print(dict(Counter(g["tier"] for g in segs if g["keep"] or g["tier"] != "drop")))
