"""축 (f) 상시 점검 한 번에: golden gate + 메모 감사 게이트 + logo_route + 자가검사/테스트 + 변화 리포트(섀도 diff)를 병렬로 돌리고 한 표로 요약한다.
  python harness/check.py            전체 (병렬, 약 20초)
  python harness/check.py --fast     메모 감사, logo_route 를 건너뜀 (규칙 편집 중 빠른 확인)
  python harness/check.py --accept   지금 결과를 '승인된 기준'(변화 리포트 비교 기준)으로 저장. 의도한 변경을 확인한 뒤에만
  python harness/check.py --rescene  golden 게이트 전에 치지직 번호 golden 방송 12개(통합 전 4_scene.json)의 장면 단계를 현재 코드로 다시 계산(약 13분, 인터넷). 장면 규칙(scene_multi, scene, black_max, 풀)을 바꾼 뒤에 쓴다
  python harness/check.py --step 이름  단계 하나만(내부용, 마지막 줄이 JSON)
종료코드: 0 전부 통과 / 1 게이트 실패(승인 라이브 이탈, 메모 감사 퇴행, logo_route 퇴행, 테스트 실패, 변화 리포트 이탈) / 2 점검 자체 오류(단계가 예외로 죽음, 파일 없음).
게이트 기준: golden 이탈 0 / 메모 감사 hit@0.5,3,10 · 방향 통과 · 경계 좋음 유지가 저장본(memo_audit_baseline.json) 이상, 곡 사라짐 0, 길이 오차>5초 곡이 저장본 이하 /
 logo_route 가 규칙 A 재현(노출 23/weak 22/drop 10)과 배포 규칙 라이브 걸림 0 을 assert 하고, 배포 규칙 blind9 N 노출(오디오만, + 화면: integ_holdout eval 의 배포 경로 vis)이 저장본(check_accepted/logo_sets.json)에 없던 N 곡을 새로 노출하지 않고 라이브 손실 0 (개수는 보고만) / 변화 리포트: 승인 라이브 노출 하락, N 이 auto 로, 승인 곡 경계 2초 초과 이동 없음.
출력 요약은 cache/proto_harness/check_last.json 에도 저장(CI 아티팩트용).
shortcut: 변화 리포트의 기준 스냅샷은 cache/proto_harness/check_accepted(첫 실행 때 자동 승인), 라벨은 NAS 10월 191후보뿐이라 다른 방송 세트는 golden 이 맡는다."""
import json, os, shutil, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.lib import *

PY = sys.executable
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")          # 자식 출력과 부모 디코딩을 UTF-8 로 통일: 콘솔 인코딩(cp949 등)이 달라도 한국어 출력 디코딩이 예외로 죽지 않게(리뷰 B-5)
RUN = dict(capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
SELF = [("selftest-route", [PY, "test_route.py"]), ("selftest-detect", [PY, "test_detect.py"]), ("selftest-snap", [PY, "snap.py", "selftest"]), ("selftest-finalize", [PY, "finalize.py", "selftest"]),
        ("selftest-make_final", [PY, "make_final.py", "selftest"]), ("selftest-pipeline", [PY, "pipeline.py", "selftest"]), ("selftest-manifest", [PY, "harness/manifest.py", "selftest"]),
        ("selftest-shadow", [PY, "harness/shadow_diff.py", "selftest"]), ("selftest-memo", [PY, "experiments/memo_audit.py", "selftest"]), ("selftest-tune", [PY, "tune.py"]), ("selftest-n_visual", [PY, "n_visual.py"]), ("selftest-holdout", [PY, "experiments/integ_holdout.py", "selftest"]), ("selftest-check", [PY, "harness/check.py", "--selftest"])]
ACC = PH / "check_accepted"
GS = PH / "golden_scene"      # --rescene 스크래치
WAIVED_EXISTS = {64, 33}      # 64 데뷔방송 앞 5분 예외, 33 등록부 N 로 막힌 회복 가능 곡: 둘 다 못 맞추는 상태를 알고 허용한다(HANDOFF 31절)


def sh(cmd, timeout=900):
    r = subprocess.run(cmd, timeout=timeout, env=ENV, **RUN)
    return r.returncode, (r.stdout + r.stderr)


def step_selftest():
    bad = []
    for name, cmd in SELF:
        rc, out = sh(cmd, 300)
        if rc:
            bad.append(f"{name}: {out.strip().splitlines()[-1][:80] if out.strip() else rc}")
    return not bad, f"{len(SELF) - len(bad)}/{len(SELF)} 통과" + (f" 실패 {bad}" if bad else "")


def rescene_golden():
    """치지직 번호 golden 방송의 4_scene.json 은 통합 전(10-25) 산출물이라 golden_gate 가 장면 규칙 변경을 못 본다(리뷰 A2-4). 단계 파일 3개를 스크래치로 복사하고 pipeline.py 의 장면 단계만 현재 코드와 현재 장면 풀로 다시 돌린다(클립 없음, 144p 프레임은 인터넷, 약 13분).
    저장본과 달라지는 것은 규칙뿐 아니라 장면 풀 변화도 포함한다(has_refs 가 달라지는 방송이 있다). 요약 문자열을 돌려준다.
    shortcut: 144p 프레임은 읽기에 실패하는 경우가 있어(15761307 은 저장본에서도 후보 12개 중 6개가 비었다) 비는 후보가 저장본보다 방송당 2개 넘게 늘면 실패로 본다. vis(GPU)는 이 python 에 torch 가 없으면 건너뛴다: golden 게이트는 vis 를 안 본다."""
    vids = sorted({g["vid"] for g in json.load(open(ROOT / "experiments/golden_v4.json", encoding="utf8"))["songs"] if g["vid"].isdigit()})
    load = lambda p: json.load(open(p, encoding="utf8"))
    blank = lambda p: sum(g.get("tstd") is None for g in load(p)["segs"] if g.get("keep"))

    def one(v):
        d = GS / v
        shutil.rmtree(d, ignore_errors=True); d.mkdir(parents=True)
        for f in STAGE_FILES[:3]:
            shutil.copy(ROOT / "out" / v / f, d / f)
        r = subprocess.run([PY, "pipeline.py", f"data/vod/{v}.wav", "--id", v, "--out", str(GS)], timeout=3600, env=dict(ENV, SONG_NOCLIP="1"), **RUN)
        assert r.returncode == 0, f"{v}: pipeline 장면 단계 실패 {r.stderr.strip()[-150:]}"
        a, b = blank(d / "4_scene.json"), blank(ROOT / "out" / v / "4_scene.json")
        assert a <= b + 2, f"{v}: 프레임을 못 읽은 후보가 저장본 {b}개에서 {a}개로 늘었다(네트워크 확인)"
        return a, b, load(d / "4_scene.json")["has_refs"] != load(ROOT / "out" / v / "4_scene.json")["has_refs"]
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(one, vids))
    return f"rescene {len(vids)}개 방송(프레임 못 읽은 후보 {sum(r[0] for r in res)}, 저장본 {sum(r[1] for r in res)}, has_refs 달라진 방송 {sum(r[2] for r in res)})"


