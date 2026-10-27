"""사람 라벨 보관소: data/labels.json 을 만든다/갱신한다. 새 세트(blind6 등)는 ADD 에 항목을 추가하거나 add() 로 넣는다.
형식: {세트: {Vxx: {live, tag, user:[시작,끝]|null, boundary_ok}}}  user 는 클립 내 상대초(클립은 탐지 구간 앞뒤 20초 패딩).
tag(오탐 유형): cover_watch / other_live_watch / idle_screen / game_ost / rhythm_game / sing_along / gta_karaoke / afk_bgm / bgm_chat / listen_watch, 라이브면 null.
사용: python labels.py   (blind5 를 data/labels.json 에 기록)"""
import json
from pathlib import Path

OUT = Path("data/labels.json")
TAGS = {"cover_watch", "other_live_watch", "idle_screen", "game_ost", "rhythm_game", "sing_along", "gta_karaoke", "afk_bgm", "bgm_chat", "listen_watch", None}
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
# blind8(사용자 답변, 2026-10-25). 토아 10-24 는 싱크룸 방송이라 가창자가 토아가 아니어도 모두 정상 라이브(싱크룸/듀엣 예외). 시간은 파일 안 상대초(파일 0초 = 후보 시작 - 60초).
# 피아노: 직접 연주+가창(Q5 Q6)은 선택 대상이라 기본 평가 세트에서 제외, 피아노 MR 에 부른 것(Q7)은 일반 라이브.
BLIND8 = {"Q1_리코_15733149_2304": dict(live=False, tag="sing_along", note="원곡을 틀고 따라 부르기(원곡 덧씌움 = 같은 멜로디 2인 이상이면 제외)"),
          "Q2_토아_15837908_2443": dict(live=True, tag=None, user=[57, 268], note="메리+히요리 듀엣, 싱크룸. MR 시작이 보컬(01:00)보다 3초 앞: 드럼 하이햇 2+4박 카운트인"),
          "Q3_토아_15837908_4342": dict(live=True, tag=None, user=[59, 288], note="메리 단독, 싱크룸. 곡 종료 04:48 확정(05:48 은 오기), MR 종료 소리가 메리 감탄에 묻혀 불명확, 바로 멘트로 이어짐"),
          "Q4_토아_15837908_3403": dict(live=True, tag=None, user=[59, 265], note="랑 단독, 싱크룸"),
          "Q5_히나_4328274_16711": dict(live=None, tag="piano_live", note="직접 피아노 치며 가창 = 선택 대상, 평가 제외"),
          "Q6_히나_6570934_7339": dict(live=None, tag="piano_live", note="직접 피아노 치며 가창 = 선택 대상, 평가 제외"),
          "Q7_히나_15086957_7143": dict(live=True, tag=None, note="피아노 MR 에 가창(직접 연주 아님) = 일반 라이브. piano_gate 가 오분류하는 유형")}
