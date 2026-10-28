"""전사(단어 타임스탬프) -> 가사 구간/경계 제안/검증 신호. asr_run.py 가 만든 cache/proto_asr/tx/<태그>/<gid>.json 을 읽는다.
  가사 단어 = 환각 필터(압축비/반복/무음확률) + 오디오 지지(Singing 또는 Music 점수) 를 통과한 단어.
  lyric_span(words, lo, hi, gap) : [lo,hi] 안에서 gap 초보다 가깝게 이어진 단어 덩어리 중 가장 긴 것의 (첫 시작, 마지막 끝)
  tail_flag / head_flag          : 현재 끝 뒤 / 시작 앞 W초 안의 가사 단어 수(끝이 이르다 / 시작이 늦다 검증기)
사용: python experiments/asr_bounds.py selftest
shortcut: 가사 단어와 스트리머 발화를 텍스트로는 못 가르고 YAMNet Singing/Speech 점수로만 가른다(점수 해상도 0.5초). 전주/후주 길이는 곡마다 달라 가사 경계 -> 곡 경계 변환은 오프셋 통계로만 본다."""
import sys, json, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import numpy as np

HOP = 0.5
P = dict(cr=2.4, nsp=0.95, alp=-1.6, rep=3, sing=0.15, music=0.3, pmin=0.0, chunk=1, uniq=0.0, pmean=0.0, maxw=99.0)    # 기본 필터 파라미터(실험으로 바꿈)


def scores(vno):
    return np.load(ROOT / "cache/detect" / f"{vno}.scores.npy")


def load_tx(tag, gid):
    f = ROOT / "cache/proto_asr/tx" / tag / f"{gid}.json"
    return json.load(open(f, encoding="utf8")) if f.exists() else None


def norm(w):
    return re.sub(r"[^\w]", "", w.lower())


def words(d, a, p=P):
    """[(s, e, w, prob, sing, speech, music)] 환각 필터를 통과한 단어. a = scores.npy"""
    segs = d["segs"]
    bad = [False] * len(segs)
    for i, s in enumerate(segs):
        bad[i] = bool(p["chunk"]) and (s["cr"] > p["cr"] or s["nsp"] > p["nsp"] or s["alp"] < p["alp"])
        tk = norm(s["text"]).split() if False else s["text"].split()
        if p["uniq"] and len(tk) >= 6 and len(set(tk)) / len(tk) < p["uniq"]:      # 세그먼트 단위 반복 환각(chunk 값은 30초 덩어리 공통이라 진짜 가사까지 버린다)
            bad[i] = True
    # 같은 문장이 rep 번 넘게 연속 반복하면 환각으로 본다
    run, last = 0, None
    for i, s in enumerate(segs):
        t = norm(s["text"])
        run = run + 1 if t == last else 1
        last = t
        if run > p["rep"]:
            for j in range(i - run + 1, i + 1):
                bad[j] = True
    if p["pmean"]:
        for i, sg in enumerate(segs):
            pw = [w[3] for w in d["words"] if sg["s"] - .01 <= w[0] <= sg["e"] + .01]
            if pw and sum(pw) / len(pw) < p["pmean"]:
                bad[i] = True
    out = []
    for w in d["words"]:
        si = next((i for i, s in enumerate(segs) if s["s"] - 0.01 <= w[0] <= s["e"] + 0.01), None)
        if si is None or bad[si] or w[3] < p["pmin"] or w[1] - w[0] > p["maxw"]:
            continue
        k0, k1 = int(w[0] / HOP), max(int(w[0] / HOP) + 1, int(w[1] / HOP) + 1)
        f = a[k0:k1]
        if not len(f):
            continue
        m = f.mean(0)
        out.append((w[0], w[1], w[2], w[3], float(m[0]), float(m[1]), float(m[2])))
    return out


def lyric(ws, p=P):
    """오디오가 지지하는 가사 단어: Singing 또는 Music 이 임계 이상이고 Singing >= Speech (말 우세 프레임 제외)"""
    return [w for w in ws if (w[4] >= p["sing"] or w[6] >= p["music"]) and w[4] >= w[5]]


