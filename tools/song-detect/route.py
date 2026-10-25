"""3단계 라우팅 (별도 모듈): KEEP 후보를 auto / review / drop 으로 나눈다. 오탐이 더 나쁘므로 애매하면 review 로 보낸다.
입력은 detect -> scene 을 거친 segments.json(각 구간의 scene 거리, 같은 채널 기준 프레임 유무).
  drop   : 오디오 게이트 실패(keep=False), 또는 장면 거리가 drop 임계 초과(같이 보기/영상 시청/콘서트 화면)
  review : 같은 채널 기준 프레임이 없음, 장면이 애매함, 길이가 1절/짧은 랩(90~125초)이거나 6분 근처, 장면 거리를 못 읽음
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
    if g.get("piano"):                                   # piano_gate.annotate 가 채운 경우만(없으면 기존 동작). 피아노 연주 의심: 보컬 스템 낮고 other 높음
        return "drop", f"피아노 연주 의심(vocal {g.get('vocal')}, other {g.get('other')})"
    if g.get("start", 1e9) < p["wait_s"]:
        return "drop", "방송 시작 대기시간(앞 5분)"
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


if __name__ == "__main__":
    seg_in, seg_out = sys.argv[1:3]
    has_refs = next((a[9:] for a in sys.argv if a.startswith("has_refs=")), "1") == "1"
    segs = json.load(open(seg_in, encoding="utf8"))
    for g in segs:
        g["tier"], g["tier_why"] = tier(g, has_refs)
    json.dump(segs, open(seg_out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    from collections import Counter
    print(dict(Counter(g["tier"] for g in segs if g["keep"] or g["tier"] != "drop")))
