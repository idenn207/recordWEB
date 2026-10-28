"""ASR 경계 제안을 현재 엔진 경계 위에 얹어 memo_audit 지표(hit@0.5/3/10, 방향, 길이 오차, ok 유지)가 어떻게 변하는지 본다. 코드(snap)는 안 바꾸고 계산 위에서만 적용.
  python experiments/asr_memo.py [--tx t_small_multi] [--k 3] [--gap 8] [--pad_e 1.5] [--pad_s 0] [--W 40]
엔진 경계는 cache/proto_asr/engine_S.json 에 캐시(memo_audit.load_src('engine'), 첫 실행 수 분).
규칙: 끝 확장 = 엔진 끝 e 뒤로 가사 사슬이 이어지고(단어 >= k) 마지막 단어가 e+3초 보다 늦으면 e' = 마지막 단어 끝 + pad_e.
      시작 확장 = 엔진 시작 s 앞으로 가사 사슬(>= k 단어)이 있고 첫 단어가 s-3초 보다 이르면 s' = 첫 단어 시작 - pad_s.
shortcut: 가사 사슬은 곡 안 가사가 이어질 때만 연장하므로 끝이 MR 아웃트로(가사 뒤 소리)로 이어지는 곡(#26 등)은 가사 끝까지만 간다."""
import sys, os, json, argparse
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT); sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
import numpy as np
import memo_audit as M, asr_bounds as B, asr_eval as A
from asr_run import groups

CACHE = ROOT / "cache/proto_asr/engine_S.json"


def engine_S():
    if CACHE.exists():
        return json.load(open(CACHE, encoding="utf8"))
    exp = json.load(open(M.EXP, encoding="utf8"))
    S = M.load_src("engine", exp)
    json.dump(S, open(CACHE, "w", encoding="utf8"))
    return S


def apply(S, tx, k=3, gap=8.0, pad_e=1.5, pad_s=0.0, W=40.0, use_end=True, use_start=True, p=None):
    D = A.prep(tx, p)
    out, moved = [], []
    for x in S:
        x = dict(x)
        for gid, (g, ly, d) in D.items():
            if g["slug"] != x["slug"] or M.ov(x["s"], x["e"], *g["base"]) < 0.5 * (g["base"][1] - g["base"][0]):
                continue
            if use_end:
                r = B.chain_end(ly, x["e"], W, gap, 3.0)
                if r and r[1] >= k and r[0] > x["e"] + 3.0:
                    moved.append((gid, "end", round(r[0] + pad_e - x["e"], 1))); x["e"] = r[0] + pad_e
            if use_start:
                r = B.chain_start(ly, x["s"], W, gap, 3.0)
                if r and r[1] >= k and r[0] < x["s"] - 3.0:
                    moved.append((gid, "start", round(r[0] - pad_s - x["s"], 1))); x["s"] = r[0] - pad_s
        out.append(x)
    return out, moved


def report(name, S, exp):
    ev = M.evaluate(exp, S)
    s = M.summarize(ev)
    print(f"{name:34} hit@0.5/3/10 {s['hit@0.5']}/{s['hit@3']}/{s['hit@10']} of {s['num_sides']}  중앙|오차| {s['median_abs_err']}  방향 {s['dir_pass']}/{s['dir_n']}  ok 유지 {s['ok_pass']}/{s['ok_n']}  길이오차>5초 {s['len_err_gt5']}/{s['len_n']}  사라짐 {s['vanished']}")
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--tx", default="t_small_multi"); ap.add_argument("--k", type=int, default=3); ap.add_argument("--gap", type=float, default=8)
    ap.add_argument("--pad_e", type=float, default=1.5); ap.add_argument("--pad_s", type=float, default=0.0); ap.add_argument("--W", type=float, default=40)
    a = ap.parse_args()
    exp = json.load(open(M.EXP, encoding="utf8"))
    S = engine_S()
    report("엔진(현재)", S, exp)
    for nm, ue, us in (("+ASR 끝", True, False), ("+ASR 시작", False, True), ("+ASR 끝+시작", True, True)):
        S2, mv = apply(S, a.tx, a.k, a.gap, a.pad_e, a.pad_s, a.W, ue, us)
        report(f"{nm} [{a.tx} k={a.k} gap={a.gap} W={a.W}]", S2, exp)
        print("     이동:", mv)
