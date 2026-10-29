"""축 (e) 섀도 모드/드리프트 리포트: 규칙 변경 전(A)과 후(B)의 결과를 같은 후보 집합에서 비교해 등급 변화, 승인 라이브 이탈, N 노출 변화, 경계 이동을 요약한다.
두 가지 입력:
  (1) 결정 변경: 카드 v2 를 replay 로 두 번 계산(A = 현행, B = --set 로 덮어쓴 규칙). 초 단위, wav/NAS 불필요.
        python harness/shadow_diff.py --set np.rel_db=-5.0 --set mp.motion=30 [--registry-off]      (rp.* = route.P, mp.* = scene_multi.P, np.* = n_signals.P)
  (2) 경계 규칙 변경: 매니페스트 루트 두 개(A, B)의 cards2.json 을 읽어 비교(snap 을 고친 뒤 manifest.Run(root_B).run() 으로 만든 것).
        python harness/shadow_diff.py --root-a cache/proto_harness/out_m --root-b cache/proto_harness/out_m2
이탈 기준(종료코드 1): 승인 라이브(L,B 라벨)가 낮은 등급이 되거나 weak 로 숨겨짐 / N 라벨이 새로 auto 로 오름 / 승인 곡 경계가 2초 넘게 이동.  등급 변화만 있으면 0(보고만).
출력: 표준출력 마크다운 + --json 경로. 종료코드 0 변화 허용 범위, 1 이탈, 2 사용 오류.
shortcut: 라벨은 등록부(approved/known_negatives)에서 만든 NAS 191후보 라벨이라 다른 방송 세트의 이탈은 golden_gate 가 본다. 두 입력의 후보는 (슬러그, 시작 0.1초 반올림)이 아니라 카드 순서(idx)와 겹침 50%로 맞춘다."""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.lib import *
from harness.replay import load_cards, labels, Replayer, RK


def vis(t, weak):
    return 2 if t == "auto" else (1 if t in ("review", "optional") and not weak else 0)       # 완성본 노출 수준: auto 2 > 노출 review 1 > 숨김/drop 0


def match(ca, cb):
    """B 카드마다 겹침이 가장 큰 A 카드의 인덱스(50% 이상, 같은 슬러그), 없으면 None"""
    by = {}
    for i, c in enumerate(ca):
        by.setdefault(c["slug"], []).append(i)
    out = []
    for c in cb:
        best, bo = None, 0.0
        for i in by.get(c["slug"], []):
            a = ca[i]
            ov = min(a["end"], c["end"]) - max(a["start"], c["start"])
            if ov > bo and ov >= 0.5 * min(a["end"] - a["start"], c["end"] - c["start"]):
                best, bo = i, ov
        out.append(best)
    return out


def diff(ca, cb, ra, rb, lab_b, lab_a=None):
    """ra, rb = [(tier, likely, weak, why)] , lab_b = B 카드별 라벨, lab_a = A 카드별 라벨(주면 B 에 대응 카드가 없는 승인 라이브 A 카드를 이탈로 센다). 반환 dict(리포트)"""
    mt = match(ca, cb)
    trans, chg, viol, moved = {}, [], [], []
    for j, i in enumerate(mt):
        a = ra[i] if i is not None else ("(없음)", False, False, "")
        b = rb[j]
        k = f"{a[0]}->{b[0]}"
        trans[k] = trans.get(k, 0) + 1
        if i is None or (a[0], a[2]) != (b[0], b[2]) or a[1] != b[1]:
            row = dict(slug=cb[j]["slug"], start=round(cb[j]["start"]), lab=lab_b[j], a=f"{a[0]}{'/weak' if a[2] else ''}{'/likely' if a[1] else ''}", b=f"{b[0]}{'/weak' if b[2] else ''}{'/likely' if b[1] else ''}", why=b[3][:40])
            chg.append(row)
            if lab_b[j] in ("L", "B") and vis(b[0], b[2]) < vis(a[0], a[2]):
                viol.append(dict(row, kind="승인 라이브 노출 하락"))
            if lab_b[j] == "N" and b[0] == "auto" and a[0] != "auto":
                viol.append(dict(row, kind="N 이 auto 로"))
        if i is not None:
            s0, e0, s1, e1 = ca[i]["start"], ca[i]["end"], cb[j]["start"], cb[j]["end"]
            if max(abs(s1 - s0), abs(e1 - e0)) > 1:
                moved.append(dict(slug=cb[j]["slug"], start=round(s1), lab=lab_b[j], ds=round(s1 - s0, 1), de=round(e1 - e0, 1), why=("A: " + (ca[i]["boundary"].get("why_snap") or "-"))[:60]))
            if lab_b[j] in ("L", "B") and max(abs(s1 - s0), abs(e1 - e0)) > 2:
                viol.append(dict(slug=cb[j]["slug"], start=round(s1), lab=lab_b[j], kind="승인 곡 경계 이동", a=f"{s0:.1f}-{e0:.1f}", b=f"{s1:.1f}-{e1:.1f}", why=""))
    seen = {i for i in mt if i is not None}
    for i in range(len(ca)):
        if lab_a and i not in seen and lab_a[i] in ("L", "B") and vis(ra[i][0], ra[i][2]) > 0:      # 노출되던 승인 라이브 카드가 B 에서 통째로 사라짐
            viol.append(dict(slug=ca[i]["slug"], start=round(ca[i]["start"]), lab=lab_a[i], kind="승인 라이브 카드 사라짐", a=f"{ra[i][0]}", b="(없음)", why=""))
    lost_a = sum(i is None for i in mt)
    return dict(transitions=trans, changed=chg, violations=viol, moved=moved, new_in_b=lost_a, n_a=len(ca), n_b=len(cb))


