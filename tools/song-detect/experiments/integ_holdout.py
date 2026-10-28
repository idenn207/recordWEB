"""통합 공통 지표(experiments_log/integration.md 0절): 배포 규칙(표본 내, A 정의)과 hold-out(B 정의) 두 열로 N 노출/라이브 손실을 같은 표본, 같은 정의로 낸다.
  python experiments/integ_holdout.py build   프레임 캐시(cache/proto_visual/frames, visual 트랙 산출)를 배포 코드 n_visual 로 점수화 -> cache/audit/vis_table.json (GPU, torch+open_clip 이 있는 venv python)
  python experiments/integ_holdout.py golden  승인 golden 113곡을 배포 경로(n_visual.fill: NAS 1080p 또는 치지직 144p 프레임 8장)로 점수화 -> cache/audit/vis_golden.json (GPU + NAS 세션 + 인터넷, 약 9분)
  python experiments/integ_holdout.py cal     vis_table 라이브 + vis_golden 라이브의 최댓값 + 0.1 x 범위로 n_visual_cal.json 의 thr 을 다시 정함(--write 가 있을 때만 저장)
  python experiments/integ_holdout.py eval    표 출력. 입력: cache/audit/signals.csv(logo_route build) + vis_table.json
정의(0절): N 노출 = blind9 사용자 N 55곡 중 등록부 없이 완성본에 노출되는 수(auto 이거나 weak 가 아닌 review). 라이브 손실 = 블라인드 라이브 중 drop 이거나 weak 인 수.
  A(표본 내) = 배포 임계 그대로(임계가 이 표본에서 정해져 과적합 참고값). B(hold-out) = logo_route 행 D(임계/신호를 스트리머 제외로 다시 정함, m=0.1) 위에 n_visual 임계도 스트리머 제외로 다시 정해 얹음(임계 = 학습 라이브 최댓값 + m x 범위).
shortcut: vis 표는 visual 트랙 프레임 204곡(라이브 133, N 71, 그중 신호 표와 맞는 163행)뿐이다. 스트리머 11명 표본이라 구간이 넓다."""
import json, os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments")); os.chdir(ROOT)
import numpy as np, pandas as pd

TAB, PV = Path("cache/audit/vis_table.json"), Path("cache/proto_visual")


def build():
    from PIL import Image
    import n_visual
    c = n_visual.cal()
    rows = []
    for r in json.load(open(PV / "manifest.json", encoding="utf8")):
        fs = sorted((PV / "frames" / r["key"].replace("/", "__")).glob("*.jpg"), key=lambda p: int(p.stem))
        if len(fs) >= 3:
            rows.append(dict(key=r["key"], live=int(r["live"] == 1), set=r["set"], tag=r["tag"], name=r["name"], vis=n_visual.vis_of(n_visual.components([Image.open(f) for f in fs]), c)))
    TAB.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf8")
    print(f"{TAB}: {len(rows)}곡 (라이브 {sum(x['live'] for x in rows)})")


def golden():
    import time
    import n_visual, vod
    sys.path.insert(0, str(ROOT / "datasets"))
    import nas_ingest as N
    rows = {r["slug"]: r for r in json.load(open("data/nas_index.json", encoding="utf8"))}
    out = []
    for g in json.load(open("experiments/golden_v4.json", encoding="utf8"))["songs"]:
        seg = [dict(keep=True, start=g["frozen"]["s"], end=g["frozen"]["e"])]
        n_visual.fill(seg, N.url_of(rows[g["vid"]]["path"]) if g["vid"] in rows else vod.url144(int(g["vid"])))
        out.append(dict(id=g["id"], vis=seg[0].get("vis")))
    Path("cache/audit/vis_golden.json").write_text(json.dumps(out), encoding="utf8")
    v = [x["vis"] for x in out if x["vis"] is not None]
    print(f"golden {len(out)}곡 중 vis {len(v)}곡, 최대 {max(v):.3f}")


def golden_rows():
    n = {}
    for p in Path("data").glob("vods*.json"):
        n.update({str(v["videoNo"]): v["name"] for v in json.load(open(p, encoding="utf8"))})
    idx = {r["slug"]: r["streamer"] for r in json.load(open("data/nas_index.json", encoding="utf8"))}
    vg = {x["id"]: x["vis"] for x in json.load(open("cache/audit/vis_golden.json", encoding="utf8"))}
    return pd.DataFrame([dict(key=f"golden/{g['id']}", live=1, set="golden", tag="", name=idx.get(g["vid"]) or n[g["vid"]], vis=vg[g["id"]])
                         for g in json.load(open("experiments/golden_v4.json", encoding="utf8"))["songs"] if vg.get(g["id"]) is not None])


