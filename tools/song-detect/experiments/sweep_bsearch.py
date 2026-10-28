"""경계 규칙 상수 동시 탐색(Optuna TPE) + 그룹(스트리머) hold-out 사후 평가.
  python experiments/sweep_bsearch.py run [--trials 600] [--workers 8]   -> cache/proto_sweep/bsearch.jsonl (시험마다 설정 + 지표 + 항목별 결과)
  python experiments/sweep_bsearch.py holdout                              -> 스트리머별 hold-out(학습 = 그 스트리머의 항목/golden 곡을 뺀 점수로 시험 선택, 평가 = 뺀 항목)
목적(스칼라): score = hit@0.5 + hit@3 + hit@10 + 방향 통과 + 경계좋음 유지 - 길이>5초 - 3 x golden 이탈 - 0.05 x (전 방송 이동곡 moved2). golden 이탈은 동결 기준이라 이동 폭의 대리 지표(정확도 아님).
탐색 대상: OAT 에서 반응이 있었던 상수(무반응 상수 제외), 기본값 +-span(기본 6%: OAT 촘촘 격자에서 단독 절벽이 2~10% 라 넓히면 거의 모든 점이 이탈).
shortcut: 항목이 13(숫자)+27(방향)+67(좋음) 개라 표본이 작다. hold-out 은 스트리머 단위 사후 선택이라 시험 수(600)가 선택 폭을 정한다."""
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import sweep_core as S
from sweep_oat import KEYS, INT

DEAD = {"snap.E1_SP", "snap.E1_MIN", "snap.music_run.gap", "snap.start_s2.maxback", "make_final.TAIL", "make_final.TAIL_MIN", "make_final.TAIL_SP", "make_final.TAIL_DB", "make_final.TAIL_LOUD", "make_final.PAD_MIN", "make_final.PAD_EDGE", "snap.HOLE"}
F = Path("cache/proto_sweep/bsearch.jsonl")


def items_of(ev, r):
    """시험 하나의 항목별 결과(hold-out 사후 계산용)"""
    _, evm = ev.memo(r["_R"])
    it = [[i["gid"], i["side"], i["kind"], None if i["kind"] != "num" else round(i["err"], 2), bool(i.get("pass_", i.get("asym", True)))] for i in evm["items"] if i["lab"] != "N"]
    return it, sorted({f[0] for f in r["gold_flags"]})


def run(trials, workers, span=0.06):
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    import tune
    cur = tune.listing()
    keys = [k for k in KEYS if k not in DEAD and k not in INT]
    ev = S.Evaluator(workers, wide=True)
    base = ev.evaluate({})
    st = optuna.create_study(sampler=optuna.samplers.TPESampler(seed=0, multivariate=True, n_startup_trials=80))
    out = open(F, "w", encoding="utf8")
    def rec(cfg, r, tag):
        it, gd = items_of(ev, r)
        row = dict(tag=tag, cfg=cfg, m={k: v for k, v in r.items() if not k.startswith("_") and k != "gold_flags"}, items=it, gold_ids=gd)
        out.write(json.dumps(row, ensure_ascii=False) + "\n"); out.flush()
        m = r
        return m["hit05"] + m["hit3"] + m["hit10"] + m["dir_pass"] + m["ok_pass"] - m["len_gt5"] - 3 * m["gold_dev"] - 0.05 * m.get("moved2", 0)
    rec({}, base, "base")
    t0 = time.time()
    for i in range(trials):
        tr = st.ask()
        cfg = {}
        for k in keys:
            d = cur[k]
            if k in INT:
                continue                                         # 정수형(RUN, B_SP, B_ITER)은 한 칸만 움직여도 이탈이 커서(Morris 최상위) 탐색에서 고정
            else:
                lo, hi = d * (1 - span), d * (1 + span)
                cfg[k] = tr.suggest_float(k, lo, min(hi, 1.0) if d < 1.0 else hi)
        r = ev.evaluate(cfg)
        sc = rec(cfg, r, "tpe")
        st.tell(tr, -sc)
        if i % 25 == 0:
            print(i, f"best {max(-t.value for t in st.trials if t.value is not None):.1f} 이번 {sc:.1f} ({time.time() - t0:.0f}s)", flush=True)
    ev.close()


def holdout():
    rows = [json.loads(l) for l in open(F, encoding="utf8")]
    base = rows[0]
    import audit_engine  # noqa: F401  (경로 설정)
    import golden_gate as G
    import memo_audit as M
    exp = json.load(open(M.EXP, encoding="utf8"))
    gold = json.load(open(G.GOLD, encoding="utf8"))["songs"]
    nm = {}
    for p in Path("data").glob("vods*.json"):
        for v in json.load(open(p, encoding="utf8")):
            nm[str(v["videoNo"])] = v["name"]
    K = json.load(open("data/review/blind9/key.json", encoding="utf8"))
    for g in exp["groups"]:
        nm.setdefault(g["vno"], K[g["key"]]["name"])
    st_of_gid = {g["gid"]: nm.get(g["vno"], g["vno"]) for g in exp["groups"]}
    st_of_gold = {e["id"]: nm.get(e["vid"], e["vid"]) for e in gold}
    streamers = sorted(set(st_of_gid.values()) | set(st_of_gold.values()))

    def score(row, excl=None, only=None):
        sel = lambda s: (excl is None or s != excl) and (only is None or s == only)
        it = [x for x in row["items"] if sel(st_of_gid[x[0]])]
        num = [x for x in it if x[2] == "num"]
        hit = sum(abs(x[3]) <= t for x in num for t in (0.5, 3, 10))
        okp = sum(x[4] for x in it if x[2] in ("ok", "dir"))
        gd = sum(sel(st_of_gold[i]) for i in row["gold_ids"])
        return hit + okp - 3 * gd, dict(hit=hit, okdir=okp, gold_dev=gd, n_num=len(num), n_okdir=sum(x[2] in ("ok", "dir") for x in it))
    tot = dict(base=0, chosen=0)
    print("스트리머 | 학습 점수(기준 -> 선택) | hold-out 점수(기준 -> 선택) | 상세(hold-out 기준/선택)")
    res = []
    for s in streamers:
        tr = [(score(r, excl=s)[0], i) for i, r in enumerate(rows)]
        b = max(tr)[1]
        ho_b, dtb = score(base, only=s)
        ho_c, dtc = score(rows[b], only=s)
        res.append(dict(streamer=s, train_base=score(base, excl=s)[0], train_best=max(tr)[0], hold_base=ho_b, hold_best=ho_c, trial=b, d_base=dtb, d_best=dtc))
        print(f"{s:8} | {score(base, excl=s)[0]} -> {max(tr)[0]} | {ho_b} -> {ho_c} | {dtb} / {dtc}")
        tot["base"] += ho_b; tot["chosen"] += ho_c
    print("합계 hold-out 점수 기준", tot["base"], "-> 선택", tot["chosen"], f"(스트리머 {len(streamers)}명, 시험 {len(rows)}개)")
    json.dump(dict(per=res, total=tot), open("cache/proto_sweep/bsearch_holdout.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "holdout"])
    ap.add_argument("--trials", type=int, default=600)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--span", type=float, default=0.06)
    a = ap.parse_args()
    run(a.trials, a.workers, a.span) if a.cmd == "run" else holdout()
