"""다중 참조 장면 게이트 (새 채널용): 채널별 기준 프레임 없이 구간을 live / watch / idle / unknown 으로 분류한다.
기준 = 사용자가 live 로 승인한 클립의 키프레임(live 풀), 오탐 클립의 키프레임(neg 풀). 애매하면 unknown(= review).
  idle  : 시간축 밝기 변화가 거의 없음(대기 화면에 곡만 재생)
  watch : 검은 띠가 큼(같이 보기 레이아웃) / 화면 전체가 크게 계속 움직임(영상 시청, 게임, 리듬게임)
  live  : 위에 해당하지 않고 live 풀이 neg 풀보다 가까움
  unknown: 그 외(neg 풀이 더 가까움 포함), 또는 live 풀이 비어 있음
사용: python scene_multi.py  (data/blind5 의 승인/오탐 클립으로 방송 단위 leave-one-streamer-out 평가 후 assert)
이 모듈은 scene.thumbs(48x27 키프레임 회색)를 그대로 쓴다."""
import json, re, sys
from pathlib import Path
import numpy as np

P = dict(idle=5.0, black=0.10, motion=40.0)
# shortcut: idle(표본 4개: 1.3~2.8 vs 비대기 최소 10.1), black(오탐 6개 0.15~0.44 vs live 최대 0.009), motion(오탐 5개 >=43.6 vs live 최대 34.2)은 22개 표본에서 정한 값, 표본이 늘면 재보정


def feats(fr):
    """(시간축 밝기 표준편차 0~255, 항상 검은 픽셀 비율)"""
    return float(fr.std(0).mean() * 255), float(((fr < 14 / 255).mean(0) > 0.9).mean())


def dist(fr, R):
    return float(np.median([np.abs(R - f).mean(1).min() for f in fr]))


def classify(fr, live, neg, p=P):
    if len(fr) < 3:
        return "unknown", "키프레임 부족"
    tstd, blk = feats(fr)
    if tstd < p["idle"]:
        return "idle", f"정지 화면 tstd={tstd:.1f}"
    if blk > p["black"]:
        return "watch", f"검은 띠 {blk:.2f}"
    if tstd > p["motion"]:
        return "watch", f"전체가 계속 움직임 tstd={tstd:.1f}"
    if live is None or not len(live):
        return "unknown", "live 기준 없음"
    dl = dist(fr, live)
    dn = dist(fr, neg) if neg is not None and len(neg) else 9.0
    return ("live", f"dl={dl:.3f}<dn={dn:.3f}") if dl < dn else ("unknown", f"dl={dl:.3f}>=dn={dn:.3f} (픽셀 최근접은 약해서 watch 로 확정하지 않음)")


def pools(clips, labels, who, exclude):
    """exclude 방송(스트리머)을 뺀 live / neg 풀. clips={id: 키프레임}, labels={id: 'live'|'neg'}, who={id: 방송}"""
    ids = [v for v in clips if who[v] != exclude]
    cat = lambda g: np.concatenate([clips[v] for v in ids if labels[v] == g]) if any(labels[v] == g for v in ids) else None
    return cat("live"), cat("neg")


def loso(clips, labels, who):
    return {v: classify(clips[v], *pools(clips, labels, who, who[v])) for v in clips}


if __name__ == "__main__":
    d = Path("data/blind5")
    K = json.load(open(d / "key.json", encoding="utf8"))
    LIVE = "V11 V12 V13 V14 V15 V16 V22".split()
    REL = {"V13": (20, 230), "V12": (20, 245), "V14": (20, 187), "V15": (19, 256), "V16": (23, 267), "V22": (18, 150), "V11": (24, 245)}   # 사용자 시간(클립 내 상대초)
    if not (d / "_kf.npz").exists():   # 키프레임 캐시. 오탐은 클립 앞 20초 패딩 뒤 탐지 길이만큼. V07/V21 mp4 는 moov 가 없어 읽히지 않아 제외
        import scene
        np.savez(d / "_kf.npz", **{re.search(r"__(V\d+)", f.name).group(1): scene.thumbs(str(f), *REL.get(re.search(r"__(V\d+)", f.name).group(1), (20, 20 + K[re.search(r"__(V\d+)", f.name).group(1)]["len"])))
                                  for f in d.glob("*.mp4") if not re.search(r"__V(07|21)\.", f.name)})
    F = dict(np.load(d / "_kf.npz"))
    lab = {v: "live" if v in LIVE else "neg" for v in F}
    who = {v: K[v]["name"] for v in F}
    res = loso(F, lab, who)
    for v in sorted(res):
        print(v, lab[v], who[v], res[v])
    tp = [v for v in LIVE if res[v][0] == "live"]
    fp = [v for v in F if lab[v] == "neg" and res[v][0] == "live"]
    print(f"LOSO live 재현 {len(tp)}/{len(LIVE)}, 오탐이 live 로 통과 {len(fp)}/{len(F) - len(LIVE)}")
    assert not fp, fp
    assert not [v for v in LIVE if res[v][0] in ("idle", "watch")], "live 가 idle/watch 로 분류됨"
    print("ok")
