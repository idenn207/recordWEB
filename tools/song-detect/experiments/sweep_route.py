"""route/장면/N 신호 임계의 GPU(torch) 대규모 탐색. route.tier + route.mark_likely(weak) + n_signals.fire 를 후보 표 위에서 벡터로 재현한다(등록부 known_* 없음).
  build   : 후보 표 생성 -> cache/proto_sweep/route_tab.csv (logo_route 신호 표 163행 + 표에 없는 golden 라이브 행; 각 행의 장면 거리 dl/dn 은 4_scene 의 multi_why 에서)
  check   : 벡터 구현을 route.tier/mark_likely/n_signals.fire 원본 코드와 무작위 설정 300개로 대조(차이 0 이어야 함) + 기본 설정의 노출 14/55, 라이브 걸림 0/136 재현
행 결과(노출 exposed) = 등급 auto|review 이고 weak 가 아님(완성본에 노출). 라이브 손실 = 노출 안 됨(drop 또는 weak). N 노출 = N 행이 노출된 수.
shortcut: 장면 분류(multi)는 저장값이 idle/watch/키프레임 없음인 17행의 dl/dn 을 몰라(저장 안 됨) 임계가 풀리면 unknown 으로 둔다. dense(한 방송에 곡 후보 20개 이상)는 likely 에만 쓰이고 이 표에서는 끈다."""
import json, os, sys, re
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
os.chdir(ROOT)
import numpy as np
import pandas as pd

TAB = ROOT / "cache/proto_sweep/route_tab.csv"
DEF = dict(idle=5.0, black=0.10, black_max=0.50, motion=34.5, weak=25.0, scene_drop=0.18, scene_ok=0.075, scene_idle=0.03, wait_s=300.0, len_lo=125.0, len_hi=340.0,
           rel_db=-5.7, bursts=2.1, speech=0.06)


def build():
    import loso_n, scene_pool, logo_route
    meta, F = scene_pool.pool()
    R = loso_n.records(meta, F)
    df = logo_route.load()
    byk = {r["key"]: r for r in R}
    rows = []
    for _, x in df.iterrows():
        g = byk[x.key]["g"]
        why = g.get("multi_why") or ""
        m = re.search(r"dl=([\d.]+)([<>])=?dn=([\d.]+)", why)
        if m:
            dl, dn = float(m.group(1)), float(m.group(3))
        elif why.startswith("weak"):
            dl, dn = 0.0, 1.0                                   # weak 로 내려간 것은 dl<dn 이었음
        else:
            dl, dn = np.nan, np.nan
        rows.append(dict(key=x.key, set=x.set, name=x["name"], group=x.group, live=int(x.live), tag=x.tag, start=x.start, len=x.len, has_refs=int(x.has_refs),
                         scene=x.scene, tstd=x.tstd, blk=x.blk, speech=x.speech, multi0=x.multi if isinstance(x.multi, str) and x.multi else "", nokf=int("키프레임" in why),
                         dl=dl, dn=dn, rel_db=x.rel_db, bursts=x.bursts_per_min, golden=0))
    d2 = logo_route.with_golden(df)
    d2 = d2[d2.set == "golden"]
    gold = json.load(open(ROOT / "experiments/golden_v4.json", encoding="utf8"))["songs"]
    nm = {}
    for p in Path("data").glob("vods*.json"):
        for v in json.load(open(p, encoding="utf8")):
            nm[str(v["videoNo"])] = v["name"]
    for k, v in zip(df.vno, df.name):
        nm.setdefault(str(k), v)
    for _, x in d2.iterrows():
        e = next(s for s in gold if f"golden/{s['id']}" == x.key)
        sc = json.load(open(ROOT / "out" / e["vid"] / "4_scene.json", encoding="utf8"))
        import audit_engine as E
        K = E.kept(e["vid"])
        k = next((i for i, g in enumerate(K) if abs(g["start"] - e["refine"][0]) < 0.2 and abs(g["end"] - e["refine"][1]) < 0.2), None)
        g = sc["segs"][k]
        why = g.get("multi_why") or ""
        m = re.search(r"dl=([\d.]+)([<>])=?dn=([\d.]+)", why)
        dl, dn = (float(m.group(1)), float(m.group(3))) if m else ((0.0, 1.0) if why.startswith("weak") else (np.nan, np.nan))
        rows.append(dict(key=x.key, set="golden", name=nm.get(e["vid"], x["name"]), group=f"golden|{e['vid']}", live=1, tag="", start=x.start, len=x.len, has_refs=int(bool(sc["has_refs"])),
                         scene=g.get("scene"), tstd=g.get("tstd"), blk=g.get("blk"), speech=g.get("speech"), multi0=g.get("multi") or "", nokf=int("키프레임" in why), dl=dl, dn=dn,
                         rel_db=x.rel_db, bursts=x.bursts_per_min, golden=1))
    t = pd.DataFrame(rows)
    t.to_csv(TAB, index=False, encoding="utf-8")
    print(f"{TAB}: {len(t)}행 (라이브 {int(t.live.sum())}, N {int((t.live == 0).sum())}, golden 추가 {int(t.golden.sum())})")
    return t