# blind9(사용자 청취 판정, 2026-10-26, data/review/blind9/labels.json 145개 -> 중복 제거 104개, experiments/mk_blind9.py 가 생성). 키 = NAS 슬러그_후보 시작초. L 경계 좋음(boundary_ok=True) / B 라이브지만 경계 문제(False) / N 라이브 아님(tag = 유형).
# 같은 곡의 이전 규칙 stale(길이 1초 차이)은 하나로 보며 L/B 가 갈리면 B.
BLIND9 = {
    "2026-10-01_rize_1_3904": dict(live=False, tag='listen_watch', user=None, boundary_ok=None),
    "2026-10-01_rize_1_9493": dict(live=False, tag='afk_bgm', user=None, boundary_ok=None),
    "2026-10-03_rize_1_393": dict(live=False, tag='afk_bgm', user=None, boundary_ok=None),
    "2026-10-03_rize_1_12824": dict(live=False, tag='gta_karaoke', user=None, boundary_ok=None),
    "2026-10-03_rize_1_13294": dict(live=False, tag='gta_karaoke', user=None, boundary_ok=None),
    "2026-10-03_rize_1_13505": dict(live=False, tag='gta_karaoke', user=None, boundary_ok=None),
    "2026-10-03_rize_1_13763": dict(live=False, tag='gta_karaoke', user=None, boundary_ok=None),
    "2026-10-03_rize_1_14056": dict(live=False, tag='gta_karaoke', user=None, boundary_ok=None),
    "2026-10-03_rize_1_14342": dict(live=False, tag='gta_karaoke', user=None, boundary_ok=None),
    "2026-10-03_rize_1_14648": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-03_nana_1_23454": dict(live=False, tag='gta_karaoke', user=None, boundary_ok=None),
    "2026-10-03_nana_1_23799": dict(live=False, tag='gta_karaoke', user=None, boundary_ok=None),
    "2026-10-04_rize_1_4003": dict(live=False, tag='gta_karaoke', user=None, boundary_ok=None),
    "2026-10-04_rize_1_10357": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-04_rize_1_10568": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-04_rize_1_10893": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-06_nana_1_25197": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-06_nana_1_28702": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-06_nana_1_29030": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-07_rize_1_510": dict(live=False, tag='afk_bgm', user=None, boundary_ok=None),
    "2026-10-07_nana_1_15067": dict(live=False, tag='other_live_watch', user=None, boundary_ok=None),
    "2026-10-07_nana_1_18838": dict(live=False, tag='other_live_watch', user=None, boundary_ok=None),
    "2026-10-08_rize_1_5621": dict(live=False, tag='bgm_chat', user=None, boundary_ok=None),
    "2026-10-08_rize_1_26275": dict(live=False, tag='bgm_chat', user=None, boundary_ok=None),
    "2026-10-09_rize_1_22560": dict(live=False, tag='bgm_chat', user=None, boundary_ok=None),
    "2026-10-09_rize_1_23169": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-10_nana_2_15896": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-10_nana_2_16084": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-11_nana_1_2402": dict(live=False, tag='cover_watch', user=None, boundary_ok=None),
    "2026-10-11_nana_1_13600": dict(live=False, tag='afk_bgm', user=None, boundary_ok=None),
    "2026-10-12_rize_1_9424": dict(live=False, tag='afk_bgm', user=None, boundary_ok=None),
    "2026-10-12_rize_1_16165": dict(live=False, tag='afk_bgm', user=None, boundary_ok=None),
    "2026-10-12_rize_1_18652": dict(live=False, tag='afk_bgm', user=None, boundary_ok=None),
    "2026-10-16_nana_1_20110": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-16_nana_1_20396": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-16_nana_1_20684": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-16_nana_1_22027": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-16_nana_1_22423": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-16_nana_1_23029": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-16_nana_1_23289": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-16_nana_1_23558": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-17_toa_1_1185": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-17_toa_1_2668": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-17_toa_1_2994": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-17_rang_1_395": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-17_rang_1_2723": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-17_rang_1_3081": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-18_mary_1_2398": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-18_mary_1_2739": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-18_hiyori_1_1248": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-18_hiyori_1_2789": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-18_hiyori_1_3119": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-19_rize_1_2718": dict(live=False, tag='other_live_watch', user=None, boundary_ok=None),
    "2026-10-19_rize_1_3815": dict(live=False, tag='other_live_watch', user=None, boundary_ok=None),
    "2026-10-19_rize_1_4840": dict(live=False, tag='other_live_watch', user=None, boundary_ok=None),
    "2026-10-19_rize_1_7984": dict(live=False, tag='other_live_watch', user=None, boundary_ok=None),
    "2026-10-19_rize_1_9662": dict(live=False, tag='other_live_watch', user=None, boundary_ok=None),
    "2026-10-19_rize_1_9923": dict(live=False, tag='other_live_watch', user=None, boundary_ok=None),
    "2026-10-19_rize_1_11539": dict(live=False, tag='other_live_watch', user=None, boundary_ok=None),
    "2026-10-19_rize_1_11874": dict(live=False, tag='other_live_watch', user=None, boundary_ok=None),
    "2026-10-19_rize_1_17812": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-19_rize_1_18197": dict(live=False, tag='sing_along', user=None, boundary_ok=None),
    "2026-10-19_rize_1_18374": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-19_mary_1_19513": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-20_toa_1_8667": dict(live=False, tag='cover_watch', user=None, boundary_ok=None),
    "2026-10-20_mary_1_11307": dict(live=False, tag='cover_watch', user=None, boundary_ok=None),
    "2026-10-20_hiyori_1_534": dict(live=False, tag='cover_watch', user=None, boundary_ok=None),
    "2026-10-20_nana_1_4566": dict(live=False, tag='rhythm_game', user=None, boundary_ok=None),
    "2026-10-20_nana_1_4783": dict(live=False, tag='rhythm_game', user=None, boundary_ok=None),
    "2026-10-20_nana_1_6977": dict(live=False, tag='rhythm_game', user=None, boundary_ok=None),
    "2026-10-20_nana_1_7258": dict(live=False, tag='rhythm_game', user=None, boundary_ok=None),
    "2026-10-20_nana_1_7865": dict(live=False, tag='rhythm_game', user=None, boundary_ok=None),
    "2026-10-20_nana_1_9465": dict(live=False, tag='rhythm_game', user=None, boundary_ok=None),
    "2026-10-20_nana_1_10886": dict(live=False, tag='rhythm_game', user=None, boundary_ok=None),
    "2026-10-20_nana_1_13051": dict(live=False, tag='rhythm_game', user=None, boundary_ok=None),
    "2026-10-21_rang_1_14302": dict(live=False, tag='game_ost', user=None, boundary_ok=None),
    "2026-10-21_rang_1_21594": dict(live=False, tag='afk_bgm', user=None, boundary_ok=None),
    "2026-10-21_mary_1_21231": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-22_rize_1_17386": dict(live=False, tag='afk_bgm', user=None, boundary_ok=None),
    "2026-10-22_rize_1_21596": dict(live=False, tag='sing_along', user=None, boundary_ok=None),
    "2026-10-22_rize_1_21808": dict(live=False, tag='sing_along', user=None, boundary_ok=None),
    "2026-10-22_hiyori_1_26716": dict(live=False, tag='bgm_chat', user=None, boundary_ok=None),
    "2026-10-23_toa_1_21582": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-23_mary_1_18745": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-23_hiyori_1_6618": dict(live=False, tag='game_ost', user=None, boundary_ok=None),
    "2026-10-23_hiyori_1_7574": dict(live=False, tag='game_ost', user=None, boundary_ok=None),
    "2026-10-23_hiyori_1_8953": dict(live=False, tag='game_ost', user=None, boundary_ok=None),
    "2026-10-23_hiyori_1_22981": dict(live=False, tag='game_ost', user=None, boundary_ok=None),
    "2026-10-23_hiyori_1_24924": dict(live=False, tag='game_ost', user=None, boundary_ok=None),
    "2026-10-23_hiyori_1_26014": dict(live=False, tag='bgm_chat', user=None, boundary_ok=None),
    "2026-10-24_toa_3_555": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-24_toa_3_936": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-24_toa_3_1342": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-24_toa_3_1745": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-24_toa_3_2048": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-24_toa_3_2405": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-24_toa_3_2759": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-24_toa_3_3085": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-24_toa_3_3365": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-24_toa_3_3821": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-24_toa_3_4305": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-24_toa_3_4731": dict(live=True, tag=None, user=None, boundary_ok=False),
    "2026-10-24_toa_3_5108": dict(live=True, tag=None, user=None, boundary_ok=True),
    "2026-10-24_toa_3_5511": dict(live=True, tag=None, user=None, boundary_ok=False),
}
ADD = {"blind5": BLIND5, "blind6": BLIND6, "blind9": BLIND9}


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
