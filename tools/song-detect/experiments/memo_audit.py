"""메모 감사: 사용자 메모(blind9 labels.json 145행)를 점검 항목으로 구조화(expectations.json)하고, 규칙 버전 전/후를 자동 대조한다.
점검 항목: (1) 경계 시각 hit@0.5/3/10초(시작/끝, 메모 시각 + 오디오/재생목록으로 확정한 값, 사용자가 '경계 좋음'이라 한 쪽은 v3 경계 유지), (2) 곡 길이 오차,
(3) 방향(early/late 지적 쪽으로 1초 이상 이동), (4) 곡 사라짐, (5) 화면 tag 별 게이트 예측(등록부 켠/끈 두 조건), (6) 한 곡의 stale 쌍 병합,
(7) 이동 >1초 경계의 규칙 이름 귀속률(attrib), (8) 곡이 있어야 하는 구간(exists). 귀로 들어야 하는 항목은 unverifiable 로 센다(자동 판정 안 함).
사용: python experiments/memo_audit.py build                       # expectations.json 생성 (data/ 는 gitignore)
      python experiments/memo_audit.py [before] [after] [--save]    # 기본 before=out/stale_v3 after=out/final,out/final_review. 소스 = 폴더/json 쉼표 목록 또는 engine(현재 코드로 refine 후보 재계산)
      python experiments/memo_audit.py attrib                       # 전 방송 keep 후보의 >1초 이동 귀속률(약 2분)
      python experiments/memo_audit.py selftest
--save 는 data/review/blind9/audit/memo_audit_baseline.json 에 쓰고, 이후 실행은 저장본과 다른 지표를 같이 보여 준다(P2/P6 전후 비교의 기준).
shortcut: 메모 숫자 판독과 오디오 확정값은 사람이 만든 표(AUDIO, REL)라 새 메모는 직접 추가해야 한다. 오디오 값은 지난 자체 검수(audit g1~g4)가 파형으로 확인한 것이고 귀로 들은 것이 아니다."""
import sys, os, json, re, gc
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
os.chdir(ROOT)
import tune  # SONG_TUNE 환경변수가 있으면 상수 오버라이드(tune.py 참고), 없으면 아무 일도 안 한다
import numpy as np

BD = ROOT / "data/review/blind9"
EXP, BASE = BD / "expectations.json", BD / "audit/memo_audit_baseline.json"
TOLS, TOL, OKTOL = (0.5, 3.0, 10.0), 1.0, 2.0      # hit 임계(초), 방향 판정 최소 이동, '경계 좋음' 유지 한도(blind9_bounds 와 같은 값)

# 오디오로 초 단위 확정한 경계(wav 시간축, 메모가 지적한 쪽만). 근거는 data/review/blind9/audit/g*.json. 대략값(18 22 50 63 65 82 144)은 넣지 않는다.
AUDIO = {20: {"start": (10841.6, "무음(-95dB)에서 곡 시작, 곡 337.9초 = 메모 '5분 정도'"), "end": (11179.5, "소리 절벽")},
         23: {"end": (28910.5, "곡 소리가 -25 -> -80dB 로 끊김, 승인 끝과 0.9초")},
         25: {"end": (29331.5, "보컬 29250 뒤 MR 아웃트로, MR 정지 후 멘트")},
         53: {"start": (23283.2, "-44dB 딥 뒤 저음량 MR 전주 시작, 메모 '약 5초 앞'과 1.7초 차")}}
