"""축 (a) 단계 매니페스트 실측: 시나리오마다 '지금 방식(전부 다시)'과 '매니페스트(stale 단계만)'의 실제 시간을 잰다. 스크래치 out_m 에서만 실행, 소스 수정은 try/finally 로 되돌린다.
사용: python harness/exp_a.py [시나리오,...]  시나리오: noop comment thr knreg snap
결과: cache/proto_harness/exp_a.json"""
import json, os, sys, time, glob, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.lib import *
import harness.manifest as M

OUT = PH / "exp_a.json"
res = json.load(open(OUT)) if OUT.exists() else {}


def fresh():
    """프로세스 안 캐시 초기화(소스를 고쳤으니 AST 키를 다시 계산)"""
    M._CK.clear()
    return M.Run()


def tiers():
    return {(c["slug"], c["idx"]): (c["tier"], c["likely"], c["weak"]) for f in glob.glob(str(PH / "out_m/*/cards2.json")) for c in json.load(open(f, encoding="utf8"))}


def edit(path, old, new):
    p = ROOT / path
    src = p.read_text(encoding="utf8")
    assert old in src, (path, old)
    p.write_text(src.replace(old, new, 1), encoding="utf8")
    return src


def scen(name):
    sl = [r["slug"] for r in rows()]
    base = tiers()
    r = fresh()
    t0 = time.perf_counter()
    P = r.plan(sl)
    t_plan = time.perf_counter() - t0
    out = dict(plan_s=round(t_plan, 2))
    if name == "noop":
        pass
    elif name == "comment":                                    # route.py 에 주석/독스트링만 추가
        src = edit("route.py", "def tier(g, has_refs, p=P):", "# 주석만 추가한 시험\ndef tier(g, has_refs, p=P):")
        try:
            r = fresh(); P = r.plan(sl)
        finally:
            (ROOT / "route.py").write_text(src, encoding="utf8")
    elif name == "thr":                                         # n_signals 임계 rel_db -5.7 -> -5.0 (route 입력 코드만 변경)
        src = edit("n_signals.py", "P = dict(rel_db=-5.7, bursts=2.1)", "P = dict(rel_db=-5.0, bursts=2.1)")
        try:
            r = fresh(); P = r.plan(sl)
            t0 = time.perf_counter(); r.run(sl); out["run_s"] = round(time.perf_counter() - t0, 2); out["stage_s"] = {k: round(v, 2) for k, v in r.t.items()}; out["n"] = r.n
            now = tiers(); out["changed"] = sum(base[k] != now[k] for k in base)
        finally:
            (ROOT / "n_signals.py").write_text(src, encoding="utf8")
        fresh().run(sl)                                          # 원복 후 매니페스트도 원복
    elif name == "snap":                                        # 끝 탐색 앞쪽 범위 FWD 15 -> 20 (snap 규칙 변경)
        src = edit("snap.py", "BACK, FWD, MARGIN = 8.0, 15.0, 2.0", "BACK, FWD, MARGIN = 8.0, 20.0, 2.0")
        try:
            r = fresh(); P = r.plan(sl)
            t0 = time.perf_counter(); r.run(sl); out["run_s"] = round(time.perf_counter() - t0, 2); out["stage_s"] = {k: round(v, 2) for k, v in r.t.items()}; out["n"] = r.n
            now = tiers(); out["changed"] = sum(base[k] != now[k] for k in base if k in now); out["cands_before_after"] = [len(base), len(now)]
        finally:
            (ROOT / "snap.py").write_text(src, encoding="utf8")
        # 원복: 스크래치도 원래 상태로(3_final/4_scene 을 메인 것으로 되돌려 매니페스트 재생성)
        for s in sl:
            for f in ("3_final.json", "4_scene.json"):
                shutil.copy(ROOT / "out" / s / f, PH / "out_m" / s / f)
        fresh().run(sl, force=("route",))
    out["stale"] = {k: sum(k in v for v in P.values()) for k in ("final", "scene", "route")}
    out["stale_slugs"] = sum(bool(v) for v in P.values())
    res[name] = out
    OUT.write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(name, out)


if __name__ == "__main__":
    for n in (sys.argv[1].split(",") if len(sys.argv) > 1 else ["noop", "comment", "thr", "snap"]):
        scen(n)
