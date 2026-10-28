"""하네스 공통: 슬러그 목록, 스크래치 out 루트(cache/harness/out), 등록부 읽기 캐시(replay 속도용).
메인 out/ 은 읽기만 한다: 스크래치로 복사해서 쓴다."""
import json, os, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
os.chdir(ROOT)
PH = ROOT / "cache" / "harness"
SCR = PH / "out"
STAGE_FILES = ("1_detect.json", "2_refine.json", "3_final.json", "4_scene.json")


def rows():
    return json.load(open(ROOT / "data/nas_index.json", encoding="utf8"))


def seed_scratch(files=STAGE_FILES, slugs=None, root=None):
    """메인 out/<slug>/ 의 단계 json 을 스크래치로 복사(이미 있으면 건너뜀). 반환: 슬러그 목록"""
    out = []
    for r in rows():
        if slugs and r["slug"] not in slugs:
            continue
        d = (root or SCR) / r["slug"]
        d.mkdir(parents=True, exist_ok=True)
        for f in files:
            if not (d / f).exists():
                shutil.copy(ROOT / "out" / r["slug"] / f, d / f)
        out.append(r["slug"])
    return out


class _JsonShim:
    """route.py 가 known_pos/known_neg 마다 approved.json 을 다시 읽는다. 재생(replay)에서는 파일명 기준으로 한 번만 읽도록 json.load 를 캐시한다."""
    def __init__(self):
        import json as _j
        self._j, self._c = _j, {}

    def load(self, f):
        k = os.path.basename(getattr(f, "name", str(f)))
        if k not in self._c:
            self._c[k] = self._j.load(f)
        return self._c[k]

    def __getattr__(self, n):
        return getattr(self._j, n)


def cache_registries():
    """route.json 을 캐시 shim 으로 교체(replay 용). 등록부 파일이 바뀌면 shim 을 새로 만든다."""
    import route, types
    route.json = _JsonShim()
    route.open = lambda p, *a, **k: types.SimpleNamespace(name=str(p))     # 카드마다 등록부 파일을 여는 비용 제거(윈도우에서 동시 실행 시 파일 열기가 직렬화되어 병렬 처리량을 막았다)
    return route.json


def timed(f, *a, **k):
    t = time.perf_counter()
    r = f(*a, **k)
    return r, time.perf_counter() - t