def load():
    if not TAB.exists():
        return build()
    return pd.read_csv(TAB, na_values=[""], keep_default_na=True, dtype={"multi0": str, "tag": str}).fillna({"multi0": "", "tag": ""})


def tensors(t, dev="cuda"):
    import torch
    f = lambda c, fill=np.nan: torch.tensor(t[c].fillna(fill).to_numpy(np.float32), device=dev)
    T = {c: f(c) for c in ("start", "len", "scene", "tstd", "blk", "speech", "dl", "dn", "rel_db", "bursts")}
    T["has_refs"] = torch.tensor(t.has_refs.to_numpy().astype(bool), device=dev)
    T["nokf"] = torch.tensor(t.nokf.to_numpy().astype(bool), device=dev)
    T["m0none"] = torch.tensor((t.multi0 == "").to_numpy(), device=dev)         # 저장된 multi 가 없는 행(4_scene 없음): 장면 규칙 대상 아님
    T["live"] = torch.tensor(t.live.to_numpy().astype(bool), device=dev)
    return T


def outcomes(P, T):
    """P: {이름: [C] 텐서(또는 스칼라)}. 반환 exposed, auto, likely 각각 [C, N] bool. route.tier -> mark_likely 의 weak 와 같은 순서를 그대로 옮김."""
    import torch
    g = lambda k: P[k].reshape(-1, 1) if torch.is_tensor(P[k]) else torch.tensor(float(P[k]), device=T["start"].device).reshape(1, 1)
    nan = torch.isnan
    tstd = torch.nan_to_num(T["tstd"], nan=0.0)[None]                  # g.get('tstd') or 0
    blk = torch.nan_to_num(T["blk"], nan=0.0)[None]
    dlv, dnv = T["dl"][None], T["dn"][None]
    dl_known = ~nan(dlv)
    # 장면 분류 재계산 (scene_multi.classify): idle -> 검은 띠 -> 움직임 -> dl<dn(+weak 대역)
    idle = tstd < g("idle")
    black = (blk > g("black")) & (blk <= g("black_max"))
    mot = tstd > g("motion")
    lt = dl_known & (dlv < dnv)
    live = lt & (tstd < g("weak"))
    multi_idle = idle & ~T["nokf"][None]
    multi_watch = ~idle & (black | mot) & ~T["nokf"][None]
    multi_live = ~idle & ~black & ~mot & live & ~T["nokf"][None]
    none = T["m0none"][None]
    multi_idle, multi_watch, multi_live = multi_idle & ~none, multi_watch & ~none, multi_live & ~none
    # route.tier: m != idle 이고 tstd > motion 이면 watch
    watch_route = (~multi_idle & (tstd > g("motion"))) | multi_watch
    drop = multi_idle | watch_route
    drop = drop | (T["start"][None] < g("wait_s"))
    sc = T["scene"][None]
    sc_known = ~nan(sc)
    far = T["has_refs"][None] & sc_known & (sc > g("scene_drop"))
    m_lu = ~(multi_idle | multi_watch)                                     # m in (live, unknown) 또는 None(4_scene 없음은 None 이라 아님)
    m_lu = m_lu & ~none
    drop = drop | (far & ~m_lu)
    review_far = far & m_lu
    auto = (~drop) & (~review_far) & T["has_refs"][None] & sc_known & (sc >= g("scene_idle")) & (sc <= g("scene_ok")) & (T["len"][None] >= g("len_lo")) & (T["len"][None] <= g("len_hi"))
    # weak: n_signals.fire 가 판단 가능하면 그 결과, 아니면 움직임 대역
    has_sig = ~nan(T["rel_db"][None]) & ~nan(T["bursts"][None])
    fired = (T["rel_db"][None] < g("rel_db")) | (T["bursts"][None] > g("bursts"))
    band = (g("weak") <= tstd) & (tstd <= g("motion"))
    weak = torch.where(has_sig, fired, band)
    exposed = ~drop & ~weak
    inlen = (T["len"][None] >= g("len_lo")) & (T["len"][None] <= g("len_hi"))
    sp = torch.nan_to_num(T["speech"], nan=0.0)[None]
    likely = exposed & ~auto & multi_live & (sp < g("speech")) & inlen & (T["start"][None] >= g("wait_s"))
    return exposed, auto & exposed, likely


