"""blind9 사용자 판정(data/review/blind9/labels.json, 145개)을 정리해 등록한다. python experiments/mk_blind9.py [--write]
 - 중복(같은 방송에서 절반 이상 겹침 = 이전 규칙 stale 의 1초 차이) 제거 후 104개
 - 출력: BLIND9 상수 본문(labels.py 에 붙임), data/review/blind9/key.json(eval_blind 용), --write 면 known_negatives.json / approved.json 에 합침(멱등)
shortcut: N 유형 분류는 사용자 메모의 키워드 매칭, 새 표현이 나오면 other 로 떨어진다"""
import json, re, sys
from pathlib import Path

LAB = json.load(open("data/review/blind9/labels.json", encoding="utf8"))
CODE = {"rize": "아카네 리제", "nana": "하나코 나나", "toa": "시즈키 토아", "rang": "코가네 랑", "mary": "토키노 메리", "hiyori": "하나요 히요리"}   # datasets/nas_ingest.STREAMERS 역
TYPES = [(r"따라부르기", "sing_along", "원곡 따라 부르기"), (r"GTA.*같이보", "other_live_watch", "GTA 클립 같이보기(타인 라이브)"), (r"데뷔방송 같이보기", "other_live_watch", "타 스트리머 라이브 같이보기"),
         (r"커버곡.*같이보기|단체 커버곡", "cover_watch", "커버곡 같이보기"), (r"GTA", "gta_karaoke", "GTA 서버 노래방(타인 라이브)"), (r"리듬게임", "rhythm_game", "리듬게임"), (r"OST", "game_ost", "게임 OST"),
         (r"자리 ?비움|아무 멘트도 치지 않", "afk_bgm", "자리비움/BGM(멘트 없음)"), (r"추천방송", "listen_watch", "추천방송 감상")]


def typ(memo):
    return next(((t, w) for p, t, w in TYPES if re.search(p, memo)), ("bgm_chat", "배경음악 + 간헐 멘트"))


def dedupe(L):
    out = []
    for x in L:
        y = next((y for y in out if y["slug"] == x["slug"] and min(x["se"], y["se"]) - max(x["ss"], y["ss"]) >= 0.5 * min(x["se"] - x["ss"], y["se"] - y["ss"])), None)
        if y is None:
            out.append(dict(x))
        elif y["lab"] != x["lab"]:                               # 같은 곡 L/B 상충(경계 판정이 갈림): 경계 보수적으로 B
            y["lab"] = "B"
    return out


D = dedupe(LAB)
vno = lambda x: "_".join(x["slug"].split("_")[2:])             # NAS 슬러그 = pipeline 의 videoNo 자리
kid = lambda x: f"{vno(x)}_{int(x['ss'])}"
nm = lambda x: CODE[vno(x).split("_")[1]]
assert len(D) == 104 and sum(x["lab"] == "N" for x in D) == 55, len(D)
print("BLIND9 = {")
for x in D:
    t = typ(x["memo"])[0] if x["lab"] == "N" else None
    print(f'    "{kid(x)}": dict(live={x["lab"] != "N"}, tag={t!r}, user=None, boundary_ok={None if x["lab"] == "N" else x["lab"] == "L"}),')
print("}")
key = {kid(x): dict(name=nm(x), videoNo=vno(x), start=x["ss"], end=x["se"], len=x["se"] - x["ss"], scene=x["scene"], multi=x["multi"], tstd=x["sig"]["tstd"], blk=x["sig"]["blk"], speech=x["sig"]["speech"],
                    tier_why=x["why"], likely=x["likely"], lab=x["lab"], slug=x["slug"], file=x["file"]) for x in D}
Path("data/review/blind9/key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf8")
if "--write" in sys.argv:
    def merge(p, new, same):
        old = json.load(open(p, encoding="utf8")) if Path(p).exists() else []
        Path(p).write_text(json.dumps(old + [n for n in new if not any(same(n, o) for o in old)], ensure_ascii=False, indent=1), encoding="utf8")
    same = lambda a, b: a["videoNo"] == b["videoNo"] and abs(a["start"] - b["start"]) < 1
    merge("data/known_negatives.json", [dict(videoNo=vno(x), start=x["ss"], end=x["se"], why=f"blind9 {typ(x['memo'])[1]}: {x['memo'][:60]}") for x in D if x["lab"] == "N"], same)
    merge("data/approved.json", [dict(videoNo=vno(x), start=x["ss"], end=x["se"], src="blind9 사용자 라이브" + ("" if x["lab"] == "L" else "(경계 문제)"), boundary_ok=x["lab"] == "L") for x in D if x["lab"] != "N"], same)
