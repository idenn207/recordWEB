"""경계가 바뀐 후보 하나의 장면 필드를 NAS 영상에서 실제로 다시 계산한다(pipeline.py 의 4_scene 단계와 같은 호출, 후보 단위).
manifest.Run(scene_fn=real_scene_fn) 으로 쓴다. 401 이면 빈 프레임 -> 호출자가 알 수 있게 예외를 낸다(scene.thumbs 는 실패를 빈 배열로 삼켜 조용히 틀린 값이 저장되는 위험이 있다).
shortcut: 풀/기준 프레임은 슬러그마다 한 번 만들고 메모리에 둔다(61방송 전체면 수 GB 아님: 키프레임 6032장 48x27)."""
import re, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.lib import *
import numpy as np

_C = {}


class NasDown(RuntimeError):
    pass


def real_scene_fn(slug, g, stats=None):
    import scene_pool
    from scene import thumbs, dist
    from scene_multi import classify, feats
    sys.path.insert(0, str(ROOT / "datasets"))
    import nas_ingest as N
    R = next(r for r in rows() if r["slug"] == slug)
    if slug not in _C:
        meta, F = scene_pool.pool()
        day = re.match(r"\d{4}-\d{2}-\d{2}(?=_)", slug)
        name = R["streamer"]
        keep = scene_pool.excluder("date", dict(name=name, date=day[0]), meta) if day and name else (lambda m: True)
        LIVEP, NEGP = (scene_pool.cat(meta, F, keep)[x] for x in ("live", "neg"))
        Rf = scene_pool.cat(meta, F, lambda m: keep(m) and m["name"] == name)["live"] if name and scene_pool.eligible(meta, name, keep) else None
        _C[slug] = (LIVEP, NEGP, Rf)
    LIVEP, NEGP, Rf = _C[slug]
    t = time.perf_counter()
    fr = thumbs(N.url_of(R["path"]), g["start"], g["end"])
    dt = time.perf_counter() - t
    if stats is not None:
        stats.append(dt)
    if len(fr) < 3:
        raise NasDown(f"{slug} {g['start']:.0f}: 프레임 {len(fr)}장 (401 이거나 읽기 실패) - 중단")
    multi, why = classify(fr, LIVEP, NEGP)
    tstd, blk = feats(fr)
    return dict(multi=multi, multi_why=why, tstd=tstd, blk=blk, scene=dist(fr, Rf) if Rf is not None else None)
