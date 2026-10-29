"""단계 매니페스트 + 증거 카드 v2 (하네스 시제품). 단계마다 '입력 해시 + 코드 버전'을 키로 기록하고, 키가 달라진 단계만 다시 돌린다.
  final : 2_refine.json + wav/점수/vocal 파일 서명 | 코드 = snap.py, finalize.py (AST 해시: 주석/공백/독스트링 변경은 stale 아님)
  sig   : 후보(시작/끝 0.1초) 단위 n_signals.fill 결과(bursts, rel_db) | 코드 = n_signals 의 계산 함수만(임계 P 는 제외)
  scene : 후보 단위 재사용(경계가 같은 후보는 이전 4_scene 값 그대로). NAS 가 필요해서 경계가 바뀐 후보만 scene_fn 으로 다시 계산
  route : 4_scene + sig + 이 방송에 해당하는 등록부 항목(approved/known_negatives) | 코드 = route.py, n_signals.py, scene_multi.py, piano_gate.py
카드 v2(cards2.json): route 입력 전부(g_in) + 경계 이력(stages) + 결정. replay.py 가 카드만으로 결정을 다시 계산한다.
사용: python harness/manifest.py plan|run   /   python harness/manifest.py selftest   (스크래치 cache/proto_harness/out 에서만)
shortcut: 파일 서명은 크기+mtime(내용 해시 아님, wav 39GB), 경계가 같은 후보를 같은 후보로 본다(0.1초 반올림), scene 코드가 바뀌면 stale 로 보고 후보 단위 재사용은 호출자가 정한다."""
import ast, hashlib, json, os, sys, time
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.lib import *
import numpy as np

CODE = {"final": [("snap.py", None), ("finalize.py", None)],
        "sig": [("n_signals.py", ("_bursts", "speech_db", "fill"))],
        "scene": [("scene_multi.py", None), ("scene.py", None), ("scene_pool.py", None), ("n_visual.py", None)],
        "route": [("route.py", None), ("n_signals.py", None), ("scene_multi.py", None), ("piano_gate.py", None), ("pipeline.py", ("decide", "card", "card_file", "hms")), ("n_visual.py", ("fire", "cal", "CAL"))]}


def _strip(n):
    for x in ast.walk(n):
        b = getattr(x, "body", None)
        if isinstance(b, list) and b and isinstance(b[0], ast.Expr) and isinstance(getattr(b[0], "value", None), ast.Constant) and isinstance(b[0].value.value, str):
            b[:] = b[1:] or [ast.Pass()]
    return n


_CK = {}


def code_key(stage):
    """프로세스 안에서는 한 번만 계산(파일이 실행 중에 안 바뀐다고 본다)"""
    if stage not in _CK:
        _CK[stage] = _code_key(stage)
    return _CK[stage]


def _code_key(stage):
    h = hashlib.sha1()
    for f, names in CODE[stage]:
        tree = ast.parse((ROOT / f).read_text(encoding="utf8"))
        nodes = [n for n in tree.body if names is None or getattr(n, "name", None) in names]
        h.update(f.encode() + ast.dump(_strip(ast.Module(nodes, []))).encode())
    return h.hexdigest()[:12]


def sig_of(p):
    p = Path(p)
    return f"{p.stat().st_size}:{p.stat().st_mtime_ns}" if p.exists() else "-"


def h(*parts):
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:12]


def fh(p):
    return hashlib.sha1(Path(p).read_bytes()).hexdigest()[:12] if Path(p).exists() else "-"


def seg_key(g):
    return f"{g['start']:.1f}-{g['end']:.1f}"


_REG = {}


def registry_for(vid):
    """이 방송에 해당하는 등록부 항목만 해시한다: 다른 방송의 등록은 이 방송의 route 를 stale 로 만들지 않는다. (등록부 파일은 mtime 이 바뀔 때만 다시 읽는다)"""
    out = []
    for f in ("data/approved.json", "data/known_negatives.json"):
        sg = sig_of(ROOT / f)
        if _REG.get(f, (None,))[0] != sg:
            _REG[f] = (sg, json.load(open(ROOT / f, encoding="utf8")))
        out.append([k for k in _REG[f][1] if str(k["videoNo"]) == str(vid)])
    return out


IN_KEYS = ("keep", "why", "start", "end", "len", "multi", "tstd", "blk", "scene", "speech", "music", "vocal", "cover", "bursts", "rel_db", "piano", "other", "vis")


