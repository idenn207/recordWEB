"""전사 캐시(asr_run.py) -> 끝 early / 시작 late 검증기 평가와 경계 제안 오차. 지표는 memo_audit 와 같은 정답(expectations.json)을 쓴다.
  python experiments/asr_eval.py <태그> [--W 20 --k 3 --gap 8 --sing 0.15 ...]
양성 = 메모가 early(끝) / late(시작)라 한 곡, 음성 = 사용자가 경계 좋음(ok)이라 한 라이브(L/B) 곡. N 곡은 제외.
shortcut: 표본이 작다(끝 early 12, 끝 ok 약 40, 시작 late 9). 임계는 표본 내 선택이므로 참고값이다."""
import sys, json, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import asr_bounds as B
from asr_run import groups


def prep(tag, p=None, G=None):
    """{gid: (g, ly)} 전사가 있는 라이브(비 N) 곡의 가사 단어"""
    out = {}
    for g in (G or groups()):
        if g["lab"] == "N":
            continue
        d = B.load_tx(tag, g["gid"])
        if d:
            out[g["gid"]] = (g, B.lyric(B.words(d, B.scores(g["vno"]), p or B.P), p or B.P), d)
    return out


def verifier(D, W=20.0, gap=8.0, k=3, back=3.0):
    """끝/시작 검증기: 사슬 단어 수 >= k 이면 flag. 반환 {side: {pos, neg, flags_pos, flags_neg, list}}"""
    R = {}
    for side in ("end", "start"):
        want = "early" if side == "end" else "late"
        pos, neg, fp, fn, prop = [], [], [], [], {}
        for gid, (g, ly, d) in D.items():
            sd = g["sides"][side]
            if sd["issue"] not in (want, "ok"):
                continue
            b = g["base"][1 if side == "end" else 0]
            r = B.chain_end(ly, b, W, gap, back) if side == "end" else B.chain_start(ly, b, W, gap, back)
            flag = r is not None and r[1] >= k
            (pos if sd["issue"] == want else neg).append(gid)
            (fp if sd["issue"] == want else fn).append(gid) if flag else None
            if flag:
                prop[gid] = r[0]
        R[side] = dict(pos=len(pos), neg=len(neg), tp=len(fp), fp=len(fn), tp_ids=fp, fp_ids=fn, prop=prop)
    return R


def prop_err(D, R):
    """제안 경계의 정답 오차(정답이 있는 곡만): 가사 마지막/처음 단어 시각 - 정답. 가사 경계는 곡 경계와 전주/후주만큼 다르다."""
    rows = []
    for side in ("end", "start"):
        for gid, t in R[side]["prop"].items():
            g = D[gid][0]
            tr = g["sides"][side]["truth"]
            if tr is not None:
                rows.append((gid, side, round(t - tr, 1)))
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("tag"); ap.add_argument("--W", type=float, default=20); ap.add_argument("--k", type=int, default=3); ap.add_argument("--gap", type=float, default=8)
    ap.add_argument("--sing", type=float, default=B.P["sing"]); ap.add_argument("--music", type=float, default=B.P["music"])
    a = ap.parse_args()
    p = dict(B.P, sing=a.sing, music=a.music)
    D = prep(a.tag, p)
    R = verifier(D, a.W, a.gap, a.k)
    for side in R:
        r = R[side]
        print(f"{side}: 양성 {r['tp']}/{r['pos']} 음성 flag {r['fp']}/{r['neg']}  tp={r['tp_ids']} fp={r['fp_ids']}")
    print("제안 오차(가사 경계 - 정답):", prop_err(D, R))


def offsets(D, gap=30.0):
    """경계가 좋다(ok)고 한 변에서 가사 경계 - 곡 경계 분포: 시작(전주 길이), 끝(후주 길이, 음수=가사가 곡 끝보다 앞)."""
    S, E = [], []
    for gid, (g, ly, d) in D.items():
        r = B.extent(ly, *g["base"], gap)
        if r is None:
            continue
        if g["sides"]["start"]["issue"] == "ok":
            S.append(r[0] - g["base"][0])
        if g["sides"]["end"]["issue"] == "ok":
            E.append(r[1] - g["base"][1])
    return np.array(S), np.array(E)


def hit_rate(err, tols=(0.5, 3, 10)):
    return {f"@{t:g}": int((np.abs(err) <= t).sum()) for t in tols} | {"n": len(err)}