# 시각 확인(cache/audit/p3 스펙트로그램, 0.5초 rms)으로 20 시작 10841.5, 24 끝 28910.5 절벽, 26 끝 29331.5(Music 0.85 -> 0.03 + 말), 54 시작 MR 전주(-44dB 딥 뒤)를 재확인했다.
# 141/142 끝 4973.3 은 감쇠 구간이라 +-3초 불확실(4971~4976.5)해 뺐다.
REL = {37: ("end", 125), 108: ("start", 19)}        # 메모 mm:ss 를 클립 상대초로(N 행, 참고용: 클립 시작 = v3 json 의 vod_start)
# 사용자 답이 아직 없어 규칙을 바꾸지 않는 항목(현재 동작 유지). 감사표에 unresolved 로만 기록한다.
UNRESOLVED = {18: "메모 '1분 끊김'과 오디오(+19.5초만 확인)가 어긋남(P2 의 일반 규칙 E1b 가 +19.5초 연장, 1분은 여전히 미확인)", 22: "재생목록 25428.6 / 오디오 이음매 25511 / 메모 약 1분이 서로 다름", 82: "오디오상 음악 끝 18074.4 에 컷이 맞음, 메모 '끝 전 잘림' 재현 안 됨",
              45: "재생목록 시작이 15.6초 앞(MR 전주 포함)인데 L: 전주 포함 선호인지 미확인"}
UNRESOLVED_ALL = "승인 시작이 음악 시작보다 15~25초 늦은 5곡(나나 10-06 25775 승인 시작 25774.35, 28389 등)의 의도 미확인: S3 류 시작 규칙은 auto 에 못 씀(P5 이후)"
# 지난 수동 자체 검수(audit g1~g4)의 숫자 정답 판정(pass=True). 자동 판정(asym)이 이것을 재현하는지 본다: 자르면 안 되는 쪽(시작이 늦음/끝이 이름) 1초, 남는 쪽 3초.
MANUAL = {(20, "start"): False, (20, "end"): False, (24, "end"): True, (26, "end"): False, (44, "start"): False, (47, "start"): True, (49, "start"): True, (49, "end"): True,
          (52, "start"): False, (54, "start"): False, (60, "end"): True, (111, "start"): False, (112, "end"): True}
CUT, EXTRA = 1.0, 3.0
EXISTS = [dict(n=64, start=80.0, end=284.0, want="not drop", why="메모: 방송 시작 3분쯤 라이브 1곡 더(데뷔방송 셋리스트), 앞 5분 규칙 예외")]


def name_of(slug):
    return re.sub(r"^\d+_[^_]+_", "", slug)


