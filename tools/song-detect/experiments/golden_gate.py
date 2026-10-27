"""golden gate: 승인된 라이브 곡(approved.json 중 boundary_ok != False: 재생목록 위치 정답, blind5~8 사용자 라이브, blind9 L)의 v4 결과를 동결(golden_v4.json)하고,
현재 코드의 결과와 비교해 이탈을 목록으로 낸다. 이탈이 화이트리스트(사유 필수)에 없으면 종료코드 1.
  python experiments/golden_gate.py freeze   동결(처음 한 번, 의도한 개선을 받아들일 때). 화이트리스트는 보존. 기준: cache/audit/master.json(audit_master.py)으로 승인 구간 -> 후보 매칭
  python experiments/golden_gate.py          비교(약 몇 분: 방송별 pcm 로드). 현재 = audit_engine.calc(refine 경계 -> fix -> snap) + route(tier+known_pos+known_neg)
이탈 기준(PLAN_NEXT 3.3): 시작/끝 이동 > 2초, 클립 길이 변화 > 3초, 곡 사라짐(refine 후보 없음/drop), 등급 하락(기대 등급 expect = v3 코드 재현 등급, blind9 L 은 auto), 정답에서 멀어짐(재생목록 정답 오차 +2초 초과), 이웃 golden 곡과 새로 겹침.
shortcut: 이웃 겹침은 golden 곡끼리만 본다. tail(곡 끝 직후 말소리, D4)은 이동/길이로 안 잡히므로 이 게이트 대상이 아니다(P2 의 말소리 포함 검사로)."""
import sys, json, copy
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
import os
os.chdir(ROOT)
GOLD = ROOT / "experiments/golden_v4.json"
RANK = {"auto": 3, "review": 2, "optional": 1, "drop": 0}


