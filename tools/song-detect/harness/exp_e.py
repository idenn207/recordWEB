"""축 (e) 섀도 diff 시험: 실제 규칙 변경 3종 + 경계 규칙 변경 1종을 diff 도구로 요약하고 시간과 종료코드를 기록한다. 소스 수정은 try/finally 로 원복.
사용: python harness/exp_e.py snap|decisions"""
import json, os, sys, time, io, contextlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.lib import *
import harness.shadow_diff as SD

res = {}
def run(name, argv):
    buf = io.StringIO(); t = time.perf_counter()
    with contextlib.redirect_stdout(buf):
        rc = SD.main(argv)
    dt = time.perf_counter() - t
    print(f"=== {name} (종료코드 {rc}, {dt:.1f}초)\n{buf.getvalue()}")
    res[name] = dict(rc=rc, sec=round(dt, 2), out=buf.getvalue())

if sys.argv[1] == "decisions":
    run("신호 끔(P6 이전과 유사)", ["--registry-off", "--set", "np.rel_db=-99", "--set", "np.bursts=99"])
    run("wait_s 300->600", ["--registry-off", "--set", "rp.wait_s=600"])
    run("motion 34.5->30", ["--registry-off", "--set", "mp.motion=30"])
    run("rel_db -5.7 -> -4.0", ["--registry-off", "--set", "np.rel_db=-4.0"])
elif sys.argv[1] == "snap2":                                      # 규칙 E1b, E3 를 끈 B 루트(승인 곡 경계가 움직이는 큰 변경)
    import harness.manifest as M
    from blind9_bounds import patched
    root_b = PH / "out_m3"
    undo = patched({"E1b", "E3"})
    try:
        sl = seed_scratch(root=root_b)
        r = M.Run(root_b); t = time.perf_counter(); r.run(sl); print("B 루트 생성", round(time.perf_counter() - t, 1), "초", r.n)
    finally:
        undo()
    run("E1b,E3 끔 (경계 규칙)", ["--root-a", str(PH / "out_m"), "--root-b", str(root_b)])
else:
    import harness.manifest as M
    p = ROOT / "snap.py"; src = p.read_text(encoding="utf8")
    root_b = PH / "out_m2"
    try:
        p.write_text(src.replace("BACK, FWD, MARGIN = 8.0, 15.0, 2.0", "BACK, FWD, MARGIN = 8.0, 20.0, 2.0", 1), encoding="utf8")
        sl = seed_scratch(root=root_b)
        r = M.Run(root_b); t = time.perf_counter(); r.run(sl); print("B 루트 생성", round(time.perf_counter() - t, 1), "초", r.n)
    finally:
        p.write_text(src, encoding="utf8")
    run("snap FWD 15->20 (경계 규칙)", ["--root-a", str(PH / "out_m"), "--root-b", str(root_b)])
json.dump(res, open(PH / f"exp_e_{sys.argv[1]}.json", "w"), ensure_ascii=False, indent=1)
