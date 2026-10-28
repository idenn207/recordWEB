"""boundary 트랙 실험 작업대: snap 이후에 얹는 '제안 규칙' prop 을 snap 흐름에 끼워 넣고(finalize.snap 교체) 메모 감사 + golden gate 를 한 번에 잰다.
코드(snap.py)는 건드리지 않는다. prop(pcm, a, voc, s, e, s0, e0) -> (s, e): s,e = 기존 snap 결과, s0,e0 = snap 입력(refine 후보).
사용: python experiments/bound_lab.py base            # 기준선(prop 없음)
      from bound_lab import run; run("이름", prop)      # 다른 스크립트에서
산출: cache/proto_boundary/lab_<이름>.json (지표 + 곡-경계별 오차). 공유 폴더(data, out)는 읽기만 한다.
shortcut: golden/메모 평가만 한다(전 방송 이동 목록은 sweep_lab.py). prop 은 snap 안의 규칙 순서(E1 -> E3 -> 시작)와 달리 모든 규칙이 끝난 뒤에 얹힌다."""
import sys, os, json, contextlib, io, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
os.chdir(ROOT)
import numpy as np
import snap, finalize
import memo_audit as M
import golden_gate as G

OUT = ROOT / "cache/proto_boundary"
OUT.mkdir(parents=True, exist_ok=True)
_orig = snap.snap
_MEMO = {}
VAR = [""]                  # 기존 snap 규칙 on/off 변형 이름(메모 캐시 키에 들어간다)


@contextlib.contextmanager
def proposing(prop, name="P"):
    """finalize.snap 을 '원래 snap + prop' 로 바꿔 둔다(E.calc, golden_gate.current 모두 finalize.fix 를 거친다)."""
    def sn(pcm, a, s, e, voc=None, trace=None):
        k = (VAR[0], getattr(pcm, "filename", id(pcm)), round(s, 3), round(e, 3), trace is None)
        if k not in _MEMO:                                  # 기존 snap 결과는 입력이 같으면 같다: 한 프로세스 안의 여러 설정이 공유
            tr = [] if trace is not None else None
            _MEMO[k] = (*_orig(pcm, a, s, e, voc, tr), tr)
        s2, e2, tr = _MEMO[k]
        if trace is not None:
            trace.extend(dict(x) for x in tr)
        if prop is None:
            return s2, e2
        s3, e3 = prop(pcm, a, voc, s2, e2, s, e)
        if trace is not None:
            snap.mv(trace, name, "start", s2, s3)
            snap.mv(trace, name, "end", e2, e3)
        return s3, e3
    finalize.snap = sn
    try:
        yield
    finally:
        finalize.snap = _orig


_GOLD = None


def review_only(prop):
    """정책 '승인 라이브는 건드리지 않고 B/review 후보에만': golden 곡(승인 L, 재생목록 정답)의 후보는 prop 을 건너뛴다."""
    global _GOLD
    if _GOLD is None:
        _GOLD = [(e["vid"], e["refine"][0], e["refine"][1]) for e in json.load(open(G.GOLD, encoding="utf8"))["songs"]]
    def p(pcm, a, voc, s, e, s0, e0):
        v = Path(str(getattr(pcm, "filename", ""))).stem
        if any(v == g[0] and abs(s0 - g[1]) < 0.2 and abs(e0 - g[2]) < 0.2 for g in _GOLD):
            return s, e
        return prop(pcm, a, voc, s, e, s0, e0)
    return p


def memo_eval(exp=None):
    exp = exp or M.jl(M.EXP)
    ev = M.evaluate(exp, M.load_src("engine", exp))
    s = M.summarize(ev)
    items = {f"{i['gid']}{i['side'][0]}:{i['kind']}": (round(i.get("err", i["move"]), 2), bool(i.get("asym", i.get("pass_", True)))) for i in ev["items"]}
    moves = {f"{i['gid']}{i['side'][0]}": round(i["move"], 2) for i in ev["items"]}
    return s, items, moves