def reference(t, cfg):
    """원본 코드(route.tier, n_signals.fire, route.mark_likely 의 weak/likely)로 같은 표를 계산한 (exposed, auto, likely) 배열 - 벡터 구현 대조용."""
    import route, scene_multi, n_signals, tune
    undo = tune.apply({f"route.P.{k}": v for k, v in cfg.items() if k in ("scene_drop", "scene_ok", "scene_idle", "wait_s", "len_lo", "len_hi")} |
                      {f"scene_multi.P.{k}": v for k, v in cfg.items() if k in ("idle", "black", "black_max", "motion", "weak")} |
                      {f"n_signals.P.{k}": v for k, v in cfg.items() if k in ("rel_db", "bursts")})
    P = scene_multi.P
    E, A, L = [], [], []
    try:
        for _, x in t.iterrows():
            tstd, blk = (0.0 if pd.isna(x.tstd) else x.tstd), (0.0 if pd.isna(x.blk) else x.blk)
            if x.multi0 == "":
                m = None
            elif x.nokf:
                m = "unknown"
            elif tstd < P["idle"]:
                m = "idle"
            elif P["black"] < blk <= P["black_max"]:
                m = "watch"
            elif tstd > P["motion"]:
                m = "watch"
            else:
                lt = (not pd.isna(x.dl)) and x.dl < x.dn
                m = "live" if (lt and tstd < P["weak"]) else "unknown"
            g = dict(keep=True, start=x.start, len=x.len, end=x.start + x.len, scene=None if pd.isna(x.scene) else x.scene, multi=m, tstd=None if pd.isna(x.tstd) else x.tstd, speech=0.0 if pd.isna(x.speech) else x.speech)
            if not pd.isna(x.rel_db) and not pd.isna(x.bursts):
                g["rel_db"], g["bursts"] = x.rel_db, x.bursts
            g["tier"], g["tier_why"] = route.tier(g, bool(x.has_refs))
            route.mark_likely([g], p=dict(route.P, **{k: v for k, v in cfg.items() if k in ("len_lo", "len_hi", "wait_s")}))
            ex = g["tier"] in ("auto", "review") and not g["weak"]
            E.append(ex); A.append(ex and g["tier"] == "auto"); L.append(bool(g["likely"]))
    finally:
        undo()
    return np.array(E), np.array(A), np.array(L)


def check(n=300, seed=0):
    import torch
    t = load()
    T = tensors(t)
    rng = np.random.default_rng(seed)
    def draw():
        return dict(idle=rng.uniform(1, 12), black=rng.uniform(0.02, 0.3), black_max=rng.uniform(0.35, 0.7), motion=rng.uniform(20, 45), weak=rng.uniform(10, 34), scene_drop=rng.uniform(0.1, 0.3),
                    scene_ok=rng.uniform(0.04, 0.12), scene_idle=rng.uniform(0.005, 0.05), wait_s=rng.uniform(0, 600), len_lo=rng.uniform(90, 160), len_hi=rng.uniform(300, 400),
                    rel_db=rng.uniform(-9, -2), bursts=rng.uniform(1, 4), speech=0.06)
    cfgs = [dict(DEF)] + [draw() for _ in range(n)]
    P = {k: torch.tensor([c[k] for c in cfgs], device="cuda", dtype=torch.float32) for k in DEF}
    E, A, L = (x.cpu().numpy() for x in outcomes(P, T))
    bad = 0
    for i, c in enumerate(cfgs):
        e, a, l = reference(t, c)
        d = (e != E[i]).sum() + (a != A[i]).sum() + (l != L[i]).sum()
        if d:
            bad += 1
            if bad <= 5:
                j = np.flatnonzero((e != E[i]) | (a != A[i]) | (l != L[i]))
                print("차이", i, {k: round(v, 3) for k, v in c.items()}, [(t.key[q], bool(e[q]), bool(E[i][q]), bool(a[q]), bool(A[i][q]), bool(l[q]), bool(L[i][q]), t.tstd[q], t.scene[q], t.multi0[q]) for q in j[:3]])
    print(f"원본 대조: 설정 {len(cfgs)}개 중 차이 난 설정 {bad}")
    live = t.live.to_numpy().astype(bool)
    b9 = (t.set == "blind9").to_numpy()
    e0 = E[0]
    print(f"기본 설정: blind9 N 노출 {int((e0 & ~live & b9).sum())}/{int((~live & b9).sum())}, 라이브 {int(live.sum())} 중 손실 {int((~e0 & live).sum())}, auto N {int((A[0] & ~live).sum())}, auto 라이브 {int((A[0] & live).sum())}, likely {int(L[0].sum())}")
    assert bad == 0
    return t


if __name__ == "__main__":
    if sys.argv[1:] == ["build"]:
        build()
    elif sys.argv[1:] == ["check"]:
        check()