def summary(ca, cb, ra, rb, lab_a, lab_b):
    def cnt(c, r, lab):
        v = lambda x: x[0] == "auto" or (x[0] in ("review", "optional") and not x[2])
        return dict(auto=sum(x[0] == "auto" for x in r), review=sum(x[0] == "review" for x in r), drop=sum(x[0] == "drop" for x in r), likely=sum(x[1] for x in r),
                    N_expose=sum(l == "N" and v(x) for l, x in zip(lab, r)), live_hidden=sum(l in ("L", "B") and not v(x) for l, x in zip(lab, r)))
    return dict(A=cnt(ca, ra, lab_a), B=cnt(cb, rb, lab_b))


def render(rep, sm):
    L = ["# 섀도 diff", f"후보 A {rep['n_a']} -> B {rep['n_b']} (B 에만 있는 후보 {rep['new_in_b']})", "", "| | auto | review | drop | likely | N 노출 | 숨겨진 라이브(L,B) |", "|---|---|---|---|---|---|---|"]
    for k in ("A", "B"):
        s = sm[k]; L.append(f"| {k} | {s['auto']} | {s['review']} | {s['drop']} | {s['likely']} | {s['N_expose']} | {s['live_hidden']} |")
    L += ["", "등급 이동: " + (", ".join(f"{k} {v}" for k, v in sorted(rep["transitions"].items()) if k.split("->")[0] != k.split("->")[1]) or "없음"), f"바뀐 후보 {len(rep['changed'])}개"]
    for r in rep["changed"][:15]:
        L.append(f"  - {r['slug']} @{r['start']} [{r['lab']}] {r['a']} -> {r['b']} {r['why']}")
    L.append(f"경계가 1초 넘게 이동한 후보 {len(rep['moved'])}개" + ("" if not rep["moved"] else ":"))
    for r in rep["moved"][:15]:
        L.append(f"  - {r['slug']} @{r['start']} [{r['lab']}] 시작 {r['ds']:+.1f} 끝 {r['de']:+.1f} ({r['why']})")
    L.append(f"이탈 {len(rep['violations'])}건" + ("" if not rep["violations"] else ":"))
    for r in rep["violations"]:
        L.append(f"  - {r['kind']}: {r['slug']} @{r['start']} [{r['lab']}] {r['a']} -> {r['b']}")
    return "\n".join(L)


def parse_set(items):
    kw = {"rp": {}, "mp": {}, "npp": {}}
    for it in items or []:
        k, v = it.split("=")
        grp, name = k.split(".")
        kw["npp" if grp == "np" else grp][name] = float(v)
    return kw


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", action="append")
    ap.add_argument("--registry-off", action="store_true")
    ap.add_argument("--root-a")
    ap.add_argument("--root-b")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    if a.root_a and a.root_b:
        ca, cb = load_cards(Path(a.root_a)), load_cards(Path(a.root_b))
        ra = [(c["tier"], c["likely"], c["weak"], c["tier_why"]) for c in ca]
        rb = [(c["tier"], c["likely"], c["weak"], c["tier_why"]) for c in cb]
        la, lb = labels(ca), labels(cb)
    elif a.set or a.registry_off:
        ca = cb = load_cards()
        la = lb = labels(ca)
        rp = Replayer(ca)
        ra = rp.run(registry=not a.registry_off)
        rb = rp.run(registry=not a.registry_off, **parse_set(a.set))
    else:
        print("--set 또는 --root-a/--root-b 가 필요", file=sys.stderr)
        return 2
    rep = diff(ca, cb, ra, rb, lb, la)
    sm = summary(ca, cb, ra, rb, la, lb)
    print(render(rep, sm))
    if a.json:
        json.dump(dict(rep, summary=sm), open(a.json, "w"), ensure_ascii=False, indent=1)
    return 1 if rep["violations"] else 0


def selftest():
    c = lambda s, e, sl="x": dict(slug=sl, start=s, end=e, boundary={})
    ca, cb = [c(0, 100), c(200, 300)], [c(0.5, 100), c(200, 310)]
    assert match(ca, cb) == [0, 1] and match(ca, [c(1000, 1100)]) == [None]
    ra = [("auto", False, False, ""), ("review", True, False, "")]
    rb = [("review", False, False, "x"), ("review", True, False, "")]
    rep = diff(ca, cb, ra, rb, ["L", "N"])
    assert len(rep["violations"]) == 1 and rep["violations"][0]["kind"] == "승인 라이브 노출 하락", rep
    rep = diff(ca, cb, ra, ra, ["L", "N"])
    assert not rep["violations"] and not rep["changed"]
    rep = diff([c(0, 100)], [], ra[:1], [], [], ["L"])                  # B 에 대응 카드가 없는 노출 승인 라이브 A 카드 = 이탈
    assert [v["kind"] for v in rep["violations"]] == ["승인 라이브 카드 사라짐"], rep
    assert not diff([c(0, 100)], [], [("drop", False, False, "")], [], [], ["L"])["violations"]      # 원래 안 보이던 카드는 아님
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:2] == ["selftest"]:
        selftest(); sys.exit()
    sys.exit(main())
