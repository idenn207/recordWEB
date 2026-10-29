"""축 (f) 상시 점검 한 번에: golden gate + 메모 감사 게이트 + logo_route + 자가검사/테스트 + 변화 리포트(섀도 diff)를 병렬로 돌리고 한 표로 요약한다.
  python harness/check.py            전체 (병렬, 약 20초)
  python harness/check.py --fast     메모 감사, logo_route 를 건너뜀 (규칙 편집 중 빠른 확인)
  python harness/check.py --accept   지금 결과를 '승인된 기준'(변화 리포트 비교 기준)으로 저장. 의도한 변경을 확인한 뒤에만
  python harness/check.py --step 이름  단계 하나만(내부용, 마지막 줄이 JSON)
종료코드: 0 전부 통과 / 1 게이트 실패(승인 라이브 이탈, 메모 감사 퇴행, logo_route 퇴행, 테스트 실패, 변화 리포트 이탈) / 2 점검 자체 오류(단계가 예외로 죽음, 파일 없음).
게이트 기준: golden 이탈 0 / 메모 감사 hit@0.5,3,10 · 방향 통과 · 경계 좋음 유지가 저장본(memo_audit_baseline.json) 이상, 곡 사라짐 0, 길이 오차>5초 곡이 저장본 이하 /
 logo_route 가 규칙 A 재현(노출 23/weak 22/drop 10)과 배포 규칙 라이브 걸림 0 을 assert 하고, 배포 규칙 blind9 N 노출이 오디오만 14 이하 + 화면(integ_holdout eval 의 배포 경로 vis) 11 이하(라이브 손실 0) / 변화 리포트: 승인 라이브 노출 하락, N 이 auto 로, 승인 곡 경계 2초 초과 이동 없음.
출력 요약은 cache/proto_harness/check_last.json 에도 저장(CI 아티팩트용).
shortcut: 변화 리포트의 기준 스냅샷은 cache/proto_harness/check_accepted(첫 실행 때 자동 승인), 라벨은 NAS 10월 191후보뿐이라 다른 방송 세트는 golden 이 맡는다."""
import json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.lib import *

PY = sys.executable
SELF = [("selftest-route", [PY, "test_route.py"]), ("selftest-detect", [PY, "test_detect.py"]), ("selftest-snap", [PY, "snap.py", "selftest"]), ("selftest-finalize", [PY, "finalize.py", "selftest"]),
        ("selftest-make_final", [PY, "make_final.py", "selftest"]), ("selftest-pipeline", [PY, "pipeline.py", "selftest"]), ("selftest-manifest", [PY, "harness/manifest.py", "selftest"]),
        ("selftest-shadow", [PY, "harness/shadow_diff.py", "selftest"]), ("selftest-memo", [PY, "experiments/memo_audit.py", "selftest"]), ("selftest-tune", [PY, "tune.py"]), ("selftest-n_visual", [PY, "n_visual.py"])]
ACC = PH / "check_accepted"
WAIVED_EXISTS = {64, 33}      # 64 데뷔방송 앞 5분 예외, 33 등록부 N 로 막힌 회복 가능 곡: 둘 다 못 맞추는 상태를 알고 허용한다(HANDOFF 31절)


def sh(cmd, timeout=900):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr)


def step_selftest():
    bad = []
    for name, cmd in SELF:
        rc, out = sh(cmd, 300)
        if rc:
            bad.append(f"{name}: {out.strip().splitlines()[-1][:80] if out.strip() else rc}")
    return not bad, f"{len(SELF) - len(bad)}/{len(SELF)} 통과" + (f" 실패 {bad}" if bad else "")


def step_golden():
    rc, out = sh([PY, "experiments/golden_gate.py"])
    line = [l for l in out.splitlines() if l.startswith(("golden ", "recall "))]
    return rc == 0, ("  ".join(line) if line else out.strip()[-120:])


def step_memo():
    sys.path.insert(0, str(ROOT / "experiments"))
    import memo_audit as M
    exp = M.jl(M.EXP)
    s = M.summarize(M.evaluate(exp, M.load_src("engine_rev", exp)))      # engine_rev = make_final 과 같은 정책(S3 시작 제안은 auto 가 아닌 곡에만)
    b = M.jl(M.BASE)["summary"]["engine_rev"]
    fails = [k for k in ("hit@0.5", "hit@3", "hit@10", "dir_pass", "ok_pass", "asym_pass") if s[k] < b[k]] + [k for k in ("vanished", "len_err_gt5") if s[k] > b[k]]
    if s["ok_pass"] != s["ok_n"]:
        fails.append("ok_pass<ok_n")
    ex = [e["n"] for e in M.exists(exp) if not e["ok"]]                  # 메모가 '곡이 있어야 한다'고 한 구간이 drop 이면 실패. 아래 둘은 사용자 결정 대기라 지금은 허용(memo_audit.EXISTS 주석)
    if set(ex) - WAIVED_EXISTS:
        fails.append(f"exists 새 실패 {sorted(set(ex) - WAIVED_EXISTS)}")
    return not fails, f"hit@0.5/3/10 {s['hit@0.5']}/{s['hit@3']}/{s['hit@10']} (저장본 {b['hit@0.5']}/{b['hit@3']}/{b['hit@10']}) 방향 {s['dir_pass']}/{s['dir_n']} 좋음유지 {s['ok_pass']}/{s['ok_n']} 사라짐 {s['vanished']} 길이>5초 {s['len_err_gt5']} exists 실패(허용) {ex}" + (f" 퇴행 {fails}" if fails else "")


