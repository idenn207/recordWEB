"""NAS 방송 전체의 pipeline 을 다시 돌려 route/카드를 갱신(GPU 탐지 캐시 재사용). 장면(4_scene.json)은 풀에서 빠지는 방송(승인 풀에 같은 스트리머+날짜가 있는 방송)만 지워 다시 계산한다(--all 이면 전부).
사용: python datasets/reroute_nas.py [동시수=2] [--all] [--final] [--manifest]   (--final: 3_final.json 도 지워 경계 규칙(snap/finalize)을 다시 적용, 이때 4_scene 도 같이 지운다)
  --manifest: 지우고 전부 다시 계산하는 대신 단계 매니페스트(harness/manifest.py)로 입력이 바뀐 단계만 다시 한다(경계 규칙을 고친 뒤 장면은 경계가 바뀐 후보만 NAS 에서 다시 읽음, 61방송 약 593초 -> 수십 초).
    출력(3_final.json, 4_scene.json, cards/*.json = SONG_NOCLIP=1 일 때와 같음)은 위 방식과 같다. 클립은 만들지 않는다. --all/--final/동시수는 무시한다.
  NAS 에서 프레임을 못 읽으면(세션 만료 401 등) scene.NasDown 으로 그 방송을 원래 상태로 되돌리고 남은 방송도 건너뛴다. 로그인은 시도하지 않는다(nas_auth 세션만 사용)."""
import json, sys, shutil, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import nas_ingest as N

import scene_pool
POOL = {(m["name"], m["date"]) for m in scene_pool.pool()[0]}
rows = [r for r in json.load(open(N.IDX, encoding="utf8")) if (N.ROOT / "out" / r["slug"] / "3_final.json").exists()]


STOP = []      # NAS 세션 문제면 남은 방송도 같은 이유로 실패하므로 건너뛴다


def one(r):
    if STOP:
        return
    d = N.ROOT / "out" / r["slug"]
    bak = {}
    for f, hit in (("3_final.json", "--final" in sys.argv), ("4_scene.json", "--all" in sys.argv or "--final" in sys.argv or (r["streamer"], r["date"]) in POOL)):
        if hit and (d / f).exists():
            bak[d / f] = (d / f).read_bytes()
            (d / f).unlink()
    t = time.time()
    try:
        N.pipe(r)
        print(time.strftime("%H:%M:%S"), "ok", r["slug"], round(time.time() - t), flush=True)
    except Exception as e:
        for f, b in bak.items():                                # 실패하면 지우기 전 상태로(3_final 과 4_scene 이 서로 다른 경계 기준이 되지 않게 둘 다 되돌린다)
            f.write_bytes(b)
        if "NasDown" in str(e):
            STOP.append(r["slug"])
        print(time.strftime("%H:%M:%S"), "FAIL", r["slug"], str(e)[-200:], flush=True)


def by_manifest():
    import harness.manifest as M
    from harness.scene_real import real_scene_fn, real_has_refs
    path = {r["slug"]: r["path"] for r in rows}

    def vis_fn(slug, segs):                                    # 화면 신호: torch+open_clip 이 있는 호스트 venv 로 실행할 때만(아니면 건너뜀)
        try:
            import n_visual
            n_visual.fill(segs, N.url_of(path[slug]))
        except ImportError as e:
            print(f"n_visual 건너뜀({e.name} 없음): 호스트 venv python 으로 실행하면 화면 신호가 붙는다", file=sys.stderr)
    run = M.Run(root=N.ROOT / "out", scene_fn=real_scene_fn, vis_fn=vis_fn, refs_fn=real_has_refs)
    slugs = [r["slug"] for r in rows]
    try:
        P = run.run(slugs)
    except Exception as e:                                      # Run.run 은 방송마다 단계 파일을 쓰고 마지막에 manifest.json 을 쓴다. 실패한 방송의 단계는 manifest 에 기록되지 않아 다음에 다시 계산된다
        sys.exit(f"중단: {type(e).__name__}: {str(e)[-300:]}")
    print("단계 실행", {k: round(v, 1) for k, v in run.t.items()}, "후보 수", run.n, "stale 방송", sum(bool(v) for v in P.values()), flush=True)


if "--manifest" in sys.argv:
    by_manifest()
else:
    with ThreadPoolExecutor(int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 2) as ex:
        list(ex.map(one, rows))
print("끝", len(rows), flush=True)
