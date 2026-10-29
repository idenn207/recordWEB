"""통합 공통 지표(experiments_log/integration.md 0절): 배포 규칙(표본 내, A 정의)과 hold-out(B 정의) 두 열로 N 노출/라이브 손실을 같은 표본, 같은 정의로 낸다.
  python experiments/integ_holdout.py build   프레임 캐시(cache/proto_visual/frames, visual 트랙 산출)를 배포 코드 n_visual 로 점수화 -> cache/audit/vis_table.json (GPU, torch+open_clip 이 있는 venv python)
  python experiments/integ_holdout.py golden  승인 golden 113곡을 배포 경로(n_visual.fill: NAS 1080p 또는 치지직 144p 프레임 8장)로 점수화 -> cache/audit/vis_golden.json (GPU + NAS 세션 + 인터넷, 약 9분)
  python experiments/integ_holdout.py cal     vis_table 라이브 + vis_golden 라이브의 최댓값 + 0.1 x 범위로 n_visual_cal.json 의 thr 을 다시 정함(--write 가 있을 때만 저장)
  python experiments/integ_holdout.py eval    표 출력(배포 경로 vis 표, 이어서 참고용 프로토 프레임 표). 입력: cache/audit/signals.csv(logo_route build) + vis_table.json + out/<방송>/4_scene.json
정의(0절): N 노출 = blind9 사용자 N 55곡 중 등록부 없이 완성본에 노출되는 수(auto 이거나 weak 가 아닌 review). 라이브 손실 = 블라인드 라이브 중 drop 이거나 weak 인 수.
  A(표본 내) = 배포 임계 그대로(임계가 이 표본에서 정해져 과적합 참고값). B(hold-out) = logo_route 행 D(임계/신호를 스트리머 제외로 다시 정함, m=0.1) 위에 n_visual 임계도 스트리머 제외로 다시 정해 얹음(임계 = 학습 라이브 최댓값 + m x 범위).
shortcut: vis 표는 visual 트랙 프레임 204곡(라이브 133, N 71, 그중 신호 표와 맞는 163행)뿐이다. 스트리머 11명 표본이라 구간이 넓다.
배포 경로 vis = out/<방송>/4_scene.json 의 후보 vis(NAS 프레임 8장, 실제 배포가 쓰는 값). blind9 104행만 NAS 후보와 맞는다(blind5/6/78 은 치지직 옛 방송이라 out/ 에 없어 프로토 프레임 값을 쓴다).
shortcut: 같은 곡의 배포 - 프로토 vis 는 평균 +0.06, 표준편차 0.23, 범위 -0.59~+0.91(프레임 선택 잡음)이라 임계 근처 N 몇 곡의 노출 여부는 이 잡음이 정한다. 두 표를 같이 읽는다."""
import json, os, sys
from collections import Counter
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
            comps = n_visual.components([Image.open(f) for f in fs])                 # 성분 5개를 저장해 둔다: 폴드별로 mu/sd 를 다시 맞추는 독립 추정(refit_vis)에 쓴다
            rows.append(dict(key=r["key"], live=int(r["live"] == 1), set=r["set"], tag=r["tag"], name=r["name"], vis=n_visual.vis_of(comps, c), comps=comps))
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
        im = n_visual.frames_of(N.url_of(rows[g["vid"]]["path"]) if g["vid"] in rows else vod.url144(int(g["vid"])), g["frozen"]["s"], g["frozen"]["e"])      # n_visual.fill 과 같은 계산, 성분(comps)도 저장
        comps = n_visual.components(im) if len(im) >= 3 else None
        out.append(dict(id=g["id"], vis=n_visual.vis_of(comps) if comps else None, comps=comps))
    Path("cache/audit/vis_golden.json").write_text(json.dumps(out), encoding="utf8")
    v = [x["vis"] for x in out if x["vis"] is not None]
    print(f"golden {len(out)}곡 중 vis {len(v)}곡, 최대 {max(v):.3f}")


def golden_rows():
    n = {}
    for p in Path("data").glob("vods*.json"):
        n.update({str(v["videoNo"]): v["name"] for v in json.load(open(p, encoding="utf8"))})
    idx = {r["slug"]: r["streamer"] for r in json.load(open("data/nas_index.json", encoding="utf8"))}
    vg = {x["id"]: x for x in json.load(open("cache/audit/vis_golden.json", encoding="utf8"))}
    return pd.DataFrame([dict(key=f"golden/{g['id']}", live=1, set="golden", tag="", name=idx.get(g["vid"]) or n[g["vid"]], vis=vg[g["id"]]["vis"], comps=vg[g["id"]].get("comps"))
                         for g in json.load(open("experiments/golden_v4.json", encoding="utf8"))["songs"] if vg.get(g["id"], {}).get("vis") is not None])


