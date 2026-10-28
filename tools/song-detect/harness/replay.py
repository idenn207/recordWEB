"""축 (b) 결정 재생(replay): 증거 카드 v2(cards2.json)만으로 등급 결정(route.tier -> known_pos -> known_neg -> mark_likely)을 다시 계산한다.
wav, 점수 캐시, NAS 를 열지 않는다. 임계/규칙 변형을 인자로 받아 초 단위로 비교한다.
라벨은 등록부에서 만든다(approved: boundary_ok False = B, 나머지 = L / known_negatives = N / 그 외 U). 등록부를 끈 모드(registry=False)가 'N 노출을 등록부에 기대지 않고' 본 수치다.
사용: python harness/replay.py [selftest|baseline]"""
import copy, glob, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.lib import *

RK = {"auto": 3, "review": 2, "optional": 1, "drop": 0}


def load_cards(root=PH / "out_m"):
    return [c for f in sorted(glob.glob(str(root / "*/cards2.json"))) for c in json.load(open(f, encoding="utf8"))]


def labels(cards):
    A = json.load(open(ROOT / "data/approved.json", encoding="utf8"))
    K = json.load(open(ROOT / "data/known_negatives.json", encoding="utf8"))
    out = []
    for c in cards:
        L = c["end"] - c["start"]
        ov = lambda k: min(c["end"], k["end"]) - max(c["start"], k["start"])
        hit = lambda k: str(k["videoNo"]) == c["slug"] and ov(k) >= 0.5 * min(L, k["end"] - k["start"])
        n = [k for k in K if hit(k)]
        a = [k for k in A if hit(k)]
        out.append("N" if n else ("B" if a and all(k.get("boundary_ok") is False for k in a) else ("L" if a else "U")))
    return out


class Replayer:
    """카드 목록을 방송별로 묶어 g 를 복원해 두고, run(params, registry) 로 등급을 다시 계산한다."""

    def __init__(self, cards):
        import route, scene_multi, n_signals
        self.route, self.MP, self.NP = route, scene_multi.P, n_signals.P
        self.cards = cards
        self.by = {}
        for i, c in enumerate(cards):
            self.by.setdefault(c["slug"], []).append(i)
        self.sh = cache_registries()
        self.reg = {f: self.sh.load(open(ROOT / f, encoding="utf8")) for f in ("data/approved.json", "data/known_negatives.json")}   # 등록부 원본(shim 에 올려 둠)
        self.sh._c.update({f.split("/")[-1]: v for f, v in self.reg.items()})

    def run(self, rp=None, mp=None, npp=None, registry=True, extra=None):
        """rp/mp/npp = route.P / scene_multi.P / n_signals.P 덮어쓰기(이 호출 안에서만). extra(g) 가 있으면 tier 뒤에 추가 규칙으로 등급을 바꿈(실험용 훅). 반환: [(tier, likely, weak)]"""
        R, sv = self.route, []
        for d, o in ((R.P, rp), (self.MP, mp), (self.NP, npp)):
            if o:
                sv.append((d, dict(d))); d.update(o)
        a = self.sh._c["approved.json"], self.sh._c["known_negatives.json"]
        if not registry:
            self.sh._c["approved.json"] = self.sh._c["known_negatives.json"] = []
        res = [None] * len(self.cards)
        try:
            for s, idx in self.by.items():
                segs = []
                for i in idx:
                    c = self.cards[i]
                    g = dict(c["g_in"]); g.update(has_refs=c["has_refs"])
                    g["tier"], g["tier_why"] = R.tier(g, c["has_refs"])
                    if extra:
                        extra(g, c)
                    R.known_pos(s, g); R.known_neg(s, g)
                    segs.append(g)
                R.mark_likely(segs)
                for i, g in zip(idx, segs):
                    res[i] = (g["tier"], g["likely"], g["weak"], g["tier_why"])
        finally:
            for d, o in sv:
                d.clear(); d.update(o)
            self.sh._c["approved.json"], self.sh._c["known_negatives.json"] = a
        return res


def metrics(lab, res):
    """등급 결과 + 라벨 -> 라이브 손실 / N 노출 / 분포. 완성본 노출 = auto 또는 (review 이고 weak 아님). 손실 = 라이브(L,B)가 drop 이거나 weak review."""
    vis = lambda r: r[0] == "auto" or (r[0] in ("review", "optional") and not r[2])
    m = dict(n=len(res), auto=sum(r[0] == "auto" for r in res), review=sum(r[0] == "review" for r in res), drop=sum(r[0] == "drop" for r in res))
    for L in ("L", "B", "N"):
        ix = [i for i, x in enumerate(lab) if x == L]
        m[L] = len(ix)
    m["L_loss"] = sum(lab[i] == "L" and not vis(res[i]) for i in range(len(res)))
    m["B_loss"] = sum(lab[i] == "B" and not vis(res[i]) for i in range(len(res)))
    m["L_drop"] = sum(lab[i] == "L" and res[i][0] == "drop" for i in range(len(res)))
    m["N_expose"] = sum(lab[i] == "N" and vis(res[i]) for i in range(len(res)))
    m["N_auto"] = sum(lab[i] == "N" and res[i][0] == "auto" for i in range(len(res)))
    return m


if __name__ == "__main__":
    cards = load_cards()
    lab = labels(cards)
    from collections import Counter
    print(len(cards), "카드", Counter(lab))
    rp = Replayer(cards)
    t = time.perf_counter(); res = rp.run(); dt = time.perf_counter() - t
    assert all(r[:2] == (c["tier"], c["likely"]) and r[2] == c["weak"] for r, c in zip(res, cards)), "재생이 저장된 결정과 다름"
    print(f"재생 {dt * 1000:.0f}ms, 저장 결정과 191/191 동일")
    print("등록부 있음", metrics(lab, res))
    print("등록부 없음", metrics(lab, rp.run(registry=False)))
