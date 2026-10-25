"""승인(라이브)/오탐 클립의 키프레임 기준 풀 (캐시 파일 cache/scene_pool.npz + scene_pool.json). 새 방송에서 재사용한다.
풀 항목 = 라벨된 검토 클립 하나: {set, id, name, videoNo, live} 와 48x27 키프레임. 클립의 탐지 구간만(앞뒤 20초 패딩 제외).
사용: python scene_pool.py build            (blind5 + blind6 클립 mp4 에서 풀 생성/갱신, 읽히지 않는 클립은 건너뜀)
      python scene_pool.py eval [broadcast|streamer|clip|prev1]   (분할 방식별 route 등급 재평가, eval_blind 보고 함수 재사용)
분할: date=같은 스트리머+날짜(pipeline 이 NAS 슬러그로 사용) / broadcast=같은 방송(videoNo) 항목을 풀에서 뺌 / streamer=같은 스트리머를 뺌 / clip=그 클립만 뺌(같은 방송 형제 클립 사용, 낙관적)
      prev1=같은 방송 형제는 바로 앞 클립 1개만 남김(승인 1개로 시작하는 현실적 상황)
shortcut: 클립 mp4 가 없으면 풀에 못 넣음(V07 류 moov 없음, 오디오만 클립), 키프레임 개수는 클립 길이 비례(상한 없음)."""
import glob, json, re, sys
from pathlib import Path
import numpy as np
from labels import load

NPZ, META = Path("cache/scene_pool.npz"), Path("cache/scene_pool.json")
SETS = ("blind5", "blind6")


def build():
    from scene import thumbs
    meta, fr = [], {}
    old = dict(np.load(NPZ)) if NPZ.exists() else {}
    for s in SETS:
        key, lab = json.load(open(f"data/review/{s}/key.json", encoding="utf8")), load()[s]
        for f in sorted(Path(f"data/review/{s}").glob("*.mp4")):
            v = re.search(r"__(V\d+)", f.name).group(1)
            k, l = key[v], lab[v]
            a = k["start"] - k["clip_start"]
            if s == "blind5" and l["live"] and l["user"]:
                a, b = l["user"]                       # blind5 라이브는 사용자 경계 안만(말/사운드체크 제외)
            else:
                b = a + k["len"]
            x = thumbs(str(f), a, b)
            if len(x) < 3:
                continue
            fr[f"{s}/{v}"] = x
            meta.append(dict(set=s, id=v, name=k["name"], videoNo=k["videoNo"], start=k["start"], live=l["live"], n=len(x)))
    np.savez_compressed(NPZ, **fr)
    META.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf8")
    print("풀", len(meta), "클립, 라이브", sum(m["live"] for m in meta), "프레임", sum(m["n"] for m in meta))


REFS = Path("cache/scene_pool_refs.npz"), Path("cache/scene_pool_refs.json")    # cache/exp15/grab_refs.py: 사람이 검수한 위치 정답(refs*.json)과 사용자 승인 후보의 라이브 프레임


def pool():
    meta, F = json.load(open(META, encoding="utf8")), dict(np.load(NPZ))
    if all(f.exists() for f in REFS):                   # 있으면 합친다(set='refs', 전부 live). videoNo 가 있어 방송 단위 분할에서 자기 방송은 빠진다
        meta += json.load(open(REFS[1], encoding="utf8"))
        F.update(np.load(REFS[0]))
    D = {v["videoNo"]: v.get("date") or v.get("start") for p in glob.glob("data/vods*.json") for v in json.load(open(p, encoding="utf8"))}
    refs = json.load(open("data/refs.json", encoding="utf8"))
    for m in meta:                                      # 방송 날짜(NAS 슬러그와 같은 방송 판별용): vods*.json, 없으면 refs.json 위치(start)로
        m["date"] = D.get(m["videoNo"]) or next((r["date"] for r in refs if abs(r["start"] - m["start"]) < 1), None)
    return meta, F


def eligible(meta, name, keep=lambda m: True, n_min=5, b_min=2):
    """채널 승인 이력이 충분한가: 승인 라이브 곡 n_min 개 이상이고 서로 다른 방송 b_min 개 이상이어야 같은 채널 기준(has_refs)을 쓴다.
    미달이면 새 채널 취급(review 전용). 승인 1곡 풀로 auto 가 열려 후야 A(게임 중 따라 부르기)가 auto 에 남았던 문제 방지.
    shortcut: 5곡/2방송은 근거 표본이 적은 제안값(exp15), 승인이 쌓이면 채널별 오탐률로 재보정"""
    L = [m for m in meta if m["name"] == name and m["live"] and keep(m)]
    return len(L) >= n_min and len({m["videoNo"] for m in L}) >= b_min