def step_golden():
    cmd, pre = [PY, "experiments/golden_gate.py"], []
    if "--rescene" in sys.argv:
        pre = [rescene_golden()]
        cmd += ["--scene-root", str(GS)]
    rc, out = sh(cmd, 3600)
    line = pre + [l for l in out.splitlines() if l.startswith(("golden ", "recall "))]
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


def step_logo(accept=False):
    """배포 규칙의 blind9 N 노출을 '곡 집합'으로 저장본(ACC/logo_sets.json)과 비교한다: 새로 노출된 N 곡과 라이브 손실만 이탈로 세고, 개수는 보고만 한다(임계 근처 N 몇 곡 때문에 개수 단언은 거짓 실패/개선을 냈다, 리뷰 A2-6).
    집합 둘: 오디오+구조 규칙(logo_route 의 배포 규칙, 신호 표) / 거기에 화면(integ_holdout 의 배포 경로 vis)을 얹은 것. --accept 일 때만 현재 집합을 저장(라이브 손실이 있으면 저장 거부, 저장본이 없으면 실패)."""
    rc, out = sh([PY, "experiments/logo_route.py", "eval", "--by", "group", "--boot", "200", "--out", str(PH / "logo_check.json")])
    import re
    m = re.search(r"배포 규칙 표본 내.*?blind9: N 노출 (\d+)/(\d+) 라이브 걸림 (\d+)/(\d+)", out)
    if rc or not m:
        return False, ("logo_route 실패(규칙 A 재현 또는 라이브 걸림 assert) " + out.strip()[-150:])
    import contextlib, io
    sys.path.insert(0, str(ROOT / "experiments"))
    import integ_holdout as IH                                                       # A 의 머리 수치(integration.md 0절): 배포 경로 vis(4_scene)까지 얹은 blind9 N 노출
    with contextlib.redirect_stdout(io.StringIO()):
        o = IH.evaluate(True)
    k, lost_all = o["blind9"]["keys"], o["전체"]["keys"]["lost"]                  # 전체 = 라이브 풀 136(golden 라이브 포함): golden_gate 가 못 보는 weak/vis 로 인한 승인 라이브 손실도 여기서 센다
    f, ne = ACC / "logo_sets.json", int(m[1])
    assert ne == len(k["A"]), f"logo_route({ne})와 integ_holdout({len(k['A'])})의 배포 규칙 노출이 다르다"
    if int(m[3]) or k["lost"] or lost_all:                                           # 라이브 손실은 저장본 유무와 --accept 와 무관하게 이탈이고, 손실이 있는 상태를 기준으로 저장하지 않는다(리뷰 B-1)
        return False, f"라이브 손실: blind9 걸림 {m[3]}/{m[4]}, 화면 포함 {k['lost']}, 라이브 풀 136 전체 {lost_all} (기준 저장 안 함)"
    if accept:
        ACC.mkdir(exist_ok=True)
        json.dump(k, open(f, "w", encoding="utf8"), ensure_ascii=False, indent=1)
        return True, f"기준 저장: 노출 오디오만 {len(k['A'])}, + 화면 {len(k['A_vis'])}, 라이브 걸림 {m[3]}/{m[4]}, 화면 포함 라이브 손실 {len(k['lost'])}"
    if not f.exists():                                                               # 저장본이 없으면 새 노출 N 비교가 빈 검사가 된다: 조용히 만들지 않고 명시적 초기화를 요구
        return False, f"저장본 {f.name} 없음: python harness/check.py --accept 로 초기화"
    old = json.load(open(f, encoding="utf8"))
    new = {s: sorted(set(k[s]) - set(old[s])) for s in ("A", "A_vis")}
    gone = {s: sorted(set(old[s]) - set(k[s])) for s in ("A", "A_vis")}
    ok = not new["A"] and not new["A_vis"]
    msg = f"배포 규칙 blind9 N 노출 오디오만 {len(k['A'])}/{m[2]} (저장본 {len(old['A'])}), + 화면(4_scene vis) {len(k['A_vis'])}/{m[2]} (저장본 {len(old['A_vis'])}) 라이브 걸림 {m[3]}/{m[4]}, 화면 포함 라이브 손실 {len(k['lost'])} (라이브 풀 136 전체 {len(lost_all)}), 규칙 A 재현"
    if new["A"] or new["A_vis"]:
        msg += f" | 새로 노출된 N 오디오만 {new['A']} 화면포함 {new['A_vis']}"
    if gone["A"] or gone["A_vis"]:
        msg += f" | 노출에서 빠진 N(개선, 확인 후 --accept) 오디오만 {gone['A']} 화면포함 {gone['A_vis']}"
    return ok, msg


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


