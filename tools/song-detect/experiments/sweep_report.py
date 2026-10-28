"""OAT 결과(cache/proto_sweep/oat.json) -> 표(마크다운)와 PNG. 통과 = 게이트 무회귀(golden 이탈 0, hit@0.5/3, 방향, 경계 좋음 유지, 길이 오차>5초 수가 기준 이하, 곡 사라짐 0, 한 곡 둘 산출 0).
  python experiments/sweep_report.py [oat.json] [--png cache/proto_sweep/oat]"""
import json, sys
from pathlib import Path
import numpy as np


def passes(r, b):
    return (r["gold_dev"] == 0 and r["hit05"] >= b["hit05"] and r["hit3"] >= b["hit3"] and r["hit10"] >= b["hit10"] and r["dir_pass"] >= b["dir_pass"] and r["ok_pass"] >= b["ok_pass"]
            and r["len_gt5"] <= b["len_gt5"] and r["vanished"] == 0 and r["multi"] == 0)


def better(r, b):
    return passes(r, b) and (r["hit05"] > b["hit05"] or r["hit3"] > b["hit3"] or r["hit10"] > b["hit10"] or r["dir_pass"] > b["dir_pass"] or r["len_gt5"] < b["len_gt5"])


def why(r, b):
    f = []
    if r["gold_dev"]: f.append(f"golden 이탈 {r['gold_dev']}")
    for k, n in (("hit05", "h@0.5"), ("hit3", "h@3"), ("hit10", "h@10"), ("dir_pass", "방향"), ("ok_pass", "좋음유지")):
        if r[k] < b[k]: f.append(f"{n} {r[k]}<{b[k]}")
    if r["len_gt5"] > b["len_gt5"]: f.append(f"길이>5초 {r['len_gt5']}")
    if r["vanished"]: f.append(f"사라짐 {r['vanished']}")
    if r["multi"]: f.append("둘산출")
    return ", ".join(f)


def table(res):
    b, P = res["base"], res["params"]
    rows = []
    for k, d in P.items():
        rs = sorted(d["rows"], key=lambda r: r["v"])
        v0 = d["default"]
        i0 = next(i for i, r in enumerate(rs) if r["v"] == v0)
        lo = hi = i0
        while lo > 0 and passes(rs[lo - 1], b): lo -= 1
        while hi < len(rs) - 1 and passes(rs[hi + 1], b): hi += 1
        fl = rs[lo - 1] if lo > 0 else None
        fh = rs[hi + 1] if hi < len(rs) - 1 else None
        pct = lambda x: None if x is None else (x["v"] - v0) / abs(v0) * 100 if v0 else None
        bet = [r["v"] for r in rs if better(r, b)]
        npass = sum(passes(r, b) for r in rs)
        nbad = len(rs) - npass
        mrg = [abs(pct(x)) for x in (fl, fh) if x is not None and pct(x) is not None]
        kind = "무반응" if nbad == 0 else "절벽(여유<=10%)" if (mrg and min(mrg) <= 10.5) else "중간(여유<=30%)" if (mrg and min(mrg) <= 30.5) else "고원(여유>30%)"
        rows.append(dict(key=k, default=v0, lo=rs[lo]["v"], hi=rs[hi]["v"], fail_lo=None if fl is None else (fl["v"], why(fl, b)), fail_hi=None if fh is None else (fh["v"], why(fh, b)),
                         margin_lo=None if fl is None else round(pct(fl), 1), margin_hi=None if fh is None else round(pct(fh), 1), better=bet, kind=kind, npass=npass, n=len(rs),
                         moved2=[r.get("moved2") for r in rs if passes(r, b)], hit3=[r["hit3"] for r in rs]))
    return rows


def md(rows):
    out = ["| 상수 | 기본 | 통과 구간(연속) | 첫 실패(낮은쪽) | 첫 실패(높은쪽) | 개선(무회귀) 값 | 통과/전체 | 유형 |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        fl = "-" if r["fail_lo"] is None else f"{r['fail_lo'][0]:g} ({r['margin_lo']:+.0f}%): {r['fail_lo'][1]}"
        fh = "-" if r["fail_hi"] is None else f"{r['fail_hi'][0]:g} ({r['margin_hi']:+.0f}%): {r['fail_hi'][1]}"
        out.append(f"| {r['key']} | {r['default']:g} | {r['lo']:g} ~ {r['hi']:g} | {fl} | {fh} | {', '.join(f'{x:g}' for x in r['better']) or '-'} | {r['npass']}/{r['n']} | {r['kind']} |")
    return "\n".join(out)


def plot(res, prefix, per=12):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Malgun Gothic"; plt.rcParams["axes.unicode_minus"] = False
    b, P = res["base"], res["params"]
    ks = list(P)
    for pg in range(0, len(ks), per):
        sub = ks[pg:pg + per]
        fig, ax = plt.subplots(3, 4, figsize=(18, 11))
        for a, k in zip(ax.flat, sub):
            rs = sorted(P[k]["rows"], key=lambda r: r["v"])
            x = [r["v"] for r in rs]
            a.plot(x, [r["gold_dev"] for r in rs], "r-o", ms=4, label="golden dev")
            a.plot(x, [b["hit3"] - r["hit3"] for r in rs], "b-s", ms=4, label="hit3 loss")
            a.plot(x, [b["dir_pass"] - r["dir_pass"] for r in rs], "g--^", ms=4, label="dir loss")
            a2 = a.twinx()
            a2.plot(x, [r.get("moved2", 0) for r in rs], "k:", label="moved>2s (840)")
            a.axvline(P[k]["default"], color="gray", ls="--")
            a.set_title(k, fontsize=11)
        ax.flat[0].legend(fontsize=8)
        plt.tight_layout()
        f = f"{prefix}_{pg // per + 1}.png"
        plt.savefig(f, dpi=70)
        plt.close()
        print("저장", f)


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    f = a[0] if a else "cache/proto_sweep/oat.json"
    res = json.load(open(f, encoding="utf8"))
    rows = table(res)
    Path(f).with_suffix(".md").write_text(md(rows), encoding="utf8")
    json.dump(rows, open(Path(f).with_suffix(".table.json"), "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print(md(rows))
    if "--png" in sys.argv:
        plot(res, sys.argv[sys.argv.index("--png") + 1])