def cat(meta, F, keep):
    return {g: (np.concatenate([F[f"{m['set']}/{m['id']}"] for m in meta if keep(m) and m["live"] == (g == "live")]) if any(keep(m) and m["live"] == (g == "live") for m in meta) else None) for g in ("live", "neg")}


def refs_for(name, meta, F):
    """새 방송용: 같은 스트리머의 라이브 키프레임(없으면 None) + 전체 live/neg 풀."""
    all_ = cat(meta, F, lambda m: True)
    same = cat(meta, F, lambda m: m["name"] == name)["live"]
    return same, all_["live"], all_["neg"]


def excluder(unit, m, meta):
    if unit == "date":                                 # 같은 스트리머+같은 날짜(NAS 녹화처럼 videoNo 가 없는 같은 방송). m = dict(name, date)
        return lambda o: not (o["name"] == m["name"] and o.get("date") == m["date"])
    if unit == "broadcast":
        return lambda o: o["videoNo"] != m["videoNo"]
    if unit == "streamer":
        return lambda o: o["name"] != m["name"]
    if unit == "clip":
        return lambda o: o is not m
    sib = sorted([o for o in meta if o["videoNo"] == m["videoNo"] and o["start"] < m["start"]], key=lambda o: o["start"])
    keep1 = sib[-1] if sib else None                   # prev1
    return lambda o: o["videoNo"] != m["videoNo"] or o is keep1


def evaluate(unit):
    import route, eval_blind
    from scene_multi import classify
    meta, F = pool()
    keys = {s: json.load(open(f"data/review/{s}/key.json", encoding="utf8")) for s in SETS}
    labs = load()
    R, out = [], []
    for s in SETS:                                      # 풀에 못 넣은 클립(대기 화면 오디오 등)도 54개 전체에 포함: 키프레임 없음 = 장면 못 읽음
        for v, l in labs[s].items():
            k = keys[s][v]
            m = next((o for o in meta if o["set"] == s and o["id"] == v), None)
            g = dict(k, keep=True, multi=None)
            g.pop("scene", None)
            has = False
            if m:
                keep = excluder(unit, m, meta)
                P = cat(meta, F, keep)
                same = cat(meta, F, lambda o: keep(o) and o["name"] == m["name"])["live"]
                fr = F[f"{s}/{v}"]
                g["multi"], _ = classify(fr, P["live"], P["neg"])
                if same is not None and eligible(meta, m["name"], keep):
                    has, g["scene"] = True, float(np.median([np.abs(same - f).mean(1).min() for f in fr]))
            R.append(dict(id=f"{s}/{v}", name=k["name"], g=g, has_refs=has, **l))
    T = eval_blind.tiers(R)
    eval_blind.report(R, T, f"기준 풀 분할={unit}")
    fp = [r["id"] for r, t in zip(R, T) if t != "drop" and not r["live"]]
    print("  통과한 오탐(auto/review):", fp)
    tt = [(r["id"], t) for r, t in zip(R, T) if r["name"] == "시즈키 토아" and r["live"]]
    print("  토아 라이브 등급:", {t: sum(x == t for _, x in tt) for t in ("auto", "review", "drop")})
    likely_report(R, T, keys)
    return R, T


# blind7/8 개별 후보(labels.py BLIND7/8): (videoNo, 시작초 근처, 라이브 여부, 이름). 채점 대상 = 현재 파일 out/<videoNo>/4_scene.json 의 가장 가까운 후보(8초 이내)
EXTRA = [(15761307, 5038, False, "7A"), (15831370, 411, False, "7D1"), (15831370, 811, False, "7D2"), (15831370, 1190, True, "7D3"), (15827672, 14393, True, "7B1"), (15827672, 14714, True, "7B2"),
         (15827672, 15549, True, "7C1"), (15827672, 16661, True, "7C2"), (15827672, 16065, True, "7E"), (15733149, 2304, False, "8Q1"), (15837908, 2443, True, "8Q2"), (15837908, 4342, True, "8Q3"),
         (15837908, 3403, True, "8Q4"), (15086957, 7143, True, "8Q7")]


def likely_flag(g, vno):
    """후보 g(tier 포함)의 likely 여부. 몰림 판정은 같은 방송 out/<vno>/3_final.json 의 keep 후보 전체로 한다(없으면 몰림 없음으로 취급)."""
    import route
    f = Path(f"out/{vno}/3_final.json")
    others = [x for x in json.load(open(f, encoding="utf8")) if x["keep"] and abs(x["start"] - g["start"]) > 1] if f.exists() else []
    S = [dict(keep=True, start=x["start"], len=0, tier="x") for x in others] + [g]
    route.mark_likely(S)
    return g["likely"]


