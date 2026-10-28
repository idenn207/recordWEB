"""작업대 LOGO: lab_<이름>.json 격자에서 '그룹 제외로 설정을 고르고 제외한 그룹에서 이득을 재는' 평가. 그룹 = 스트리머 x 방송일(slug) 또는 스트리머.
이득 U(설정, 그룹) = 그 그룹 항목(숫자 정답 hit@3, 방향, 경계 좋음)의 통과 수 변화(기준선 대비), 새로 깨진 항목은 2배로 센다. 기준선(규칙 없음)은 U=0.
출력: 제외 그룹에서의 총이득 합, 선택된 설정 분포, 부트스트랩(그룹 재표집 2000회) 95% 구간. 표본 내 최적(전체 최적)은 따로 표기한다.
사용: python experiments/bl_logo.py <glob 패턴> [streamer]    예) python experiments/bl_logo.py 's3_*@rev'"""
import json, sys, glob, re
from pathlib import Path
import numpy as np
O = Path(__file__).resolve().parent.parent / "cache/proto_boundary"
E = json.load(open(O.parent.parent / "data/review/blind9/expectations.json", encoding="utf8"))
SLUG = {}
for g in E["groups"]:
    if g["lab"] != "N":
        SLUG[g["gid"]] = g["slug"]
def grp(gid, mode):
    s = SLUG[gid]
    return re.sub(r"^\d+_", "", s).split("_")[0] if mode == "streamer" else s
def passed(k, v):
    kind = k.split(":")[1]
    return abs(v[0]) <= 3.0 if kind == "num" else bool(v[1])
def gains(name, base, mode):
    r = json.load(open(O / f"lab_{name}.json", encoding="utf8"))["items"]
    G = {}
    for k, v in r.items():
        gid = int(re.match(r"\d+", k).group())
        if gid not in SLUG:
            continue
        b = base.get(k)
        if b is None:
            continue
        d = int(passed(k, v)) - int(passed(k, b))
        G.setdefault(grp(gid, mode), 0)
        G[grp(gid, mode)] += d if d >= 0 else 2 * d
    return G
if __name__ == "__main__":
    pat, mode = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "slug")
    base = json.load(open(O / "lab_base.json", encoding="utf8"))["items"]
    names = sorted(Path(p).stem[4:] for p in glob.glob(str(O / f"lab_{pat}.json")))
    G = {n: gains(n, base, mode) for n in names}
    groups = sorted({g for n in G for g in G[n]} | {grp(i, mode) for i in SLUG})
    U = np.array([[G[n].get(g, 0) for g in groups] for n in names])        # 설정 x 그룹
    tot = U.sum(1)
    print(f"설정 {len(names)}개, 그룹 {len(groups)}개({mode}). 표본 내 최적: {names[int(tot.argmax())]} 총이득 {tot.max():+d} (과적합 참고값)")
    hold, pick = [], []
    for j, g in enumerate(groups):
        rest = U.sum(1) - U[:, j]
        i = int(np.flatnonzero(rest == rest.max())[0])                       # 동률이면 앞(단순한 기본값)
        hold.append(U[i, j]); pick.append(names[i])
    hold = np.array(hold)
    rng = np.random.default_rng(0)
    bs = [hold[rng.integers(0, len(hold), len(hold))].sum() for _ in range(2000)]
    print(f"그룹 제외 선택 후 제외 그룹 총이득 {hold.sum():+d} (그룹별 {dict(zip(groups, hold.tolist()))}), 부트스트랩 95% [{np.percentile(bs, 2.5):+.0f}, {np.percentile(bs, 97.5):+.0f}]")
    from collections import Counter
    print("제외 때마다 고른 설정:", dict(Counter(pick)))
