"""승인(라이브)/오탐 클립의 키프레임 기준 풀 (캐시 파일 cache/scene_pool.npz + scene_pool.json). 새 방송에서 재사용한다.
풀 항목 = 라벨된 검토 클립 하나: {set, id, name, videoNo, live} 와 48x27 키프레임. 클립의 탐지 구간만(앞뒤 20초 패딩 제외).
사용: python scene_pool.py build            (blind5 + blind6 클립 mp4 에서 풀 생성/갱신, 읽히지 않는 클립은 건너뜀)
      python scene_pool.py eval [broadcast|streamer|clip|prev1]   (분할 방식별 route 등급 재평가, eval_blind 보고 함수 재사용)
분할: broadcast=같은 방송(videoNo) 항목을 풀에서 뺌 / streamer=같은 스트리머를 뺌 / clip=그 클립만 뺌(같은 방송 형제 클립 사용, 낙관적)
      prev1=같은 방송 형제는 바로 앞 클립 1개만 남김(승인 1개로 시작하는 현실적 상황)
shortcut: 클립 mp4 가 없으면 풀에 못 넣음(V07 류 moov 없음, 오디오만 클립), 키프레임 개수는 클립 길이 비례(상한 없음)."""
import json, re, sys
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
    return R, T


if __name__ == "__main__":
    build() if sys.argv[1] == "build" else evaluate(sys.argv[2] if len(sys.argv) > 2 else "broadcast")
