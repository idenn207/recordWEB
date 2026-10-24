"""사람 라벨 보관소: data/labels.json 을 만든다/갱신한다. 새 세트(blind6 등)는 ADD 에 항목을 추가하거나 add() 로 넣는다.
형식: {세트: {Vxx: {live, tag, user:[시작,끝]|null, boundary_ok}}}  user 는 클립 내 상대초(클립은 탐지 구간 앞뒤 20초 패딩).
tag(오탐 유형): cover_watch / other_live_watch / idle_screen / game_ost / rhythm_game, 라이브면 null.
사용: python labels.py   (blind5 를 data/labels.json 에 기록)"""
import json
from pathlib import Path

OUT = Path("data/labels.json")
TAGS = {"cover_watch", "other_live_watch", "idle_screen", "game_ost", "rhythm_game", None}
PAD = 20  # 클립 앞 패딩(초), key.json 의 clip_start 와 start 차이가 20 미만이면 평가에서 보정하지 않음(경계 통계 제외 대상 아님)

_fp = {"cover_watch": "V01 V02 V03 V04 V06 V09 V20 V24", "other_live_watch": "V05 V10",
       "idle_screen": "V07 V08 V17 V18", "game_ost": "V19", "rhythm_game": "V23"}
_live = {"V11": (24, 245), "V12": (20, 245), "V13": (20, 230), "V14": (20, 187), "V15": (19, 256),
         "V16": (23, 267), "V22": (18, 150), "V21": (97, 313)}
BLIND5 = {v: dict(live=False, tag=t, user=None, boundary_ok=None) for t, vs in _fp.items() for v in vs.split()}
BLIND5.update({v: dict(live=True, tag=None, user=list(u), boundary_ok=(v != "V21")) for v, u in _live.items()})
# blind6: 사용자는 라이브 여부만 판정(경계 없음). 오탐 3개는 방송 시작 직후 대기시간 음원. V08 V15 V22 는 라이브 시작이 클립 안 12/15/10초(우리는 20초에서 시작 = 늦음)
_fp6 = "V05 V10 V29".split()
BLIND6 = {f"V{i:02d}": dict(live=f"V{i:02d}" not in _fp6, tag="idle_screen" if f"V{i:02d}" in _fp6 else None, user=None, boundary_ok=None) for i in range(1, 31)}
BLIND6.update({"V08": dict(live=True, tag=None, user=[12, None], boundary_ok=None), "V15": dict(live=True, tag=None, user=[15, None], boundary_ok=None), "V22": dict(live=True, tag=None, user=[10, None], boundary_ok=None)})
# blind7(사용자 답변, 2026-10-25): V번호가 아니라 (videoNo, 시작초)로 식별하는 개별 후보. incidental = 라이브지만 게임 중 우발적/비정형이라 클립 가치 없음(라이브 아님으로 취급).
BLIND7 = {"A_후야_15761307_5038": dict(live=False, tag="incidental", note="게임 따라 부르기, 00:52 MR 시작, 끝 끊김"),
          "D1_히나_411": dict(live=False, tag="idle_screen", note="채팅 중 무반주 5초 후 음원"), "D2_히나_811": dict(live=False, tag="cover_watch", note="타인 음원"),
          "D3_히나_1190": dict(live=True, tag=None, note="마인크래프트 버스킹, 관객 호응 포함"),
          "B1 B2 C1 C2 E": dict(live=True, tag=None, note="마시로 라이브(완주 미확인)")}
ADD = {"blind5": BLIND5, "blind6": BLIND6}


def add(name, labels):
    assert all(l["tag"] in TAGS and (l["live"] == (l["tag"] is None)) for l in labels.values()), "tag/live 불일치"
    d = load() if OUT.exists() else {}
    d[name] = labels
    OUT.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf8")


def load():
    return json.loads(OUT.read_text(encoding="utf8"))


if __name__ == "__main__":
    for k, v in ADD.items():
        add(k, v)
    d = load()["blind5"]
    assert len(d) == 24 and sum(l["live"] for l in d.values()) == 8
    print("blind5", len(d), "개 기록, 라이브", sum(l["live"] for l in d.values()))