def selftest():
    """step_logo 의 라이브 손실/저장본 규칙(리뷰 B-1)을 가짜 평가 값으로 확인한다"""
    import tempfile
    from unittest.mock import patch
    sys.path.insert(0, str(ROOT / "experiments"))
    import integ_holdout as IH
    me = sys.modules[__name__]
    ev = lambda lost: {"blind9": dict(keys=dict(A=["n"], A_vis=["n"], lost=lost)), "전체": dict(keys=dict(lost=lost))}

    def logo(lost, acc, accept=False):
        with patch.object(me, "ACC", acc), patch.object(me, "sh", return_value=(0, "배포 규칙 표본 내 blind9: N 노출 1/55 라이브 걸림 0/49")), patch.object(IH, "evaluate", return_value=ev(lost)):
            return step_logo(accept)[0]
    acc = Path(tempfile.mkdtemp())
    assert not logo(["L"], acc) and not logo(["L"], acc, True) and not (acc / "logo_sets.json").exists()     # 라이브 손실: 저장본이 없어도 --accept 여도 실패하고 저장하지 않는다
    assert not logo([], acc) and logo([], acc, True) and logo([], acc) and not logo(["L"], acc)              # 저장본 없음은 실패, --accept 로 초기화하면 통과, 이후 손실이 생기면 다시 실패
    print("ok")


STEPS = dict(selftest=step_selftest, golden=step_golden, memo=step_memo, logo=step_logo, drift=step_drift)


def child(name):
    t = time.perf_counter()
    try:
        ok, msg = STEPS[name](accept="--accept" in sys.argv) if name in ("logo", "drift") else STEPS[name]()
        out = dict(step=name, status="pass" if ok else "fail", msg=msg, sec=round(time.perf_counter() - t, 1))
    except Exception as e:
        out = dict(step=name, status="error", msg=f"{type(e).__name__}: {str(e)[:200]}", sec=round(time.perf_counter() - t, 1))
    print(json.dumps(out, ensure_ascii=False))


def main():
    sys.stdout.reconfigure(errors="replace")                                # 콘솔 인코딩이 못 쓰는 글자가 자식 출력에 있어도 요약 표 출력이 죽지 않게
    fast = "--fast" in sys.argv
    names = [n for n in STEPS if not (fast and n in ("memo", "logo"))]
    if "--accept" in sys.argv:
        names = ["logo", "drift"]
    t0 = time.perf_counter()

    def go(n):
        r = subprocess.run([PY, str(Path(__file__)), "--step", n] + [o for o in ("--accept", "--rescene") if o in sys.argv], timeout=3600, env=ENV, **RUN)
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except Exception:
            return dict(step=n, status="error", msg=(r.stderr or r.stdout or "")[-200:], sec=0)
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
    if "--selftest" in sys.argv:
        selftest()
    elif "--step" in sys.argv:
        child(sys.argv[sys.argv.index("--step") + 1])
    else:
        sys.exit(main())