def boot_ci(groups, n=4000, seed=0):
    """방송 단위 부트스트랩(방송을 통째로 복원추출) 정밀도 95% 구간. groups = {방송: (라이브 수, 전체 수)}"""
    rng, G = np.random.default_rng(seed), list(groups.values())
    pr = []
    for _ in range(n):
        pick = [G[i] for i in rng.integers(0, len(G), len(G))]
        d = sum(b for _, b in pick)
        if d:
            pr.append(sum(a for a, _ in pick) / d)
    return np.percentile(pr, [2.5, 97.5])


def likely_report(R, T, keys):
    import eval_blind
    fm = eval_blind.fmt
    L, by = [], {}
    for r, t in zip(R, T):
        s, v = r["id"].split("/")
        g = dict(r["g"], tier=t, start=keys[s][v]["start"], len=keys[s][v]["len"])
        L.append(likely_flag(g, keys[s][v]["videoNo"]))
        by.setdefault(keys[s][v]["videoNo"], [0, 0])
        if L[-1]:
            by[keys[s][v]["videoNo"]][0] += r["live"]
            by[keys[s][v]["videoNo"]][1] += 1
    k, n = sum(l and r["live"] for l, r in zip(L, R)), sum(L)
    nrev = sum(t == "review" for t in T)
    print(f"[likely] review {nrev}개 중 likely {n}개, 정밀도 {fm(k, n)} (클립 단위 Wilson)")
    by = {b: v for b, v in by.items() if v[1]}
    lo, hi = boot_ci(by)
    print(f"  방송 {len(by)}개 단위 부트스트랩 95% [{lo:.0%}-{hi:.0%}], 방송별 (라이브/likely):", {b: tuple(v) for b, v in by.items() if v[0] != v[1]} or "전부 오탐 없음")
    print(f"  likely 재현율(라이브 중) {fm(k, sum(r['live'] for r in R))}, review 라이브 중 {fm(k, sum(r['live'] and t == 'review' for r, t in zip(R, T)))}")
    print("  likely 인 오탐:", [r["id"] for l, r in zip(L, R) if l and not r["live"]])
    # 필터 단독 변별력: 등급을 무시하고 multi==live 와 길이/시작/몰림만 본 경우 오탐 통과율(오탐 19개 중)
    FP = [(r, keys[r["id"].split("/")[0]][r["id"].split("/")[1]]) for r in R if not r["live"]]
    free = [likely_flag(dict(r["g"], tier="review", start=kk["start"], len=kk["len"]), kk["videoNo"]) for r, kk in FP]
    print(f"  (참고) 등급 무시, 필터만 적용 시 오탐 {len(FP)}개 중 통과 {sum(free)}개 {[r['id'] for (r, _), f in zip(FP, free) if f]}")
    X = []
    for vno, st, live, tag in EXTRA:
        f = Path(f"out/{vno}/4_scene.json")
        if not f.exists():
            continue
        sc = json.load(open(f, encoding="utf8"))
        g = min(sc["segs"], key=lambda x: abs(x["start"] - st))
        if abs(g["start"] - st) < 8:
            g["tier"] = __import__("route").tier(g, sc["has_refs"])[0]      # 4_scene 에는 등급이 없다(route 가 매번 계산)
            X.append((tag, live, g["tier"], likely_flag(dict(g), vno), vno))
    print(f"  (참고) blind7/8 개별 후보 {len(X)}개 중 review 인 것 {[(t, 'L' if l else 'F', lk) for t, l, ti, lk, _ in X if ti == 'review']}")
    for t, l, ti, lk, vno in X:                       # 합산: blind5/6 + blind7/8 개별 후보 중 likely
        if lk and ti == "review":
            by.setdefault(vno, [0, 0])
            by[vno][0] += l
            by[vno][1] += 1
            k, n = k + l, n + 1
    lo, hi = boot_ci(by)
    clean = sum(a == b for a, b in by.values())
    print(f"  [합산 blind5/6/7/8] likely {fm(k, n)} (클립), 오탐 없는 방송 {fm(clean, len(by))} (방송 단위 Wilson), 방송 부트스트랩 정밀도 [{lo:.0%}-{hi:.0%}]")


if __name__ == "__main__":
    build() if sys.argv[1] == "build" else evaluate(sys.argv[2] if len(sys.argv) > 2 else "broadcast")
