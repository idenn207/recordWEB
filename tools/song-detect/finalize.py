"""파이프라인 마지막 경계 단계 (detect -> refine -> finalize -> scene -> route): snap.snap 으로 start/end 를 최종 확정한다.
입력 segments.json(cache/detect/<이름>.scores.npy 필요), 출력 segments.json: keep 구간만 start/end 를 바꾸고 이전 값은 start1/end1 에 남긴다.
안전장치: 이미 처리한 구간(start1 있음)은 건너뜀(멱등), 결과가 파일 범위 밖이거나 끝<=시작이거나 길이가 원래의 절반 미만/2배 초과면 원래 경계 유지(why_snap 에 기록).
기록: stages = snap 규칙별 이동 [{rule, edge, before, after, shift}], why_snap = 이동한 규칙 이름과 초("E1 end +46.0, S2 start -9.2"), 이동이 없으면 없음.
사용: python finalize.py <wav> <segments.json 입력> <출력>    /    python finalize.py selftest"""
import json, sys
import numpy as np
from paths import cache_of
from snap import pcm_of, snap, voc_of

MAXRATIO = 2.5      # 길이 안전장치 상한(배): E1b 가 #20(곡 338초, 후보 134초)을 2.22배로 잇는다. 전 방송 840구간 sweep 에서 1.6배 넘는 결과는 4개뿐(2.22, 1.99, 1.78, 1.76)이라 2.5 로 올려도 다른 곡이 새지 않는다


def fix(pcm, a, g, voc=None):
    if not g["keep"] or "start1" in g:
        return g
    tr = []
    s, e = snap(pcm, a, g["start"], g["end"], voc, tr)
    dur = len(pcm) / 16000
    if not (0 <= s < e <= dur and 0.5 < (e - s) / g["len"] < MAXRATIO):
        g["why_snap"], g["stages"] = "snap 결과 이상, 원래 경계 유지", []
        return g
    g.update(start1=g["start"], end1=g["end"], start=s, end=e, len=e - s, stages=tr)
    if tr:
        g["why_snap"] = ", ".join(f"{t['rule']} {t['edge']} {t['shift']:+.1f}" for t in tr)      # 규칙 이름과 이동량(초), 상세는 stages
    return g


def selftest():
    sr = 16000
    pcm = np.zeros(sr * 100, np.int16)
    pcm[sr * 20:sr * 80] = 3000                          # 20~80초 소리
    a = np.zeros((200, 3), np.float32)
    a[40:160, 2] = 0.9                                   # Music 20~80초
    g = fix(pcm, a, dict(keep=True, start=21.0, end=80.0, len=59.0))
    assert g["start"] <= 21.0 and "start1" in g and g["len"] == g["end"] - g["start"], g
    assert fix(pcm, a, g) is g and g["start1"] == 21.0   # 두 번째 호출은 변화 없음
    bad = fix(pcm, a, dict(keep=True, start=21.0, end=80.0, len=500.0))
    assert bad["why_snap"].startswith("snap 결과 이상") and bad["start"] == 21.0 and bad["stages"] == []
    assert g["stages"] and g["why_snap"].split()[0] == g["stages"][0]["rule"], g       # 이동한 규칙이 이름과 이동량으로 남는다
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1] == "selftest":
        selftest()
        sys.exit()
    wav, seg_in, seg_out = sys.argv[1:4]
    pcm, a, voc = pcm_of(wav), np.load(cache_of(wav, ".scores.npy")), voc_of(wav)
    segs = [fix(pcm, a, g, voc) for g in json.load(open(seg_in, encoding="utf8"))]
    json.dump(segs, open(seg_out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print(sum("start1" in g for g in segs), "개 확정,", sum(g.get("why_snap", "").startswith("snap 결과 이상") for g in segs), "개 원래 유지")
