"""전사(asr_run) 기반 N(라이브 아님) 신호 후보 - 등록부 없이 쓰는 특징. 연결 형태: 후보마다 곡 [s,e] +-60초를 전사한 json(d)과 점수 캐시(a)만 있으면 계산된다.
  talk_near : 곡 앞뒤 60초 안의 말 단어(Speech>Singing, 가사 아님) 수 / 분  -> 스트리머가 말을 하고 있는가(자리비움/BGM 이면 0 에 가깝다)
  talk_in   : 곡 안에서 말 단어 수 / 분 (곡 중 끼어드는 말)
  lyr_wpm   : 곡 안 가사 단어 / 분        lyr_cov : 곡 시간 중 가사 단어가 덮는 비율(간격 5초까지 이음)
  hall      : 곡 안 세그먼트 중 환각 의심 비율
fire(f, th): th = dict(talk_near_min=..) 중 하나라도 걸리면 사유 목록, 특징이 None 이면 None(n_signals.fire 와 같은 규약).
shortcut: 전사 비용(곡당 약 10~25초, small)과 모델 로드가 필요해 지금 파이프라인(점수 캐시 + wav 만)에는 연결하지 않았다. 임계는 아직 정하지 않았다(asr_n_eval.py 의 hold-out 결과 참고). 사용: python n_asr.py (자가검사)"""
import numpy as np

HOP = 0.5


def _split(d, a, p):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent / "experiments"))
    import asr_bounds as B
    ws = B.words(d, a, p)
    ly = set(map(tuple, B.lyric(ws, p)))
    return ws, ly


def features(d, a, s, e, p=None):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent / "experiments"))
    import asr_bounds as B
    p = p or B.P
    ws, ly = _split(d, a, p)
    talk = [w for w in ws if tuple(w) not in ly and w[5] > w[4]]
    dur = max(e - s, 1.0)
    near_dur = max(min(60.0, s - d["t0"]) + min(60.0, d["t1"] - e), 1.0)
    near = [w for w in talk if (s - 60 <= w[0] < s) or (e <= w[0] < e + 60)]
    inn = [w for w in talk if s <= w[0] < e]
    lin = sorted(w for w in ly if s <= w[0] < e)
    cov, cur = 0.0, None
    for w in lin:
        if cur and w[0] - cur[1] <= 5.0:
            cur[1] = max(cur[1], w[1])
        else:
            if cur: cov += cur[1] - cur[0]
            cur = [w[0], w[1]]
    if cur: cov += cur[1] - cur[0]
    sg = [x for x in d["segs"] if s <= x["s"] < e]
    return dict(talk_near=60 * len(near) / near_dur, talk_in=60 * len(inn) / dur, lyr_wpm=60 * len(lin) / dur, lyr_cov=cov / dur,
                hall=float(np.mean([x["cr"] > p["cr"] or x["alp"] < p["alp"] or x["nsp"] > p["nsp"] for x in sg])) if sg else None)


def fire(f, th):
    if f is None or f.get("talk_near") is None:
        return None
    out = []
    if "talk_near_min" in th and f["talk_near"] < th["talk_near_min"]:
        out.append(f"곡 앞뒤 말 {f['talk_near']:.1f}단어/분(자리비움/BGM)")
    if "talk_in_max" in th and f["talk_in"] > th["talk_in_max"]:
        out.append(f"곡 중 말 {f['talk_in']:.1f}단어/분")
    return out


if __name__ == "__main__":
    a = np.zeros((400, 3), np.float32); a[:, 2] = 0.9
    d = dict(t0=0, t1=200, words=[[10, 11, "a", .9], [12, 13, "b", .9], [60, 61, "c", .9], [62, 63, "d", .9]],
             segs=[dict(s=10, e=13, text="a b", alp=-.3, nsp=.1, cr=1.0), dict(s=60, e=63, text="c d", alp=-.3, nsp=.1, cr=1.0)])
    a[:, 0] = 0.5     # 노래 우세
    f = features(d, a, 50, 150)
    assert f["lyr_wpm"] > 0 and f["talk_near"] == 0.0, f           # 앞 10~13초 단어는 가사로 분류, 말 단어 없음
    assert fire(f, dict(talk_near_min=1.0)) and fire(None, {}) is None
    print("n_asr selftest ok", {k: (round(v, 2) if v is not None else None) for k, v in f.items()})