def ovl(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def current(vid, rs, re_):
    """(곡 경계/클립 경계/등급) 현재 코드 결과, 후보가 없으면 None. 등급은 pipeline 과 같은 순서(tier -> known_pos -> known_neg), 경계는 3_final(fix) 기준."""
    import audit_engine as E, route
    K = E.kept(vid)
    k = next((i for i, g in enumerate(K) if abs(g["start"] - rs) < 0.2 and abs(g["end"] - re_) < 0.2), None)
    if k is None:
        return None
    c = E.calc(vid, rs, re_)
    sc = json.load(open(ROOT / "out" / vid / "4_scene.json", encoding="utf8"))
    g = copy.deepcopy(sc["segs"][k]); g["start"], g["end"], g["len"] = c["fix_s"], c["fix_e"], c["fix_e"] - c["fix_s"]
    try:
        import piano_gate; piano_gate.annotate(vid, [g])
    except Exception:
        pass
    g["tier"], g["tier_why"] = route.tier(g, sc["has_refs"])
    route.known_pos(vid, g); route.known_neg(vid, g)
    return dict(s=c["song_s"], e=c["song_e"], clip=c["clip_e"] - c["clip_s"], tier=g["tier"], why=g["tier_why"])


def freeze():
    import audit_engine as E
    from audit_regress import find, sets, tier3
    truth = {}                                                   # 재생목록/사용자 경계 정답(절대초): 같은 후보의 첫 정답만
    for ref, r, t in sets():
        if r and t:
            truth.setdefault((r["vid"], r["k"]), t)
    ents, unmatched = {}, []
    for x in json.load(open(ROOT / "data/approved.json", encoding="utf8")):
        if x.get("boundary_ok") is False:
            continue
        vid = str(x["videoNo"])
        r = find(vid, x["start"], x["end"], "v3")
        if r is None:
            unmatched.append(dict(vid=vid, start=round(x["start"]), src=x["src"]))
            continue
        e = ents.setdefault((vid, r["k"]), dict(id=f"{vid}@{r['refine'][0]:.0f}", vid=vid, refine=r["refine"], src=[], truth=truth.get((vid, r["k"])), expect=tier3(r)))
        e["src"].append(x["src"])
        if x.get("boundary_ok"):                                 # 사용자가 경계까지 좋다고 판정한 곡(blind9 L)은 v3 에 버그가 있었어도 기대 등급 auto(#45)
            e["expect"] = "auto"
    out = sorted(ents.values(), key=lambda e: (e["vid"], e["refine"][0]))
    for e in out:
        c = current(e["vid"], *e["refine"])
        assert c, e
        e["frozen"] = dict(s=c["s"], e=c["e"], clip=c["clip"], tier=c["tier"])
        if e["truth"]:
            ts, te = e["truth"]
            e["frozen"]["err"] = [None if ts is None else c["s"] - ts, None if te is None else c["e"] - te]
        E._W.clear() if len(E._W) > 1 else None                   # pcm 캐시는 방송 2개까지만(메모리)
    old = json.load(open(GOLD, encoding="utf8")) if GOLD.exists() else {}
    GOLD.write_text(json.dumps(dict(whitelist=old.get("whitelist", []), unresolved=old.get("unresolved", []), unmatched=unmatched, songs=out), ensure_ascii=False, indent=1), encoding="utf8")
    print(f"{GOLD.name}: {len(out)}곡 동결 (승인 구간 중 후보 매칭 실패 {len(unmatched)}), 기대 등급보다 낮은 현재 상태:",
          [(e["id"], e["expect"], e["frozen"]["tier"]) for e in out if RANK[e["frozen"]["tier"]] < RANK[e["expect"]]])


def check(quiet=False):
    import audit_engine as E
    G = json.load(open(GOLD, encoding="utf8"))
    wl = {(w["id"], w["flag"]): w["why"] for w in G["whitelist"]}
    assert all(w.get("why") for w in G["whitelist"]), "화이트리스트 항목은 사유 필수"
    dev, cur = [], {}
    for e in sorted(G["songs"], key=lambda e: e["vid"]):
        cur[e["id"]] = current(e["vid"], *e["refine"])
        E._W.clear() if len(E._W) > 1 else None
    for e in G["songs"]:
        c, f, fl = cur[e["id"]], e["frozen"], []
        if c is None:
            fl.append(("곡사라짐", "refine 후보가 없음"))
        else:
            if abs(c["s"] - f["s"]) > 2: fl.append(("시작이동", f"{c['s'] - f['s']:+.1f}초"))
            if abs(c["e"] - f["e"]) > 2: fl.append(("끝이동", f"{c['e'] - f['e']:+.1f}초"))
            if abs(c["clip"] - f["clip"]) > 3: fl.append(("클립길이", f"{c['clip'] - f['clip']:+.1f}초"))
            if c["tier"] == "drop": fl.append(("곡사라짐", c["why"]))
            elif RANK[c["tier"]] < RANK[e["expect"]]: fl.append(("등급하락", f"{e['expect']} -> {c['tier']}: {c['why']}"))
            for i, nm in enumerate(("시작", "끝")):                 # 정답이 있는 쪽만: 동결 때보다 2초 넘게 멀어지면
                if e["truth"] and e["truth"][i] is not None and f["err"][i] is not None:
                    err = (c["s"] if i == 0 else c["e"]) - e["truth"][i]
                    if abs(err) > abs(f["err"][i]) + 2: fl.append((f"정답에서멀어짐{nm}", f"{f['err'][i]:+.1f} -> {err:+.1f}"))
            for q in G["songs"]:                                  # 이웃 golden 곡과 새로 겹침
                if q is not e and q["vid"] == e["vid"] and cur[q["id"]] and ovl(c["s"], c["e"], cur[q["id"]]["s"], cur[q["id"]]["e"]) > 1 \
                        and ovl(f["s"], f["e"], q["frozen"]["s"], q["frozen"]["e"]) <= 1:
                    fl.append(("병합/겹침", q["id"])); break
        dev += [(e["id"], k, d) for k, d in fl]
    bad = [d for d in dev if (d[0], d[1]) not in wl]
    for i, k, d in dev:
        print(f"{'  (화이트리스트) ' if (i, k) in wl else '이탈 '}{i:28} {k:12} {d}" + (f"  <- {wl[(i, k)]}" if (i, k) in wl else ""))
    stale = [k for k in wl if not any((d[0], d[1]) == k for d in dev)]
    print(f"golden {len(G['songs'])}곡: 이탈 {len(bad)}건 (화이트리스트 {len(dev) - len(bad)}건, 안 쓰인 화이트리스트 {len(stale)}건 {stale})  미해결 기록 {len(G['unresolved'])}건")
    return bad


if __name__ == "__main__":
    if sys.argv[1:] == ["freeze"]:
        freeze()
    else:
        sys.exit(1 if check() else 0)
