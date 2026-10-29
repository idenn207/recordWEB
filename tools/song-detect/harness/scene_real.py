"""경계가 바뀐 후보 하나의 장면 필드를 NAS 영상에서 실제로 다시 계산한다(pipeline.py 의 4_scene 단계와 같은 호출, 후보 단위).
manifest.Run(scene_fn=real_scene_fn) 으로 쓴다. 401 이면 scene.NasDown 을 낸다(scene.thumbs 는 실패를 빈 배열로 삼켜 조용히 틀린 값이 저장되는 위험이 있어 scene.nas_thumbs 를 쓴다).
shortcut: 풀/기준 프레임은 슬러그마다 한 번 만들고 메모리에 둔다(61방송 전체면 수 GB 아님: 키프레임 6032장 48x27)."""
import re, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.lib import *
import numpy as np

_C = {}


def _pool(slug):
    """(라이브 풀, N 풀, 같은 채널 기준 프레임 또는 None). 방송 날짜/채널이 같은 곡은 뺀다. 슬러그마다 한 번만 만든다."""
    import scene_pool
    R = next(r for r in rows() if r["slug"] == slug)
    if slug not in _C:
        meta, F = scene_pool.pool()
        day = re.match(r"\d{4}-\d{2}-\d{2}(?=_)", slug)
        name = R["streamer"]
        keep = scene_pool.excluder("date", dict(name=name, date=day[0]), meta) if day and name else (lambda m: True)
        LIVEP, NEGP = (scene_pool.cat(meta, F, keep)[x] for x in ("live", "neg"))
        Rf = scene_pool.cat(meta, F, lambda m: keep(m) and m["name"] == name)["live"] if name and scene_pool.eligible(meta, name, keep) else None
        _C[slug] = (LIVEP, NEGP, Rf)
    return _C[slug]


def real_has_refs(slug):
    """현재 풀로 본 has_refs(채널 승인 이력이 충분한가). pipeline.main 의 R is not None 과 같은 기준: manifest 가 이전 4_scene 값을 그대로 두지 않게(풀이 늘어난 채널)"""
    return _pool(slug)[2] is not None


def real_scene_fn(slug, g, stats=None):
    from scene import nas_thumbs, dist
    from scene_multi import classify, feats
    sys.path.insert(0, str(ROOT / "datasets"))
    import nas_ingest as N
    R = next(r for r in rows() if r["slug"] == slug)
    LIVEP, NEGP, Rf = _pool(slug)
    t = time.perf_counter()
    fr = nas_thumbs(N.url_of(R["path"]), g["start"], g["end"])      # 401/읽기 실패면 scene.NasDown (조용히 None 이 저장되지 않게)
    dt = time.perf_counter() - t
    if stats is not None:
        stats.append(dt)
    multi, why = classify(fr, LIVEP, NEGP)
    tstd, blk = feats(fr)
    return dict(multi=multi, multi_why=why, tstd=tstd, blk=blk, scene=dist(fr, Rf) if Rf is not None else None)
