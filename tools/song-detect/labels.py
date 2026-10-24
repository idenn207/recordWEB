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
ADD = {"blind5": BLIND5}


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