def ov(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def jl(p):
    return json.load(open(p, encoding="utf8"))


def build():
    from labels import BLIND9
    import audit_load
    L, K, BT = jl(BD / "labels.json"), jl(BD / "key.json"), {r["idx"]: r for r in jl(BD / "boundary_truth.json")}
    appr = [x for x in jl(ROOT / "data/approved.json") if x["src"].startswith("재생목록 위치 정답")]
    fkey = {v["file"]: k for k, v in K.items()}
    canon = {i: i for i, x in enumerate(L, 1) if x["file"] in fkey}
    for i, x in enumerate(L, 1):
        if i not in canon:
            c = [j for j in set(canon.values()) if L[j - 1]["slug"] == x["slug"] and ov(L[j - 1]["ss"], L[j - 1]["se"], x["ss"], x["se"]) > 0.5 * min(L[j - 1]["se"] - L[j - 1]["ss"], x["se"] - x["ss"])]
            assert len(c) == 1, (i, c)
            canon[i] = c[0]
    v3 = [j for j in audit_load.v3() if j.get("rule") == "v3-pad"]
    unv = {}
    for g in "g1", "g2", "g3", "g4":
        for r in jl(BD / f"audit/{g}.json")["rows"]:
            unv.setdefault(canon[r["n"]], []).extend(c["claim"] for c in r["checks"] if c["verdict"] == "unverifiable")
    groups = []
    for cg in sorted(set(canon.values())):
        mem = [i for i in canon if canon[i] == cg]
        rep = next((m for m in mem if BT.get(m, {}).get("eval")), cg)
        x, key = L[cg - 1], fkey[L[cg - 1]["file"]]
        labs = {L[m - 1]["lab"] for m in mem}
        lab = "N" if labs == {"N"} else "B" if "B" in labs else "L"
        memo = " / ".join(dict.fromkeys(L[m - 1]["memo"] for m in mem))
        b = BT.get(rep)
        base = [b["base_start"], b["base_end"]] if b else [x["ss"], x["se"]]
        vno = name_of(x["slug"])
        g = dict(gid=rep, rows=mem, key=key, slug=x["slug"], vno=vno, lab=lab, labs_mixed=len(labs) > 1, memo=memo, tag=BLIND9[key]["tag"] or "live", base=base,
                 complete=(False if re.search(r"완곡(이|은)? ?(안|되지|하지)|완곡 전|완곡 직전", memo) else True if re.search(r"완곡(은 하였|은 했|했)", memo) else None),
                 unverifiable=sorted(set(unv.get(cg, []))), unresolved=next((UNRESOLVED[m] for m in mem if m in UNRESOLVED), None), sides={})
        if re.search("싱크룸|4명", memo):
            g["tag"] = "sync_room"
        for side in ("start", "end"):
            iss = b[side + "_issue"] if b else None
            s = dict(issue=iss, truth=None, src=None, note=None)
            t = next((BT[m][side + "_true_abs"] for m in mem if m in BT and BT[m][side + "_true_abs"] is not None and not BT[m]["approx"]), None)
            if t is not None:
                s.update(truth=t, src="memo", note="메모 시각(클립 상대초 -> 방송 절대초)")
            for m in mem:
                if m in REL and REL[m][0] == side and t is None:
                    j = next(j for j in v3 if j["_slug"] == x["slug"] and abs(j["song_start"] - x["ss"]) < 2)
                    s.update(truth=j["vod_start"] + REL[m][1], src="memo", note=f"메모 {REL[m][1]}초(클립 상대), N 행 참고용")
                if side in AUDIO.get(m, {}):
                    s.update(truth=AUDIO[m][side][0], src="audio", note=AUDIO[m][side][1])
            if g["unresolved"]:
                s.update(truth=None, src=None, note="unresolved: " + g["unresolved"])      # 정답이 서로 충돌하는 곡은 숫자 정답에서 뺀다
            elif s["truth"] is None and iss not in (None, "ok", "fade_early"):
                p = next((a for a in appr if str(a["videoNo"]) == vno and ov(a["start"], a["end"], *base) > 0.5 * min(a["end"] - a["start"], base[1] - base[0])), None)
                if p:
                    s.update(truth=p["start" if side == "start" else "end"], src="playlist", note="재생목록 위치 정답(사람 검수)")
            if (g["gid"], side) in MANUAL and s["truth"] is not None:
                s["manual"] = MANUAL[(g["gid"], side)]
            g["sides"][side] = s
        groups.append(g)
    out = dict(version=1, groups=groups, exists=EXISTS, unresolved_all=UNRESOLVED_ALL, rows={str(i): canon[i] for i in canon})
    EXP.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf8")
    pts = [(g, sd) for g in groups for sd in ("start", "end") if g["sides"][sd]["truth"] is not None]
    live = [(g, sd) for g, sd in pts if g["lab"] != "N"]
    assert len(sum((g["rows"] for g, _ in live), [])) >= 20, "숫자 정답 20건(행 기준) 이상이어야 한다"
    print(f"{EXP}: 곡 {len(groups)}개(행 145), 숫자 정답 곡-경계 {len(pts)}(라이브 {len(live)}, N 참고 {len(pts) - len(live)}) 행 기준 {sum(len(g['rows']) for g, _ in live)}건, 출처 {dict(Counter(g['sides'][sd]['src'] for g, sd in live))}")


def load_src(spec, exp):
    """소스 -> [{slug, s, e}]. spec = 폴더/json 쉼표 목록(blind9_bounds.load_src) 또는 engine."""
    if spec == "engine":
        import audit_engine as E
        slug_of = {g["vno"]: g["slug"] for g in exp["groups"]}
        S = []
        for vno, slug in slug_of.items():
            for g in E.kept(vno):
                o = E.calc(vno, g["start"], g["end"])
                S.append(dict(slug=slug, s=o["song_s"], e=o["song_e"], rule="engine"))
            E._W.clear(); gc.collect()
        return S
    from blind9_bounds import load_src as ls
    return [x for p in spec.split(",") for x in ls(ROOT / p)]


def evaluate(exp, S):
    """곡(그룹) 별 경계 점검. 반환 dict(items, vanished(라이브가 사라짐), lens, multi(한 곡이 둘 이상 산출물)).
    item.kind: num(숫자 정답, err = 새 경계 - 정답, asym = 자름 CUT초/남음 EXTRA초 허용) / ok(경계 좋음, v3 경계 +-2초 유지) / dir(early/late 지적 쪽으로 1초 이상 이동)."""
    from blind9_bounds import find
    items, gone, lens, multi = [], [], [], []
    for g in exp["groups"]:
        r = dict(slug=g["slug"], base_start=g["base"][0], base_end=g["base"][1])
        c = find(S, r)
        if c is None:
            if g["lab"] != "N":
                gone.append(g["gid"])
            continue
        if len({(round(x["s"]), round(x["e"])) for x in S if x["slug"] == g["slug"] and ov(x["s"], x["e"], *g["base"]) > 0.5 * (g["base"][1] - g["base"][0])}) > 1:
            multi.append(g["gid"])
        new = dict(start=c["s"], end=c["e"])
        tr = {}
        for side in ("start", "end"):
            sd, b = g["sides"][side], g["base"][0 if side == "start" else 1]
            d = new[side] - b
            it = dict(gid=g["gid"], n=len(g["rows"]), lab=g["lab"], side=side, src=sd["src"], issue=sd["issue"], move=d)
            if sd["truth"] is not None:
                err = new[side] - sd["truth"]
                cut, extra = (max(0.0, err), max(0.0, -err)) if side == "start" else (max(0.0, -err), max(0.0, err))
                items.append(dict(it, kind="num", err=err, asym=cut <= CUT and extra <= EXTRA, manual=sd.get("manual")))
                tr[side] = sd["truth"]
            if sd["issue"] == "ok":
                items.append(dict(it, kind="ok", pass_=abs(d) <= OKTOL))
                tr.setdefault(side, b)
            elif sd["issue"] in ("early", "late"):
                want = ({"late": -1, "early": 1} if side == "start" else {"early": 1, "late": -1})[sd["issue"]]
                items.append(dict(it, kind="dir", pass_=d * want >= TOL))
        if len(tr) == 2 and any(i["kind"] == "num" for i in items if i["gid"] == g["gid"]) and g["lab"] != "N":
            lens.append(dict(gid=g["gid"], n=len(g["rows"]), err=(new["end"] - new["start"]) - (tr["end"] - tr["start"])))
    return dict(items=items, vanished=gone, lens=lens, multi=multi)


def summarize(ev):
    """hit@0.5/3/10 (num, 라이브만), ok 유지율, 방향 일치, 길이 오차."""
    num = [i for i in ev["items"] if i["kind"] == "num" and i["lab"] != "N"]
    s = dict(num_sides=len(num), num_rows=sum(i["n"] for i in num), vanished=len(ev["vanished"]))
    for t in TOLS:
        s[f"hit@{t:g}"] = sum(abs(i["err"]) <= t for i in num)
    s["median_abs_err"] = round(float(np.median([abs(i["err"]) for i in num])), 2) if num else None
    s["asym_pass"] = sum(i["asym"] for i in num)
    mn = [i for i in num if i["manual"] is not None]
    s["manual_agree"], s["manual_n"] = sum(i["asym"] == i["manual"] for i in mn), len(mn)
    for k in ("ok", "dir"):
        v = [i for i in ev["items"] if i["kind"] == k and i["lab"] != "N"]
        s[k + "_n"], s[k + "_pass"] = len(v), sum(i["pass_"] for i in v)
    s["multi_output"] = len(ev["multi"])
    s["len_n"], s["len_err_gt5"] = len(ev["lens"]), sum(abs(x["err"]) > 5 for x in ev["lens"])
    s["len_median_abs_err"] = round(float(np.median([abs(x["err"]) for x in ev["lens"]])), 2) if ev["lens"] else None
    return s


def gate(exp):
    """N/라이브 곡의 게이트 예측: 4_scene 후보 신호로 route.tier 를 등록부 없이(noreg) / 있이(prod) 재계산. 기대: N -> drop|weak, L -> auto(prod)/auto|review(noreg), B -> auto|review."""
    import route
    MP = route.MP
    res = []
    for g in exp["groups"]:
        k = jl(BD / "key.json")[g["key"]]
        sc = jl(ROOT / "out" / str(k["videoNo"]) / "4_scene.json")
        seg = max(sc["segs"], key=lambda q: ov(q["start"], q["end"], k["start"], k["end"]), default=None)
        if seg is None or ov(seg["start"], seg["end"], k["start"], k["end"]) <= 0:
            res.append(dict(gid=g["gid"], tag=g["tag"], lab=g["lab"], noreg=None, prod=None)); continue
        x = dict(seg)
        x["tier"], x["tier_why"] = route.tier(x, sc["has_refs"])
        weak = MP["weak"] <= (x.get("tstd") or 0) <= MP["motion"]
        cls = lambda q: "drop" if q["tier"] in ("drop", "optional") else "weak" if (weak and q["tier"] == "review") else q["tier"]
        a = cls(x)
        route.known_pos(k["videoNo"], x); route.known_neg(k["videoNo"], x)
        res.append(dict(gid=g["gid"], tag=g["tag"], lab=g["lab"], noreg=a, prod=cls(x)))
    return res


def gate_summary(res):
    want = lambda lab, cond: {"N": {"drop", "weak"}, "L": {"auto"} if cond == "prod" else {"auto", "review"}, "B": {"auto", "review"}}[lab]
    out = {}
    for tag in sorted({r["tag"] for r in res}):
        R = [r for r in res if r["tag"] == tag and r["noreg"] is not None]
        out[tag] = dict(n=len(R), **{c: sum(r[c] in want(r["lab"], c) for r in R) for c in ("noreg", "prod")}, noreg_dist=dict(Counter(r["noreg"] for r in R)))
    return out


def pairs(exp):
    """stale 쌍(한 곡의 여러 행): 라벨이 갈리는 쌍, approved.json 에서 boundary_ok 가 갈리는 쌍."""
    appr = [x for x in jl(ROOT / "data/approved.json") if "boundary_ok" in x]
    P = [g for g in exp["groups"] if len(g["rows"]) > 1]
    mixed = [g["rows"] for g in P if g["labs_mixed"]]
    conf = [g["rows"] for g in P if len({a["boundary_ok"] for a in appr if str(a["videoNo"]) == g["vno"] and ov(a["start"], a["end"], *g["base"]) > 0.5 * (g["base"][1] - g["base"][0])}) > 1]
    return dict(pairs=len(P), rows=sum(len(g["rows"]) for g in P), label_mixed=mixed, approved_boundary_ok_conflict=conf)


def exists(exp):
    out = []
    for e in exp["exists"]:
        g = next(g for g in exp["groups"] if e["n"] in g["rows"])
        cards = [jl(f) for f in sorted((ROOT / "out" / g["vno"] / "cards").glob("*.json"))]
        c = next((c for c in cards if ov(c["start"], c["end"], e["start"], e["end"]) > 0.5 * (e["end"] - e["start"])), None)
        out.append(dict(n=e["n"], tier=c["tier"] if c else None, why=c["tier_why"] if c else None, ok=bool(c and c["tier"] != "drop")))
    return out


def attrib():
    """전 방송 keep 후보 -> 현재 코드 컷(clip)까지 이동 >1초 인 경계의 stages 합이 이동량과 맞고 모든 stage 에 규칙 이름이 있는 비율."""
    import audit_engine as E
    n = ok = 0
    by, bad = Counter(), []
    for d in sorted((ROOT / "out").iterdir()):
        if not (d / "2_refine.json").exists() or not E.wav_path(d.name):
            continue
        for g in E.kept(d.name):
            o = E.calc(d.name, g["start"], g["end"])
            for edge, a, b in (("start", g["start"], o["clip_s"]), ("end", g["end"], o["clip_e"])):
                if abs(b - a) <= 1.0:
                    continue
                n += 1
                st = [t for t in o["stages"] if t["edge"] == edge]
                good = bool(st) and all(t["rule"] for t in st) and abs(sum(t["shift"] for t in st) - (b - a)) < 0.15
                ok += good
                by.update(t["rule"] for t in st if abs(t["shift"]) > 1.0)
                if not good:
                    bad.append((d.name, round(a, 1), edge, round(b - a, 1)))
        E._W.clear(); gc.collect()
    print(f"이동 >1초 경계 {n}개 중 규칙 이름 귀속 {ok}개 ({100 * ok / max(n, 1):.1f}%), 규칙별 1초 초과 이동 수 {dict(by.most_common())}" + (f", 미귀속 {bad[:10]}" if bad else ""))
    assert ok == n, bad
    return dict(edges_gt1=n, attributed=ok, pct=round(100 * ok / max(n, 1), 1), by_rule=dict(by))


def report(label, ev):
    s = summarize(ev)
    print(f"[{label}] 숫자 정답 {s['num_sides']}곡-경계({s['num_rows']}행): hit@0.5 {s['hit@0.5']}  hit@3 {s['hit@3']}  hit@10 {s['hit@10']}  중앙|오차| {s['median_abs_err']}s  asym(자름 1초/남음 3초) {s['asym_pass']}  (수동 감사 판정과 {s['manual_agree']}/{s['manual_n']} 일치) | "
          f"경계 좋음 유지 {s['ok_pass']}/{s['ok_n']} | 방향 {s['dir_pass']}/{s['dir_n']} | 길이 {s['len_n']}곡 중 오차>5초 {s['len_err_gt5']} (중앙 {s['len_median_abs_err']}s) | 라이브 곡 사라짐 {s['vanished']} | 한 곡 산출물 2개 이상 {s['multi_output']}")
    return s


def flat(d, p=""):
    return {p + str(k): v for k, v in d.items() if not isinstance(v, (dict, list))} | {kk: vv for k, v in d.items() if isinstance(v, dict) for kk, vv in flat(v, p + k + ".").items()}


def run(argv):
    exp = jl(EXP)
    save = "--save" in argv
    a = [x for x in argv if not x.startswith("--")]
    before, after = (a + [None, None])[:2] if a else (None, None)
    specs = {"stale_v3": before or "out/stale_v3", "current": after or "out/final,out/final_review", "engine": "engine"}
    evs, res = {}, dict(sources=specs, summary={})
    for lab, sp in specs.items():
        evs[lab] = evaluate(exp, load_src(sp, exp))
        res["summary"][lab] = report(lab, evs[lab])
    print("\n숫자 정답별 오차(after - 정답, 초): stale_v3 -> current -> engine")
    for it in [i for i in evs["current"]["items"] if i["kind"] == "num"]:
        g = next(g for g in exp["groups"] if g["gid"] == it["gid"])
        f = lambda lab: next((f"{i['err']:+7.1f}" for i in evs[lab]["items"] if i["gid"] == it["gid"] and i["side"] == it["side"]), "   없음")
        print(f"  #{it['gid']:<3d}{'(' + str(it['n']) + '행)':7s}{it['side']:6s}{it['src']:10s}{'N ' if it['lab'] == 'N' else '  '}{f('stale_v3')} -> {f('current')} -> {f('engine')}  {g['sides'][it['side']]['note']}")
    for lab in ("current", "engine"):
        bad = [i for i in evs[lab]["items"] if i["kind"] in ("ok", "dir") and i["lab"] != "N" and not i["pass_"]]
        print(f"[{lab}] 실패 {len(bad)}: " + " ".join(f"#{i['gid']}{i['side'][0]}{i['kind']}{i['move']:+.1f}" for i in bad))
    drift = [abs(i["move"] - j["move"]) for i in evs["current"]["items"] for j in evs["engine"]["items"] if i["gid"] == j["gid"] and i["side"] == j["side"]]
    print(f"engine 대 current json 곡 경계 차이: 최대 {max(drift):.2f}s, 0.1초 초과 {sum(x > 0.1 for x in drift)}/{len(drift)}  (json 은 이전 코드로 만든 산출물이라 규칙을 바꾼 뒤에는 차이가 정상)")
    res["gate"] = gate_summary(gate(exp))
    print("\n화면 tag 별 게이트 예측 (통과 = N 은 drop/weak, 라이브는 노출): tag n noreg prod | noreg 분포")
    for t, v in res["gate"].items():
        print(f"  {t:17s}{v['n']:3d}{v['noreg']:4d}{v['prod']:4d} | {v['noreg_dist']}")
    res["pairs"], res["exists"] = pairs(exp), exists(exp)
    print("stale 쌍:", res["pairs"], "\nexists:", res["exists"])
    res["unverifiable_claims"] = sum(len(g["unverifiable"]) for g in exp["groups"])
    res["unresolved"] = {g["gid"]: g["unresolved"] for g in exp["groups"] if g["unresolved"]} | {"all": exp["unresolved_all"]}
    print(f"청취 필요(unverifiable) 점검 {res['unverifiable_claims']}건, unresolved(사용자 답 대기, 규칙 변경 안 함) {len(res['unresolved'])}건: {list(res['unresolved'])}")
    if "--attrib" in argv:
        res["attrib"] = attrib()
    if save:
        old = jl(BASE) if BASE.exists() else None
        if old is not None and "--attrib" not in argv:
            res["attrib"] = old.get("attrib")
        BASE.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf8")
        print("저장:", BASE)
    elif BASE.exists():
        b, n = flat(jl(BASE)), flat(res)
        diff = {k: (b[k], n[k]) for k in n if k in b and b[k] != n[k] and not k.startswith("sources")}
        print("저장본(baseline) 대비 달라진 지표:", diff if diff else "없음")


def selftest():
    exp = jl(EXP)
    assert sum(len(g["rows"]) for g in exp["groups"]) == 145 and len(exp["groups"]) == 104 and len(exp["rows"]) == 145
    ev = evaluate(exp, [dict(slug=g["slug"], s=g["base"][0], e=g["base"][1], rule="x") for g in exp["groups"]])      # 기준 경계 그대로면 ok 는 전부 유지, 곡 사라짐 0
    s = summarize(ev)
    assert s["vanished"] == 0 and s["ok_pass"] == s["ok_n"] > 0, s
    cur = summarize(evaluate(exp, load_src("out/final,out/final_review", exp)))
    assert cur["manual_agree"] == cur["manual_n"] == 13, cur      # 자동 asym 판정이 지난 수동 감사 14건과 일치
    assert evaluate(exp, [])["vanished"] == [g["gid"] for g in exp["groups"] if g["lab"] != "N"]      # N 은 사라지는 것이 정상
    assert flat({"a": {"b": 1}, "c": 2}) == {"c": 2, "a.b": 1}
    print("selftest ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["build"]:
        build()
    elif a[:1] == ["attrib"]:
        attrib()
    elif a[:1] == ["selftest"]:
        selftest()
    else:
        run(a)