def step_logo():
    rc, out = sh([PY, "experiments/logo_route.py", "eval", "--by", "group", "--boot", "200", "--out", str(PH / "logo_check.json")])
    import re
    m = re.search(r"배포 규칙 표본 내.*?blind9: N 노출 (\d+)/(\d+) 라이브 걸림 (\d+)/(\d+)", out)
    if rc or not m:
        return False, ("logo_route 실패(규칙 A 재현 또는 라이브 걸림 assert) " + out.strip()[-150:])
    ne, lost = int(m[1]), int(m[3])
    rc2, out2 = sh([PY, "experiments/integ_holdout.py", "eval"])                      # A 의 머리 수치(integration.md 0절): 배포 경로 vis(4_scene)까지 얹은 blind9 N 노출
    v = re.search(r"배포 경로 vis.*?A \+ n_visual 배포 임계\(표본 내\)\s+노출\s+(\d+)\s+라이브 손실\s+(\d+)", out2, re.S)
    if rc2 or not v:
        return False, "integ_holdout eval 실패 " + out2.strip()[-150:]
    return ne <= 14 and lost == 0 and int(v[1]) <= 11 and int(v[2]) == 0, f"배포 규칙 blind9 N 노출 오디오만 {ne}/{m[2]} (기준 14 이하), + 화면(4_scene vis) {v[1]}/{m[2]} (기준 11 이하) 라이브 걸림 {lost}/{m[4]}, 화면 포함 라이브 손실 {v[2]}, 규칙 A 재현"


def step_drift(accept=False):
    import harness.manifest as M
    import harness.shadow_diff as SD
    from harness.replay import load_cards, labels
    r = M.Run()
    t = time.perf_counter(); P = r.run(seed_scratch(root=r.root))
    cur = load_cards()
    if accept or not ACC.exists():
        ACC.mkdir(exist_ok=True)
        json.dump(cur, open(ACC / "cards.json", "w", encoding="utf8"), ensure_ascii=False)
        return True, f"기준 저장 {len(cur)}카드 (재계산 단계 {sum(len(v) for v in P.values())}개, {time.perf_counter() - t:.1f}초)"
    old = json.load(open(ACC / "cards.json", encoding="utf8"))
    ra = [(c["tier"], c["likely"], c["weak"], c["tier_why"]) for c in old]
    rb = [(c["tier"], c["likely"], c["weak"], c["tier_why"]) for c in cur]
    rep = SD.diff(old, cur, ra, rb, labels(cur), labels(old))
    mv = [k for k, v in rep["transitions"].items() if k.split("->")[0] != k.split("->")[1]]
    msg = f"기준 대비 바뀐 후보 {len(rep['changed'])}, 경계 이동(1초 초과) {len(rep['moved'])}, 이탈 {len(rep['violations'])}" + (f" 등급 이동 {mv}" if mv else "") + f" (재계산 단계 {sum(len(v) for v in P.values())}개)"
    for v in rep["violations"][:5]:
        msg += f"\n      {v['kind']}: {v['slug']} @{v['start']} [{v['lab']}] {v['a']} -> {v['b']}"
    return not rep["violations"], msg


STEPS = dict(selftest=step_selftest, golden=step_golden, memo=step_memo, logo=step_logo, drift=step_drift)


def child(name):
    t = time.perf_counter()
    try:
        ok, msg = STEPS[name](accept="--accept" in sys.argv) if name == "drift" else STEPS[name]()
        out = dict(step=name, status="pass" if ok else "fail", msg=msg, sec=round(time.perf_counter() - t, 1))
    except Exception as e:
        out = dict(step=name, status="error", msg=f"{type(e).__name__}: {str(e)[:200]}", sec=round(time.perf_counter() - t, 1))
    print(json.dumps(out, ensure_ascii=False))


def main():
    fast = "--fast" in sys.argv
    names = [n for n in STEPS if not (fast and n in ("memo", "logo"))]
    if "--accept" in sys.argv:
        names = ["drift"]
    t0 = time.perf_counter()

    def go(n):
        r = subprocess.run([PY, str(Path(__file__)), "--step", n] + (["--accept"] if "--accept" in sys.argv else []), capture_output=True, text=True, cwd=ROOT, timeout=1800)
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            return dict(step=n, status="error", msg=(r.stderr or r.stdout)[-200:], sec=0)
    with ThreadPoolExecutor(len(names)) as ex:
        res = list(ex.map(go, names))
    wall = time.perf_counter() - t0
    print("| 단계 | 결과 | 초 | 내용 |\n|---|---|---|---|")
    for r in res:
        print(f"| {r['step']} | {r['status']} | {r['sec']} | {r['msg']} |")
    code = 2 if any(r["status"] == "error" for r in res) else (1 if any(r["status"] == "fail" for r in res) else 0)
    print(f"\n전체 {wall:.1f}초 (병렬), 종료코드 {code}")
    json.dump(dict(wall=round(wall, 1), code=code, steps=res), open(PH / "check_last.json", "w"), ensure_ascii=False, indent=1)
    return code


if __name__ == "__main__":
    if "--step" in sys.argv:
        child(sys.argv[sys.argv.index("--step") + 1])
    else:
        sys.exit(main())