def cal(write=False):
    """알려진 라이브 전부(visual 트랙 133곡 + golden 113곡을 배포 경로로 다시 점수화한 값)의 최댓값 + 0.1 x 범위. 144p 곡이 NAS 1080p 곡보다 높게 나와 visual 트랙의 133곡만으로는 임계가 낮았다."""
    import n_visual
    V = json.load(open(TAB, encoding="utf8")); Gd = json.load(open("cache/audit/vis_golden.json", encoding="utf8"))
    lv = np.array([x["vis"] for x in V if x["live"]] + [x["vis"] for x in Gd if x["vis"] is not None])
    c = n_visual.cal()
    thr = float(lv.max() + 0.1 * (lv.max() - lv.min()))
    new = dict(c, thr=thr, n_live=int(len(lv)), live_max=float(lv.max()), live_min=float(lv.min()), thr_note="알려진 라이브 = visual 트랙 133곡 + golden 113곡(배포 경로 점수, 144p 포함)의 최댓값 + 0.1 x 범위. 통합 때 0.8045 -> 이 값으로 올림(golden 144p 라이브 0.79 와의 간격 0.015 가 너무 얇아서)")
    print(f"라이브 {len(lv)}곡 최대 {lv.max():.3f} 최소 {lv.min():.3f} -> 임계 {thr:.3f} (이전 {c['thr']:.3f})")
    if write:
        Path("n_visual_cal.json").write_text(json.dumps(new, indent=1), encoding="utf8")
    return new


def veto(v, live, grp, m):
    """스트리머 hold-out: 그룹마다 학습 라이브 vis 최댓값 + m x 범위 초과면 걸림"""
    hit = np.zeros(len(v), bool)
    for g in np.unique(grp):
        te, tr = grp == g, (grp != g) & (live == 1)
        hit[te] = v[te] > v[tr].max() + m * (v[tr].max() - v[tr].min())
    return hit


def evaluate():
    import logo_route as LR, n_signals
    from scene_multi import P as MP
    import n_visual
    V = pd.DataFrame(json.load(open(TAB, encoding="utf8")))
    V = pd.concat([V, golden_rows()], ignore_index=True)           # hold-out 임계의 학습 라이브에 golden(배포 경로 점수)도 넣는다: 같은 스트리머 곡은 veto() 가 그룹 제외로 뺀다
    sig = LR.with_golden(LR.load())                                   # 라이브 풀 = 신호 표 88 + golden 라이브(표에 없는 것) = 136
    G = golden_rows().set_index("key").name                          # golden 행의 그룹은 방송이 아니라 스트리머로(스트리머 hold-out 에서 같은 스트리머가 학습에 섞이지 않게)
    sig["streamer"] = [G.get(k, n) for k, n in zip(sig.key, sig.name)]
    D, _ = LR.holdout(sig, "streamer", "D", 0.1)
    sig["D"] = D
    thr = n_visual.cal()["thr"]
    fl = np.array([bool(n_signals.fire(dict(rel_db=r, bursts=b))) for r, b in zip(sig.rel_db.fillna(0), sig.bursts_per_min.fillna(0))])
    sig["dep_ok"] = ~(((sig.struct_cls == "drop") | (sig.tstd > MP["motion"])).to_numpy() | fl)
    X = sig.merge(V[["key", "vis"]], on="key", how="left")
    print(f"신호 표 {len(sig)}행, vis 있음 {int(X.vis.notna().sum())}행, vis 표 {len(V)}곡(golden 포함, 임계 {thr:.3f})")
    out = {}
    for sub, mk in (("blind9", X.set == "blind9"), ("전체", X.set != "")):
        Z = X[mk]
        N, L = Z[Z.live == 0], Z[Z.live == 1]
        print(f"\n[{sub}] N {len(N)} / 라이브 {len(L)}")
        a = dict(nA=int(N.dep_ok.sum()), lA=int((~L.dep_ok).sum()))
        a2 = dict(nA=int((N.dep_ok & (N.vis <= thr)).sum()), lA=int((~L.dep_ok | (L.vis > thr)).sum()))
        print(f"  A 배포 규칙(표본 내)           노출 {a['nA']:2d}  라이브 손실 {a['lA']}")
        print(f"  A + n_visual 배포 임계(표본 내) 노출 {a2['nA']:2d}  라이브 손실 {a2['lA']}")
        print(f"  B 행 D m=0.1(hold-out)          노출 {int((N.D == 'ok').sum()):2d}  라이브 손실 {int((L.D != 'ok').sum())}")
        out[sub] = dict(A=a, A_vis=a2, B=(int((N.D == "ok").sum()), int((L.D != "ok").sum())))
        for m in (0.0, 0.1, 0.2):
            hit = veto(V.vis.to_numpy(), V.live.to_numpy(), V.name.to_numpy(), m)
            H = dict(zip(V.key, hit))
            vh = Z.key.map(H).fillna(False).astype(bool)
            n_exp = int(((N.D == "ok") & ~vh[N.index]).sum()); l_lost = int(((L.D != "ok") | vh[L.index]).sum())
            n_only = int((N.dep_ok & ~vh[N.index]).sum()); l_only = int((~L.dep_ok | vh[L.index]).sum())
            print(f"  B + n_visual hold-out m={m}     노출 {n_exp:2d}  라이브 손실 {l_lost}   (배포 규칙 + hold-out vis 노출 {n_only}, 손실 {l_only})")
            out[sub][f"m{m}"] = (n_exp, l_lost)
    return out


if __name__ == "__main__":
    if sys.argv[1:2] == ["build"]:
        build()
    elif sys.argv[1:2] == ["golden"]:
        golden()
    elif sys.argv[1:2] == ["cal"]:
        cal("--write" in sys.argv)
    else:
        o = evaluate()
        assert o["blind9"]["A"]["lA"] == 0, "배포 규칙이 blind9 라이브를 걸러서는 안 된다"