def cal(write=False):
    """알려진 라이브 전부(visual 트랙 133곡 + golden 113곡을 배포 경로로 다시 점수화한 값)의 최댓값 + 0.1 x 범위. 144p 곡이 NAS 1080p 곡보다 높게 나와 visual 트랙의 133곡만으로는 임계가 낮았다."""
    import n_visual
    V = json.load(open(TAB, encoding="utf8")); Gd = json.load(open("cache/audit/vis_golden.json", encoding="utf8"))
    lv = np.array([x["vis"] for x in V if x["live"]] + [x["vis"] for x in Gd if x["vis"] is not None])
    c = n_visual.cal()
    thr = float(lv.max() + 0.1 * (lv.max() - lv.min()))
    import logo_route as LR
    d = deploy_vis(LR.with_golden(LR.load()))                        # 입력 출처(리뷰 A2-8): blind9 라이브 49곡을 프로토 클립 프레임 대신 배포 경로(4_scene) vis 로 바꾼 값과 비교
    lvd = np.array([d.get(x["key"], x["vis"]) for x in V if x["live"]] + [x["vis"] for x in Gd if x["vis"] is not None])
    thr_dep = float(lvd.max() + 0.1 * (lvd.max() - lvd.min()))
    new = dict(c, thr=thr, n_live=int(len(lv)), live_max=float(lv.max()), live_min=float(lv.min()),
               thr_note=f"입력 = 프로토 프레임 라이브 133곡(visual 트랙 클립 프레임: refs 50 + blind6 27 + blind5 7 + blind9 49, blind9 도 클립 프레임 점수) + golden 113곡(배포 경로 점수: NAS 1080p 또는 치지직 144p 프레임 8장) 중 알려진 라이브 {len(lv)}행(고유 곡은 218 이하)의 최댓값 + 0.1 x 범위. "
                        f"blind9 라이브를 4_scene 배포 경로 vis 로 바꿔 계산하면 {thr_dep:.3f}(blind9 N 노출·라이브 손실은 같음, integration.md 3절 5). 통합 때 0.8045 -> 이 값으로 올림(golden 144p 라이브 0.79 와의 간격 0.015 가 너무 얇아서). 표본 내 보정이다.")
    print(f"라이브 {len(lv)}곡 최대 {lv.max():.3f} 최소 {lv.min():.3f} -> 임계 {thr:.3f} (이전 {c['thr']:.3f}), blind9 라이브를 배포 경로 vis 로 치환하면 {thr_dep:.3f}")
    dup = sum(any(x["live"] and x["key"].startswith(f"blind9/{g['vid']}_") and abs(float(x["key"].rsplit("_", 1)[1]) - g["frozen"]["s"]) < 3 for x in V) for g in json.load(open("experiments/golden_v4.json", encoding="utf8"))["songs"] if "_" in g["vid"])
    print(f"고유 곡 수 {len(lv) - dup} 이하(blind9 와 golden 에 둘 다 있는 {dup}곡을 한 번만 센 값. 치지직 번호 방송과 NAS 방송의 같은 곡은 못 맞춰 더 겹칠 수 있다)")
    for nm, lo in (("최솟값", lv.min()), ("라이브 1% 분위", np.percentile(lv, 1))):          # 임계 여유는 최솟값 1곡(-1.58)이 정한다: 정의에 따른 민감도
        print(f"  여유 정의 {nm} {lo:.2f}: m=0.05 -> {lv.max() + 0.05 * (lv.max() - lo):.3f}, m=0.1 -> {lv.max() + 0.1 * (lv.max() - lo):.3f}")
    if write:
        Path("n_visual_cal.json").write_text(json.dumps(new, indent=1), encoding="utf8")
    return new


def refit_vis(C, fit):
    """성분 5개(n x 5) -> vis. n_visual.vis_of 와 같은 식이되 z 정규화의 mu/sd 를 fit 마스크 행으로 다시 맞춘다(cal 의 mu/sd 는 visual 트랙 204곡 전체의 평균/표준편차 ddof=0 이라 이 식으로 정확히 재현된다)"""
    return ((C - C[fit].mean(0)) / C[fit].std(0)).mean(1)