def lyric_span(ws, lo, hi, gap=20.0):
    """[lo,hi] 안 단어를 gap 초 이내로 이은 덩어리 중 단어가 가장 많은 것 -> (첫 시작, 마지막 끝, 단어 수). 없으면 None"""
    ws = sorted(w for w in ws if lo <= w[0] <= hi)
    if not ws:
        return None
    cl, cur = [], [ws[0]]
    for w in ws[1:]:
        if w[0] - cur[-1][1] <= gap:
            cur.append(w)
        else:
            cl.append(cur); cur = [w]
    cl.append(cur)
    c = max(cl, key=len)
    return c[0][0], c[-1][1], len(c)


def count_in(ws, lo, hi):
    return sum(lo <= w[0] < hi for w in ws)


def selftest():
    ws = [(1, 2, "a", .9, .5, .1, .5), (3, 4, "b", .9, .5, .1, .5), (60, 61, "c", .9, .5, .1, .5), (62, 63, "d", .9, .5, .1, .5), (64, 65, "e", .9, .5, .1, .5)]
    assert lyric_span(ws, 0, 100, 20) == (60, 65, 3)
    assert lyric_span(ws, 0, 10, 20) == (1, 4, 2) and lyric_span(ws, 10, 20) is None
    assert count_in(ws, 0, 5) == 2
    assert lyric([(0, 1, "x", 1, .0, .5, .0), (0, 1, "y", 1, .5, .1, .0), (0, 1, "z", 1, .1, .5, .9)]) == [(0, 1, "y", 1, .5, .1, .0)]
    print("asr_bounds selftest ok")


if __name__ == "__main__":
    selftest() if sys.argv[1:] == ["selftest"] else print(__doc__)


# ---- 경계 검증/제안 -------------------------------------------------------------------------------------------------
def chain_end(ly, e, W=20.0, gap=8.0, back=3.0):
    """현재 끝 e 뒤로 가사가 이어지는지: e-back 이후 W초 안에서 gap 이내로 이어진 가사 단어 사슬. 반환 (마지막 단어 끝, 단어 수) 또는 None.
    사슬의 첫 단어는 e+W 이내여야 하고 e 이전 단어와 gap 안에 이어져 있어야 한다(곡이 끝난 뒤 따로 시작한 말은 사슬이 아님)."""
    ws = sorted(w for w in ly if w[0] >= e - back)
    if not ws or ws[0][0] > e + W:
        return None
    last, n = ws[0][1], 1
    for w in ws[1:]:
        if w[0] - last > gap:
            break
        last, n = max(last, w[1]), n + 1
    return last, n


def chain_start(ly, s, W=20.0, gap=8.0, fwd=3.0):
    """chain_end 의 거울상: 현재 시작 s 앞으로 가사가 이어지는지. 반환 (첫 단어 시작, 단어 수) 또는 None."""
    ws = sorted((w for w in ly if w[1] <= s + fwd), key=lambda w: -w[1])
    if not ws or ws[0][1] < s - W:
        return None
    first, n = ws[0][0], 1
    for w in ws[1:]:
        if first - w[1] > gap:
            break
        first, n = min(first, w[0]), n + 1
    return first, n


def extent(ly, s, e, gap=30.0, k=3):
    """곡 [s,e] 와 가장 많이 겹치는 가사 덩어리(단어 간격 <= gap)의 (첫 단어 시작, 마지막 단어 끝, 단어 수). 덩어리 단어가 k 미만이면 None.
    가사 경계 - 곡 경계 = 전주/후주 길이이므로 곡 경계로 바꾸려면 곡마다 다른 오프셋을 알아야 한다(asr_eval 의 offsets 로 분포를 잰다)."""
    ws = sorted(ly)
    if not ws:
        return None
    cl, cur = [], [ws[0]]
    for w in ws[1:]:
        if w[0] - max(x[1] for x in cur) <= gap:
            cur.append(w)
        else:
            cl.append(cur); cur = [w]
    cl.append(cur)
    ov = lambda c: max(0.0, min(e, max(x[1] for x in c)) - max(s, c[0][0]))
    c = max(cl, key=ov)
    return (c[0][0], max(x[1] for x in c), len(c)) if ov(c) > 0 and len(c) >= k else None