class Run:
    def __init__(self, root=PH / "out_m", scene_fn=None, vis_fn=None, refs_fn=None):
        self.root, self.scene_fn, self.vis_fn, self.refs_fn = Path(root), scene_fn, vis_fn, refs_fn      # vis_fn(slug, segs): 화면 신호 g["vis"] 채우기(n_visual, GPU 호스트에서만). refs_fn(slug): 현재 풀로 계산한 has_refs(없으면 이전 4_scene 값 그대로)
        self.mf = self.root / "manifest.json"
        try:
            self.M = json.load(open(self.mf)) if self.mf.exists() else {}
        except ValueError:                                         # 쓰다 중단돼 깨진 기록: 기록 없음으로 본다(전부 stale 이라 다시 계산할 뿐 틀린 결과는 안 나온다)
            self.M = {}
        self.partial = set()                                       # 화면 신호(vis)가 덜 채워진 방송: scene/route 키를 기록하지 않아 다음 실행에 다시 한다
        self.R = {r["slug"]: r for r in rows()}
        self.t = {}          # 단계별 누적 실행 시간(초)
        self.n = {}          # 단계별 실행 수(scene/sig 는 후보 수)

    def wav(self, s):
        return Path(self.R[s]["wav"])

    def key(self, stage, s):
        d, w = self.root / s, self.wav(s)
        det = ROOT / "cache/detect" / w.stem
        if stage == "final":
            return h(code_key("final"), fh(d / "2_refine.json"), sig_of(w), sig_of(str(det) + ".scores.npy"), sig_of(str(det) + ".vocal.json"))
        if stage == "scene":
            return h(code_key("scene"), fh(d / "3_final.json"), *self.pool_sigs(), self.vis_cal())
        if stage == "route":
            return h(code_key("route"), fh(d / "4_scene.json"), registry_for(s), sig_of(ROOT / "cache/exp12p/other.json"), code_key("sig"), fh(ROOT / "n_visual_cal.json"))
        raise KeyError(stage)

    def pool_sigs(self):
        """scene_pool.pool() 이 읽는 파일 전부(프레임 npz, 메타 json, 추가 참조 npz/json, 날짜용 refs.json)의 서명"""
        return [sig_of(ROOT / p) for p in ("cache/scene_pool.npz", "cache/scene_pool.json", "cache/scene_pool_refs.npz", "cache/scene_pool_refs.json", "data/refs.json")]

    def vis_cal(self):
        """vis 점수를 바꾸는 보정(mu, sd)만. 임계 thr 은 route 단계에서만 쓰므로 빠진다(thr 만 바뀌면 NAS 를 다시 읽지 않는다)"""
        c = json.load(open(ROOT / "n_visual_cal.json", encoding="utf8")) if (ROOT / "n_visual_cal.json").exists() else {}
        return h(c.get("mu"), c.get("sd"))

    def plan(self, slugs):
        """슬러그별로 stale 인 단계 목록. 앞 단계가 stale 면 뒤 단계도 stale 로 본다(실행해 보면 결과가 같을 수 있으나 키로는 모름)."""
        out = {}
        for s in slugs:
            m, st = self.M.get(s, {}), []
            for stage in ("final", "scene", "route"):
                if st or m.get(stage) != self.key(stage, s):
                    st.append(stage)
            out[s] = st
        return out

    def _tick(self, stage, t0, n=1):
        self.t[stage] = self.t.get(stage, 0) + time.perf_counter() - t0
        self.n[stage] = self.n.get(stage, 0) + n

    def final(self, s):
        t0 = time.perf_counter()
        from finalize import fix
        from snap import pcm_of, voc_of
        from paths import cache_of
        w = self.wav(s)
        pcm, a, voc = pcm_of(w), np.load(cache_of(w, ".scores.npy")), voc_of(w)
        segs = [fix(pcm, a, g, voc) for g in json.load(open(self.root / s / "2_refine.json", encoding="utf8"))]
        (self.root / s / "3_final.json").write_text(json.dumps(segs, ensure_ascii=False, indent=1), encoding="utf8")
        self._tick("final", t0)

    def scene(self, s):
        """경계가 같은 후보는 이전 4_scene 의 장면 필드를 그대로, 다른 후보는 scene_fn(slug, g) (없으면 겹침 80% 이상인 이전 후보 값을 근사로 쓰고 scene_approx 표시)."""
        t0 = time.perf_counter()
        d = self.root / s
        old = json.load(open(d / "4_scene.json", encoding="utf8")) if (d / "4_scene.json").exists() else dict(has_refs=False, segs=[])
        ck = h(code_key("scene"), *self.pool_sigs(), fh(ROOT / "n_visual_cal.json"))
        # scene_fn 이 있는 실사용에서는 scene 코드/풀이 지난 실행과 같을 때만 후보를 재사용한다(black_max 같은 임계나 풀이 바뀌면 같은 경계라도 multi 가 달라질 수 있어 전부 다시 읽는다).
        # scene_fn 이 없는 점검용(check.py)은 예전처럼 항상 재사용/근사
        reuse = self.scene_fn is None or self.M.get(s, {}).get("scene_in") == ck
        prev = {seg_key(g): g for g in old["segs"]} if reuse else {}
        FIELDS = ("multi", "multi_why", "tstd", "blk", "scene", "vis")
        new, redo = [], 0
        for g in (x for x in json.load(open(d / "3_final.json", encoding="utf8")) if x["keep"]):
            p = prev.get(seg_key(g))
            if p is not None:
                g.update({k: p.get(k) for k in FIELDS})
            else:
                redo += 1
                if self.scene_fn:
                    g.update(self.scene_fn(s, g))
                else:
                    best = max(old["segs"], key=lambda q: min(g["end"], q["end"]) - max(g["start"], q["start"]), default=None) if reuse else None
                    ov = best and (min(g["end"], best["end"]) - max(g["start"], best["start"])) / max(g["len"], 1e-9)
                    if best and ov >= 0.8:
                        g.update({k: best.get(k) for k in FIELDS}); g["scene_approx"] = True
            new.append(g)
        if self.vis_fn:
            self.vis_fn(s, new)                                    # 재사용한 후보는 vis 가 이미 있어 건너뛰고, 새/바뀐 후보만 프레임을 읽는다
        if self.vis_fn and any(g.get("vis") is None for g in new):
            self.partial.add(s)                                    # 건너뛴(의존성 없음) 또는 못 읽은 후보가 있으면 완료로 기록하지 않는다
        (d / "4_scene.json").write_text(json.dumps(dict(has_refs=self.refs_fn(s) if self.refs_fn else old["has_refs"], segs=new), ensure_ascii=False, indent=1), encoding="utf8")
        self.M.setdefault(s, {})["scene_in"] = ck                  # 쓰기까지 끝낸 뒤에만 기록(중간 실패 때 옛 값이 새 코드 기준으로 보이지 않게)
        self._tick("scene", t0, redo)
        return redo

    def sig(self, s, segs):
        """bursts/rel_db 를 후보 단위로 캐시(sig.json). 캐시에 없는 후보만 n_signals.fill 이 wav 를 열어 계산한다."""
        import n_signals
        f = self.root / s / "sig.json"
        C = json.load(open(f)) if f.exists() else {}
        ck = h(code_key("sig"), sig_of(self.wav(s)), sig_of(str(ROOT / "cache/detect" / self.wav(s).stem) + ".scores.npy"))      # n_signals 가 읽는 점수 npy 가 바뀌면 캐시도 무효
        if C.get("_ck") != ck:
            C = {"_ck": ck}
        todo = []
        for g in segs:
            c = C.get(seg_key(g))
            if c:
                g["bursts"], g["rel_db"] = c
            elif g.get("keep"):
                todo.append(g)
        if todo:
            t0 = time.perf_counter()
            n_signals.fill(todo, self.wav(s))
            for g in todo:
                C[seg_key(g)] = [g.get("bursts"), g.get("rel_db")]
            f.write_text(json.dumps(C))
            self._tick("sig", t0, len(todo))

    def route(self, s):
        t0 = time.perf_counter()
        import pipeline, piano_gate
        d = self.root / s
        sc = json.load(open(d / "4_scene.json", encoding="utf8"))
        segs = sc["segs"]
        self.sig(s, segs)
        piano_gate.annotate(s, segs)
        ins = [{k: g.get(k) for k in IN_KEYS} for g in segs]            # 카드 v2: 결정 입력은 결정 전에 복사
        pipeline.decide(s, segs, sc["has_refs"])                        # pipeline.main 과 같은 코드
        (d / "cards").mkdir(exist_ok=True)
        for old in (d / "cards").glob("*.json"):
            old.unlink()
        cards = []
        for i, (g, inp) in enumerate(zip(segs, ins), 1):
            c = pipeline.card(g, i)
            pipeline.card_file(d, i, g).write_text(json.dumps(c, ensure_ascii=False, indent=1), encoding="utf8")     # pipeline.main 이 SONG_NOCLIP=1 로 쓰는 카드 파일과 같다(클립 없음)
            c["slug"], c["has_refs"], c["g_in"] = s, sc["has_refs"], inp
            cards.append(c)
        (d / "cards2.json").write_text(json.dumps(cards, ensure_ascii=False), encoding="utf8")
        self._tick("route", t0)
        return cards

    def run(self, slugs, force=()):
        P = self.plan(slugs)
        try:
            for s, st in P.items():
                if "final" in st or "final" in force:
                    self.final(s)
                if "scene" in st or "scene" in force:
                    self.scene(s)
                if "route" in st or "route" in force:
                    self.route(s)
                done = ("final",) if s in self.partial else ("final", "scene", "route")
                self.M[s] = {**self.M.get(s, {}), **{k: self.key(k, s) for k in done}}
        finally:                                                  # 중간에 NasDown 등으로 멈춰도 끝낸 방송은 기록한다(못 끝낸 방송은 키가 안 맞아 다음에 다시 계산)
            tmp = self.mf.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self.M, indent=1))
            os.replace(tmp, self.mf)                              # 쓰다 중단돼도 옛 기록이 그대로(깨진 JSON 이 남지 않게)
        return P


