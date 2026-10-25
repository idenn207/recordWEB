"""녹화 파일 하나 -> 라이브 후보 클립 + 증거 카드 (detect -> refine -> finalize -> 장면 -> route(known_neg) -> 클립).
사용: python pipeline.py <wav> [--video <mp4|url>] [--id <영상번호>] [--name <스트리머>] [--force] [--out out]   |   python pipeline.py selftest
  호스트는 numpy+ffmpeg 만 필요. detect/refine 은 GPU 도커(song-detect-gpu)를 이 스크립트가 부른다(wav 는 아무 경로 가능, 읽기 전용 마운트).
  --video 생략 시 wav 이름이 숫자(치지직 영상번호)면 144p 주소(vod.url144)를, 아니면 wav 에서 오디오(.m4a)만 자른다. --name 생략 시 data/vods*.json 에서 영상번호로 찾는다(없으면 새 채널 취급: auto 없음).
출력 out/<id>/: 1_detect.json 2_refine.json 3_final.json 4_scene.json(장면 특징) cards/*.json(후보마다 증거 카드) clips/(auto 만), out/review/<id>/(review 클립). drop 은 카드만.
멱등: 단계 파일이 있으면 건너뜀. route/카드는 매번 다시 계산(known_negatives.json 수정이 바로 반영), 클립은 있으면 건너뜀. --force 는 out/<id> 의 단계 파일과 클립을 지우고 다시 만든다
  (detect 내부 캐시 cache/detect 의 YAMNet/Demucs 점수는 그대로 재사용: 지우려면 cache/detect/<이름>.* 를 직접 삭제).
승인 클립을 기준 풀에 넣기: data/review/<세트>/ 에 클립+라벨을 두고 `python scene_pool.py build` 후 --force 로 다시 실행(4_scene.json 이 풀에 의존).
shortcut: 장면 기준 풀 SETS(blind5, blind6)와 known_negatives 는 전역, 클립은 보정 없이 최종 start~end 그대로(앞뒤 패딩 없음)."""
import glob, json, os, shutil, subprocess, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOCKER = ["docker", "run", "--rm", "-e", "MSYS_NO_PATHCONV=1", "-v", f"{ROOT / 'cache'}:/work/cache", "-v", f"{ROOT / 'paths.py'}:/work/paths.py", "-v", f"{ROOT / 'detect.py'}:/work/detect.py"]


def hms(t):
    return f"{int(t // 3600)}h{int(t % 3600 // 60):02d}m{int(t % 60):02d}s"


def card(g, i, clip=None):
    """증거 카드: 최종 구간, 등급과 이유, 장면 판정, 경계 보정 전(detect)/refine 후/finalize 후, 신호 요약."""
    return dict(
        idx=i, start=g["start"], end=g["end"], len=g["len"], tier=g["tier"], tier_why=g["tier_why"],
        scene=g.get("scene"), multi=g.get("multi"), multi_why=g.get("multi_why"),
        boundary=dict(detect=[g.get("start0", g["start"]), g.get("end0", g["end"])], refine=[g.get("start1", g["start"]), g.get("end1", g["end"])], final=[g["start"], g["end"]],
                      why_snap=g.get("why_snap")),
        signals={k: g.get(k) for k in ("cover", "vocal", "speech", "music", "tstd", "blk")}, clip=clip)


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"실패: {' '.join(map(str, cmd))}\n{r.stdout[-800:]}\n{r.stderr[-800:]}")


