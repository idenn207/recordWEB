"""(b) 다중 가설 위원회: 규칙 변형(기존 규칙 on/off + 제안 규칙 격자)이 만든 경계들의 분산을 불확실도로 쓰는 경계 제안 모드(auto 에는 적용 안 함).
불확실도 U(곡, 변) = 위원회 구성원들이 낸 경계의 (최대 - 최소). '문제 곡-변' = 기준선에서 방향 지적을 못 풀었거나 숫자 정답 3초 밖인 곡-변.
평가: U 상위 k 개 중 문제 곡-변 비율(precision@k)을 무작위 기대와 비교. 위원회 = lab_<이름>.json 의 moves(v3 경계 대비 이동).
사용: python experiments/bl_committee.py"""
import json, glob, re, sys
from pathlib import Path
import numpy as np
O = Path(__file__).resolve().parent.parent / "cache/proto_boundary"
E = json.load(open(O.parent.parent / "data/review/blind9/expectations.json", encoding="utf8"))
live = {g["gid"] for g in E["groups"] if g["lab"] != "N"}
load = lambda n: json.load(open(O / f"lab_{n}.json", encoding="utf8"))
base = load("base")
prob = set()
for k, v in base["items"].items():
    gid = int(re.match(r"\d+", k).group())
    kind = k.split(":")[1]
    if gid in live and ((kind == "dir" and not v[1]) or (kind == "num" and abs(v[0]) > 3)):
        prob.add(k.split(":")[0])
pairs = sorted({k for k in base["moves"] if int(re.match(r"\d+", k).group()) in live})
print(f"후보 곡-변 {len(pairs)}개, 문제 곡-변 {len(prob)}개 {sorted(prob)}")
fam = {"기존규칙 on/off(6)": [f"off_{r}" for r in ("E1", "E1b", "E2", "E3", "S1", "S2")],
       "S3 격자(전부)": [Path(p).stem[4:] for p in glob.glob(str(O / "lab_s3_*.json")) if "@" not in p],
       "제안 규칙 전부(S3,S3e,breath,S4,E4,E5,nov)": [Path(p).stem[4:] for p in glob.glob(str(O / "lab_*.json")) if re.match(r".*lab_(s3|s3e|breath|s4|e4|e5|nov)_", p.replace("\\", "/")) and "@" not in p],
       "기존 on/off + 제안 전부": None}
fam["기존 on/off + 제안 전부"] = fam["기존규칙 on/off(6)"] + fam["제안 규칙 전부(S3,S3e,breath,S4,E4,E5,nov)"]
rng = np.random.default_rng(0)
out = {}
for fn, names in fam.items():
    names = [n for n in names if (O / f"lab_{n}.json").exists()]
    M = [load(n)["moves"] for n in names]
    U = {}
    for p in pairs:
        d = [m[p] - base["moves"][p] for m in M if p in m]
        U[p] = (max(d) - min(d)) if d else 0.0
    rank = sorted(pairs, key=lambda p: -U[p])
    row = {}
    for k in (5, 10, 15):
        hit = sum(p in prob for p in rank[:k])
        exp = k * len(prob) / len(pairs)
        # 무작위 10000번 중 hit 이상 나오는 비율 (우연 확률)
        sims = [len(set(rng.choice(len(pairs), k, replace=False)) & {i for i, p in enumerate(pairs) if p in prob}) for _ in range(5000)]
        row[k] = (hit, round(exp, 1), round(float(np.mean([s >= hit for s in sims])), 3))
    out[fn] = dict(n_members=len(names), p_at=row, top=[(p, round(U[p], 1)) for p in rank[:12]])
    print(f"{fn:42s} 구성원 {len(names):3d}  P@5 {row[5][0]}/5 (무작위 {row[5][1]}, 우연 p={row[5][2]})  P@10 {row[10][0]}/10 (무작위 {row[10][1]}, p={row[10][2]})  P@15 {row[15][0]}/15 (무작위 {row[15][1]}, p={row[15][2]})")
    print("   상위:", " ".join(f"{p}{'*' if p in prob else ''}({u})" for p, u in out[fn]["top"]))
(O / "committee.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf8")