def veto(v, live, grp, m, C=None, fit=None, thr=None):
    """스트리머 hold-out: 그룹마다 학습 라이브 vis 최댓값 + m x 범위 초과면 걸림. 이 임계만 hold-out 이고 정규화(mu/sd)·프롬프트·모델 선택은 표본 내다(리뷰 A2-1, A2-2).
    C(성분)와 fit(mu/sd 를 맞출 행 마스크)을 주면 폴드마다 mu/sd 도 그룹을 뺀 학습 행으로 다시 맞춘 vis 로 판정한다(정규화까지 독립). thr 딕셔너리를 주면 폴드별 임계를 채운다."""
    hit = np.zeros(len(v), bool)
    for g in np.unique(grp):
        te, tr = grp == g, (grp != g) & (live == 1)
        vg = v if C is None else refit_vis(C, fit & ~te)
        t = vg[tr].max() + m * (vg[tr].max() - vg[tr].min())
        hit[te] = vg[te] > t
        if thr is not None:
            thr[g] = float(t)
    return hit


def deploy_vis(sig):
    """신호 표 blind9 행의 vis 를 4_scene.json(배포 경로)에서: 같은 방송 keep 후보 중 곡 구간과 50% 이상 겹치는 것. 못 찾으면 키가 빠진다."""
    d = {}
    for _, r in sig[sig.set == "blind9"].iterrows():
        p = Path("out") / r.vno / "4_scene.json"
        if not p.exists():
            continue
        a, b = r.start, r.start + r.len
        ov, sg = max((((min(b, s["end"]) - max(a, s["start"])) / max(b - a, 1), s) for s in json.load(open(p, encoding="utf8"))["segs"] if s.get("keep")), key=lambda t: t[0])
        if ov >= 0.5 and sg.get("vis") is not None:
            d[r.key] = sg["vis"]
    return d


