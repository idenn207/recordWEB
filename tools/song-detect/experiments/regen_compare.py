"""재생성 전/후 카드 비교: NAS 61방송 후보의 등급 수와 곡 경계 이동. 전 = cache/regen/before_cards.json(`snap` 명령으로 저장), 후 = out/<슬러그>/cards.
사용: python experiments/regen_compare.py snap     # 지금 카드를 before 로 저장(재생성 전에 한 번)
      python experiments/regen_compare.py          # 전/후 등급 수, 등급이 바뀐 후보, 경계가 1초 넘게 움직인 후보"""
import glob, json, sys
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
B = ROOT / "cache/regen_v6/before_cards.json"      # v5 -> v6(통합) 비교. v4 -> v5 때의 파일은 cache/regen/before_cards.json


def cards():
    out = {}
    for r in json.load(open(ROOT / "data/nas_index.json", encoding="utf8")):
        for f in glob.glob(str(ROOT / f"out/{r['slug']}/cards/*.json")):
            j = json.load(open(f, encoding="utf8"))
            out[f"{r['slug']}/{j['idx']}"] = dict(tier=j["tier"], start=j["start"], end=j["end"], weak=j.get("weak"), why=j.get("tier_why"))
    return out


if __name__ == "__main__":
    now = cards()
    if sys.argv[1:] == ["snap"]:
        json.dump(now, open(B, "w", encoding="utf8"), ensure_ascii=False); print("saved", len(now)); sys.exit()
    old = json.load(open(B, encoding="utf8"))
    assert old.keys() == now.keys(), "후보 집합이 달라짐(탐지 캐시가 바뀜)"
    print("전", dict(Counter(v["tier"] for v in old.values())), "후", dict(Counter(v["tier"] for v in now.values())))
    print("\n등급 변경:")
    for k in sorted(now):
        if old[k]["tier"] != now[k]["tier"]:
            print(f"  {k} {old[k]['tier']} -> {now[k]['tier']}  {now[k]['why']}")
    print("\n경계 이동 > 1초 (시작/끝):")
    for k in sorted(now):
        ds, de = now[k]["start"] - old[k]["start"], now[k]["end"] - old[k]["end"]
        if abs(ds) > 1 or abs(de) > 1:
            print(f"  {k} {now[k]['tier']:6s} 시작 {ds:+.1f} 끝 {de:+.1f}  (전 {old[k]['tier']})")