def selftest():
    a = ast.dump(_strip(ast.parse('def f():\n    """x"""\n    return 1  # c\n')))
    b = ast.dump(_strip(ast.parse('def f():\n    """yy"""\n    return 1\n')))
    assert a == b                       # 주석과 독스트링 변경은 같은 해시
    assert h(1, 2) == h(1, 2) and h(1, 2) != h(1, 3)
    assert code_key("route") == code_key("route") and len(code_key("final")) == 12
    import tempfile
    root = Path(tempfile.mkdtemp()); (root / "x").mkdir()           # 장면 재사용 규칙: scene_fn 이 있으면 scene 코드/풀 키가 지난 실행과 같을 때만 같은 경계의 후보를 재사용한다
    seg = lambda a: dict(keep=True, start=a, end=a + 200.0, len=200.0)
    (root / "x" / "4_scene.json").write_text(json.dumps(dict(has_refs=True, segs=[dict(seg(0.0), multi="old", multi_why="", tstd=1.0, blk=0.0, scene=0.1), dict(seg(300.0), multi="old", multi_why="", tstd=1.0, blk=0.0, scene=0.1)])))
    (root / "x" / "3_final.json").write_text(json.dumps([seg(0.0), seg(300.5)]))             # 두 번째 후보 경계가 바뀜
    calls = []
    fn = lambda slug, g: calls.append(g["start"]) or dict(multi="new", multi_why="", tstd=2.0, blk=0.0, scene=0.2)
    r = Run(root, scene_fn=fn)
    assert r.scene("x") == 2 and calls == [0.0, 300.5]              # 처음(기록 없음)에는 전부 다시 읽는다
    calls.clear(); (root / "x" / "3_final.json").write_text(json.dumps([seg(0.0), seg(301.0)]))
    assert r.scene("x") == 1 and calls == [301.0]                    # 같은 코드/풀: 경계가 같은 후보는 재사용
    assert "x" not in r.partial                                      # vis_fn 이 없으면 완료
    r.vis_fn = lambda slug, segs: None; r.scene("x")
    assert "x" in r.partial                                          # vis 가 비면(의존성 없음/읽기 실패) 완료로 기록하지 않는다
    r.partial.clear(); r.vis_fn = lambda slug, segs: [g.update(vis=0.1) for g in segs]; r.scene("x")
    assert "x" not in r.partial
    r.M["x"]["scene_in"] = "다른키"; calls.clear()
    assert r.scene("x") == 2 and len(calls) == 2                     # 코드/풀이 바뀌면 같은 경계도 전부 다시
    print("selftest ok")


if __name__ == "__main__":
    if sys.argv[1:2] == ["selftest"]:
        selftest(); sys.exit()
    r = Run()
    sl = seed_scratch(root=r.root)
    if sys.argv[1] == "plan":
        P = r.plan(sl); print({s: v for s, v in P.items() if v} or "전부 최신")
    else:
        t = time.perf_counter(); P = r.run(sl); print(f"실행 {time.perf_counter() - t:.1f}초 단계별 {r.t} 실행수 {r.n}")