def evaluate(deploy=True):
    import logo_route as LR, n_signals
    from scene_multi import P as MP
    import n_visual
    V = pd.DataFrame(json.load(open(TAB, encoding="utf8")))
    V = pd.concat([V, golden_rows()], ignore_index=True)           # hold-out 임계의 학습 라이브에 golden(배포 경로 점수)도 넣는다: 같은 스트리머 곡은 veto() 가 그룹 제외로 뺀다
    sig = LR.with_golden(LR.load())                                   # 라이브 풀 = 신호 표 88 + golden 라이브(표에 없는 것) = 136
    assert len(sig) - (sig.set == "golden").sum() == 163 and sig[sig.set == "golden"][["struct_cls", "speech_frac"]].notna().all().all(), "golden 행에 구조 규칙 입력이 채워져야 같은 규칙으로 센다(tstd 는 저장본에서 프레임을 못 읽은 15761307 의 5곡이 비어 있다)"
    if deploy:                                                        # blind9 행의 vis 를 배포 경로(4_scene) 값으로: 임계 학습(veto)과 노출 계산 모두 같은 표를 쓴다
        d = deploy_vis(sig)
        assert len(d) == 104, f"blind9 104행이 모두 NAS 후보와 맞아야 한다: {len(d)}"
        V["vis"] = [d.get(k, v) for k, v in zip(V.key, V.vis)]
    G = golden_rows().set_index("key").name                          # golden 행의 그룹은 방송이 아니라 스트리머로(스트리머 hold-out 에서 같은 스트리머가 학습에 섞이지 않게)
    sig["streamer"] = [G.get(k, n) for k, n in zip(sig.key, sig.name)]
    D, _ = LR.holdout(sig, "streamer", "D", 0.1)
    sig["D"] = D
    thr = n_visual.cal()["thr"]
    fl = np.array([bool(n_signals.fire(dict(rel_db=r, bursts=b))) for r, b in zip(sig.rel_db.fillna(0), sig.bursts_per_min.fillna(0))])
    sig["dep_ok"] = ~(((sig.struct_cls == "drop") | (sig.tstd > MP["motion"])).to_numpy() | fl)
    X = sig.merge(V[["key", "vis"]], on="key", how="left")
    print(f"\n=== {'배포 경로 vis(4_scene)' if deploy else '참고: 프로토 프레임 vis(cache/proto_visual)'} ===")
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
        for t in (0.8045, 0.907, 0.968, thr):                       # 임계 민감도: 라이브 손실 0 을 지키는 범위에서 N 노출이 임계에 얼마나 끌려가는지
            print(f"  A + n_visual 임계 {t:.3f}          노출 {int((N.dep_ok & (N.vis <= t)).sum()):2d}  라이브 손실 {int((~L.dep_ok | (L.vis > t)).sum())}")
        print(f"  B 행 D m=0.1(hold-out)          노출 {int((N.D == 'ok').sum()):2d}  라이브 손실 {int((L.D != 'ok').sum())}")
        out[sub] = dict(A=a, A_vis=a2, B=(int((N.D == "ok").sum()), int((L.D != "ok").sum())),
                        keys=dict(A=sorted(N.key[N.dep_ok]), A_vis=sorted(N.key[N.dep_ok & (N.vis <= thr)]), lost=sorted(L.key[~L.dep_ok | (L.vis > thr)])))      # 곡 집합: check.py 가 저장본과 비교(개수 단언은 임계 근처 N 때문에 거짓 실패/개선을 낸다)
        for m in (0.0, 0.1, 0.2):
            ft = {}
            hit = veto(V.vis.to_numpy(), V.live.to_numpy(), V.name.to_numpy(), m, thr=ft)
            if sub == "blind9" and m == 0.1:                         # 리뷰 A2-1: 폴드별 임계가 표본 내 임계와 같은 값이면 hold-out 이득은 독립 증거가 아니다
                mode, k = Counter(round(x, 3) for x in ft.values()).most_common(1)[0]
                print(f"  (vis 임계 m=0.1, 폴드 {len(ft)}개: 가장 흔한 값 {mode:.3f} 인 폴드 {k}개, 범위 {min(ft.values()):.3f}~{max(ft.values()):.3f}, 표본 내 임계 {thr:.3f})")
            H = dict(zip(V.key, hit))
            vh = Z.key.map(H).fillna(False).astype(bool)
            n_exp = int(((N.D == "ok") & ~vh[N.index]).sum()); l_lost = int(((L.D != "ok") | vh[L.index]).sum())
            n_only = int((N.dep_ok & ~vh[N.index]).sum()); l_only = int((~L.dep_ok | vh[L.index]).sum())
            print(f"  B + n_visual hold-out m={m}     노출 {n_exp:2d}  라이브 손실 {l_lost}   (배포 규칙 + hold-out vis 노출 {n_only}, 손실 {l_only})")
            out[sub][f"m{m}"] = (n_exp, l_lost)
            if not deploy and V.comps.notna().all():              # 정규화(mu/sd)까지 폴드마다 다시 맞춘 독립 추정. 성분이 있는 프로토 프레임 표에서만 가능(배포 경로 vis 는 성분을 저장하지 않는다)
                h2 = dict(zip(V.key, veto(V.vis.to_numpy(), V.live.to_numpy(), V.name.to_numpy(), m, np.array(V.comps.tolist()), (V.set != "golden").to_numpy())))
                vh2 = Z.key.map(h2).fillna(False).astype(bool)
                print(f"  B + n_visual 정규화까지 재적합 m={m}  노출 {int(((N.D == 'ok') & ~vh2[N.index]).sum()):2d}  라이브 손실 {int(((L.D != 'ok') | vh2[L.index]).sum())}   (배포 규칙 + 재적합 vis 노출 {int((N.dep_ok & ~vh2[N.index]).sum())}, 손실 {int((~L.dep_ok | vh2[L.index]).sum())})")
                out[sub][f"refit{m}"] = (int(((N.D == "ok") & ~vh2[N.index]).sum()), int(((L.D != "ok") | vh2[L.index]).sum()))
    return out


def selftest():
    import n_visual
    c = n_visual.cal()
    C = np.random.default_rng(0).normal(c["mu"], c["sd"], (50, 5))
    assert np.allclose(refit_vis(C, np.ones(50, bool)), [n_visual.vis_of(r, dict(mu=C.mean(0), sd=C.std(0))) for r in C])          # 전부 맞추면 vis_of 에 그 mu/sd 를 준 값과 같다
    v, live, grp = np.array([0, .3, 5, .1, .25, 4]), np.array([1, 1, 0, 1, 1, 0]), np.array(list("aaabbb"))
    th = {}
    hit = veto(v, live, grp, 0.5, thr=th)                          # a 의 임계 = b 라이브 .25 + .5 x (.25-.1), b 의 임계 = a 라이브 .3 + .5 x (.3-0)
    assert abs(th["a"] - 0.325) < 1e-9 and abs(th["b"] - 0.45) < 1e-9 and hit.tolist() == [False, False, True, False, False, True], (th, hit)
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:2] == ["selftest"]:
        selftest()
    elif sys.argv[1:2] == ["build"]:
        build()
    elif sys.argv[1:2] == ["golden"]:
        golden()
    elif sys.argv[1:2] == ["cal"]:
        cal("--write" in sys.argv)
    else:
        o = evaluate(True)
        evaluate(False)
        assert o["blind9"]["A"]["lA"] == 0, "배포 규칙이 blind9 라이브를 걸러서는 안 된다"
