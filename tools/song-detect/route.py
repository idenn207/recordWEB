"""3단계 라우팅 (별도 모듈): KEEP 후보를 auto / review / drop 으로 나눈다. 오탐이 더 나쁘므로 애매하면 review 로 보낸다.
입력은 detect -> scene 을 거친 segments.json(각 구간의 scene 거리, 같은 채널 기준 프레임 유무).
  drop   : 오디오 게이트 실패(keep=False), 또는 장면 거리가 drop 임계 초과(같이 보기/영상 시청/콘서트 화면)
  review : 같은 채널 기준 프레임이 없음, 장면이 애매함, 길이가 1절/짧은 랩(90~125초)이거나 6분 근처, 장면 거리를 못 읽음
  auto   : 위에 해당하지 않음 (125~340초, 같은 채널 장면과 거의 같음)
임계값 근거: 같은 채널 기준에서 확인된 라이브 <=0.07, 콘서트/따라 부르기/같이 보기 >=0.08 (마시로, 후야, 나나 3채널).
사용: python route.py <segments.json 입력> <출력> [has_refs=1]"""
import json, sys

P = dict(scene_ok=0.075, scene_drop=0.18, len_lo=125, len_hi=340)
# shortcut: 임계값은 3개 채널에서 정함, 새 채널의 같은 채널 기준이 쌓이면 채널별 분포로 다시 보정


def tier(g, has_refs, p=P):
    if not g["keep"]:
        return "drop", g.get("why") or "audio-gate"
    d = g.get("scene")
    if has_refs and d is not None and d > p["scene_drop"]:
        return "drop", f"scene {d:.2f}"
    if not has_refs:
        return "review", "새 채널: 같은 채널 기준 프레임 없음"
    if d is None:
        return "review", "장면 거리를 읽지 못함"
    if d > p["scene_ok"]:
        return "review", f"장면 애매 {d:.2f}"
    if g["len"] < p["len_lo"]:
        return "review", f"짧음 {g['len']:.0f}초(1절/짧은 랩)"
    if g["len"] > p["len_hi"]:
        return "review", f"김 {g['len']:.0f}초(곡 합쳐짐 의심)"
    return "auto", ""


if __name__ == "__main__":
    seg_in, seg_out = sys.argv[1:3]
    has_refs = next((a[9:] for a in sys.argv if a.startswith("has_refs=")), "1") == "1"
    segs = json.load(open(seg_in, encoding="utf8"))
    for g in segs:
        g["tier"], g["tier_why"] = tier(g, has_refs)
    json.dump(segs, open(seg_out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    from collections import Counter
    print(dict(Counter(g["tier"] for g in segs if g["keep"] or g["tier"] != "drop")))