def main(wav, video, vid, name, force, outroot):
    os.chdir(ROOT)                                              # route/scene_pool 의 상대 경로(data/, cache/) 기준
    import numpy as np
    wav = Path(wav).resolve()
    vid = vid or wav.stem
    O = Path(outroot).resolve() / vid
    if force:
        shutil.rmtree(O, ignore_errors=True)
        shutil.rmtree(O.parent / "review" / vid, ignore_errors=True)
        shutil.rmtree(O.parent / "optional" / vid, ignore_errors=True)
    O.mkdir(parents=True, exist_ok=True)
    f1, f2, f3, f4 = (O / n for n in ("1_detect.json", "2_refine.json", "3_final.json", "4_scene.json"))
    mount = ["-v", f"{wav.parent}:/work/in:ro", "-v", f"{O}:/work/o"]
    if not f1.exists():
        run(DOCKER + ["--gpus", "all"] + mount + ["song-detect-gpu", f"/work/in/{wav.name}", "vocal_thr=0.2", "--out=/work/o/1_detect.json"])
    if not f2.exists():
        run(DOCKER + ["--entrypoint", "python", "-v", f"{ROOT / 'refine.py'}:/work/refine.py"] + mount + ["song-detect-gpu", "refine.py", f"/work/in/{wav.name}", "/work/o/1_detect.json", "/work/o/2_refine.json"])
    if not f3.exists():
        from finalize import fix
        from paths import cache_of
        from snap import pcm_of
        pcm, a = pcm_of(wav), np.load(cache_of(wav, ".scores.npy"))
        f3.write_text(json.dumps([fix(pcm, a, g) for g in json.load(open(f2, encoding="utf8"))], ensure_ascii=False, indent=1), encoding="utf8")
    if name is None:
        name = next((v["name"] for p in glob.glob("data/vods*.json") for v in json.load(open(p, encoding="utf8")) if str(v["videoNo"]) == vid), None)
    if not video and vid.isdigit():
        from vod import url144
        video = url144(int(vid))
    if not f4.exists():                                          # 장면: 승인 풀(cache/scene_pool.npz) 기준, scene_new.py 와 같은 방식
        import scene_pool
        from scene import thumbs, dist
        from scene_multi import classify, feats
        meta, F = scene_pool.pool()
        LIVEP, NEGP = (scene_pool.cat(meta, F, lambda m: True)[g] for g in ("live", "neg"))
        R = scene_pool.cat(meta, F, lambda m: m["name"] == name)["live"] if name else None
        segs = [g for g in json.load(open(f3, encoding="utf8")) if g["keep"]]
        for s in segs:
            fr = thumbs(video, s["start"], s["end"]) if video else np.zeros((0, 1), np.float32)
            s["multi"], s["multi_why"] = classify(fr, LIVEP, NEGP)
            s["tstd"], s["blk"] = feats(fr) if len(fr) >= 3 else (None, None)
            s["scene"] = dist(fr, R) if R is not None else None
        f4.write_text(json.dumps(dict(has_refs=R is not None, segs=segs), ensure_ascii=False, indent=1), encoding="utf8")
    sc = json.load(open(f4, encoding="utf8"))
    from route import tier, known_neg
    segs = sc["segs"]
    import piano_gate
    piano_gate.annotate(vid, segs)                               # cache/exp12p/other.json 이 있을 때만 g['piano'] 표시(선택)
    (O / "cards").mkdir(exist_ok=True)
    for old in (O / "cards").glob("*.json"):
        old.unlink()
    for i, g in enumerate(segs, 1):
        g["tier"], g["tier_why"] = tier(g, sc["has_refs"])
        known_neg(vid, g)
        clip = None
        if g["tier"] in ("auto", "review", "optional"):
            d = O / "clips" if g["tier"] == "auto" else O.parent / g["tier"] / vid          # optional = 피아노 연주 의심(별도 옵션 대상)
            d.mkdir(parents=True, exist_ok=True)
            clip = d / f"{hms(g['start'])}{'.mp4' if video else '.m4a'}"
            if not clip.exists():
                enc = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-c:a", "aac"] if video else ["-vn", "-c:a", "aac"]
                run(["ffmpeg", "-v", "error", "-y", "-ss", f"{g['start']:.2f}", "-to", f"{g['end']:.2f}", "-i", video or str(wav)] + enc + [str(clip)])
        (O / "cards" / f"{i:02d}_{g['tier']}_{hms(g['start'])}.json").write_text(json.dumps(card(g, i, str(clip) if clip else None), ensure_ascii=False, indent=1), encoding="utf8")
    print(vid, name, "기준 있음" if sc["has_refs"] else "새 채널", dict(Counter(g["tier"] for g in segs)), "->", O)
    return segs


def selftest():
    g = dict(start=10.0, end=100.0, len=90.0, tier="auto", tier_why="", start0=11.0, end0=99.0, start1=10.5, end1=98.0, cover=0.9)
    c = card(g, 1)
    assert c["boundary"]["detect"] == [11.0, 99.0] and c["boundary"]["refine"] == [10.5, 98.0] and c["boundary"]["final"] == [10.0, 100.0]
    assert card(dict(start=1.0, end=2.0, len=1.0, tier="drop", tier_why="x"), 2)["boundary"]["refine"] == [1.0, 2.0]   # 보정 안 된 구간도 카드가 만들어짐
    assert hms(3725.4) == "1h02m05s"
    print("selftest ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["selftest"]:
        selftest()
        sys.exit()
    opt = lambda k: a[a.index(k) + 1] if k in a else None
    main(a[0], opt("--video"), opt("--id"), opt("--name"), "--force" in a, opt("--out") or "out")