def gold_eval():
    """golden 이탈 목록과, 그중 '정답(재생목록)에 더 가까워진 이동'을 뺀 진짜 이탈(real). 정답에 가까워진 이동은 화이트리스트 사유(개선)가 된다."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        bad = G.check()
    S = {e["id"]: e for e in json.load(open(G.GOLD, encoding="utf8"))["songs"]}
    real, good = [], set()
    for ids in {b[0] for b in bad}:
        e = S[ids]
        c = G.current(e["vid"], *e["refine"])
        f = e["frozen"]
        imp = False
        if c and e["truth"]:
            for i, (cur, fr) in enumerate(((c["s"], f["s"]), (c["e"], f["e"]))):
                if e["truth"][i] is not None and abs(cur - fr) > 2 and abs(cur - e["truth"][i]) < abs(fr - e["truth"][i]) - 1:
                    imp = True
        if imp and c["tier"] != "drop":
            good.add(ids)
    real = [b for b in bad if b[0] not in good]
    return bad, real, sorted(good)


def run(name, prop, gold=True, quiet=False):
    """prop 을 켠 상태의 메모/골든 지표를 계산해 lab_<name>.json 에 저장하고 한 줄 요약을 돌려준다."""
    t = time.time()
    with proposing(prop, name):
        s, items, moves = memo_eval()
        bad, real, good = gold_eval() if gold else ([], [], [])
    r = dict(name=name, memo={k: s[k] for k in ("hit@0.5", "hit@3", "hit@10", "median_abs_err", "asym_pass", "ok_pass", "ok_n", "dir_pass", "dir_n", "len_err_gt5", "len_n", "vanished", "multi_output")},
             golden_dev=len(bad), golden_real=len(real), golden_improved=good, golden=[list(map(str, b)) for b in bad], items=items, moves=moves, sec=round(time.time() - t, 1))
    (OUT / f"lab_{name}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf8")
    m = r["memo"]
    line = f"[{name}] hit@0.5/3/10 {m['hit@0.5']}/{m['hit@3']}/{m['hit@10']} 중앙 {m['median_abs_err']} dir {m['dir_pass']}/{m['dir_n']} ok {m['ok_pass']}/{m['ok_n']} len>5 {m['len_err_gt5']} 사라짐 {m['vanished']} golden 이탈 {len(bad)} (진짜 {len(real)}, 정답쪽 개선 {len(good)}) ({r['sec']}s)"
    if not quiet:
        print(line, flush=True)
    return r, line


LOG = OUT / "results.jsonl"


def batch(cfgs, policy=("all",), gold=True):
    """cfgs = {이름: prop}. policy 에 'all'(전체 적용) 'rev'(승인 golden 건너뜀) 를 넣어 각각 돌리고 results.jsonl 에 누적한다."""
    for n, p in cfgs.items():
        for pol in policy:
            r, line = run(f"{n}" + ("" if pol == "all" else "@rev"), p if pol == "all" else review_only(p), gold=gold)
            with open(LOG, "a", encoding="utf8") as f:
                f.write(json.dumps(dict(name=r["name"], memo=r["memo"], golden_dev=r["golden_dev"], golden_real=r["golden_real"], golden_improved=r["golden_improved"], golden=r["golden"], t=time.strftime("%H:%M:%S")), ensure_ascii=False) + chr(10))


def make_snap(hooks):
    """snap.snap 과 같은 흐름에 제안 규칙을 중간 자리에 끼운 판. hooks = {자리: prop}, 자리 = after_E1 / after_E1b / after_E3 / after_lead / after_S12 (규칙 순서 변경 실험).
    trace 는 쓰지 않는다(lab 평가는 곡 경계만 본다)."""
    from snap import cliff, bridge, quiet, run_len, env_end, deep_end, lead_start, start_s1, start_s2, B_MAXLEN, BACK, FWD, MARGIN, rms_db as rdb

    def sn(pcm, a, s, e, voc=None, trace=None):
        _, db = rdb(pcm, s, e)
        ref = float(np.median(db))
        H = lambda k, s_, e_: hooks[k](pcm, a, voc, s_, e_, s, e) if k in hooks else (s_, e_)
        c = cliff(a, e - BACK, e + FWD)
        e2 = e
        if c is not None:
            e2 = bridge(pcm, a, ref, c)
            if e2 > c and e2 - s > B_MAXLEN:
                e2 = c
        q = quiet(pcm, a, ref, e2 - 1, e2 + MARGIN)
        if len(q):
            e2 = float(q[0])
        e2 = e2 + run_len(a, e2)
        s_, e2 = H("after_E1", s, e2)
        e2 = env_end(pcm, a, ref, s, e2, voc)
        s_, e2 = H("after_E1b", s_, e2)
        e2 = deep_end(pcm, a, ref, e2)
        s2 = lead_start(pcm, a, s_, ref)
        s2, e2 = H("after_E3", s2, e2)
        s2, e2 = H("after_lead", s2, e2)
        if voc:
            s1 = start_s1(a, voc, s2, e2)
            s2 = s1 if s1 > s2 else start_s2(a, voc, s2)
        return H("after_S12", s2, e2)
    return sn


@contextlib.contextmanager
def with_snap(sn, tag):
    """finalize.snap 을 sn 으로 바꿔 둔다(캐시 키는 tag)."""
    VAR[0] = tag
    finalize.snap = sn
    try:
        yield
    finally:
        finalize.snap = _orig; VAR[0] = ""


def run_hooks(name, hooks, gold=True):
    """make_snap(hooks) 흐름으로 메모/골든 지표 (run 과 같은 출력)."""
    t = time.time()
    with with_snap(make_snap(hooks), name):
        s, items, moves = memo_eval()
        bad, real, good = gold_eval() if gold else ([], [], [])
    r = dict(name=name, memo={k: s[k] for k in ("hit@0.5", "hit@3", "hit@10", "median_abs_err", "asym_pass", "ok_pass", "ok_n", "dir_pass", "dir_n", "len_err_gt5", "len_n", "vanished", "multi_output")},
             golden_dev=len(bad), golden_real=len(real), golden_improved=good, golden=[list(map(str, b)) for b in bad], items=items, moves=moves, sec=round(time.time() - t, 1))
    (OUT / f"lab_{name}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf8")
    m = r["memo"]
    line = f"[{name}] hit@0.5/3/10 {m['hit@0.5']}/{m['hit@3']}/{m['hit@10']} 중앙 {m['median_abs_err']} dir {m['dir_pass']}/{m['dir_n']} ok {m['ok_pass']}/{m['ok_n']} len>5 {m['len_err_gt5']} 사라짐 {m['vanished']} golden 이탈 {len(bad)} (진짜 {len(real)}, 정답쪽 개선 {len(good)}) ({r['sec']}s)"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf8") as f:
        f.write(json.dumps(dict(name=name, memo=r["memo"], golden_dev=len(bad), golden_real=len(real), golden_improved=good, t=time.strftime("%H:%M:%S")), ensure_ascii=False) + chr(10))
    return r, line


def run_off(off):
    """기존 snap 규칙 off(집합)를 끈 변형의 lab 결과(위원회 구성원). 이름 off_<규칙>."""
    from blind9_bounds import patched
    VAR[0] = "off_" + "_".join(sorted(off))
    undo = patched(set(off))
    try:
        return run(VAR[0], None)
    finally:
        undo(); VAR[0] = ""


def load_base():
    f = OUT / "lab_base.json"
    return json.load(open(f, encoding="utf8")) if f.exists() else None


def diff(r, base=None):
    """기준선 대비 달라진 곡-경계 이동(1초 초과)과 나빠진/좋아진 방향 항목."""
    base = base or load_base()
    ch = {k: (base["moves"].get(k), v) for k, v in r["moves"].items() if base["moves"].get(k) is not None and abs(v - base["moves"][k]) > 0.5}
    return ch


if __name__ == "__main__":
    if sys.argv[1:] == ["base"]:
        run("base", None)
