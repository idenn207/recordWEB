"""visual 트랙 1단계: 프레임을 뽑을 곡 목록(manifest) 만들기 -> cache/proto_visual/manifest.json.
행 = {key, set, name, group(스트리머|방송일), streamer, live, tag, lab, src(파일 또는 URL), t0, t1}. t0/t1 = src 안의 곡 구간(초).
출처: blind9(완성본 클립, out/stale_v3 등), blind5/6(검토 클립 mp4), refs(사람이 검수한 위치 정답 + 승인, 나나 NAS ts / 마시로 후야 로컬 mp4). blind78 은 미디어 없음 -> 제외(5행).
사용: python experiments/visual/mk_manifest.py"""
import json, os, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments"))
os.chdir(ROOT)
import loso_n, scene_pool
from labels import BLIND9

OUT = Path("cache/proto_visual/manifest.json")


def find9(file):
    for d in ("out/stale_v3/final_review", "out/stale_v3/final", "out/stale_v4/final_review", "out/stale_v4/final", "out/final_review", "out/final"):
        for p in Path(d).rglob(file):
            return str(p)


def main():
    meta, F = scene_pool.pool()
    rows, miss = [], []
    K9 = json.load(open("data/review/blind9/key.json", encoding="utf8"))
    for r in loso_n.records(meta, F):
        g, s, name = r["g"], r["set"], r["name"]
        date = (r["pm"] or {}).get("date")
        row = dict(key=r["key"], set=s, name=name, live=int(bool(r["live"])), tag=r["tag"] or "", bok=r["bok"], vno=str(r["vno"]))
        if s == "blind9":
            kk = K9[r["id"]]
            date = re.search(r"\d{4}-\d{2}-\d{2}", kk["videoNo"])[0]
            row.update(src=find9(kk["file"]), t0=0.0, t1=kk["len"], lab=BLIND9[r["id"]].get("lab", ""))
        elif s in ("blind5", "blind6"):
            K = json.load(open(f"data/review/{s}/key.json", encoding="utf8"))[r["id"]]
            date = K["date"]
            f = next(iter(Path(f"data/review/{s}").glob(f"*__{r['id']}.mp4")), None)
            a = K["start"] - K["clip_start"]
            row.update(src=str(f) if f else None, t0=a, t1=a + K["len"])
        else:
            continue
        row["group"] = f"{name}|{date}"
        (rows if row.get("src") else miss).append(row)
    # refs: 사람이 검수한 위치 정답 (라이브)
    from scene import url_of
    G = [("하나코 나나", "data/refs.json", "2026-10-06", "나나"), ("하나코 나나", "data/refs.json", "2026-10-16", "나나"),
         ("네네코 마시로", "data/refs_마시로.json", "2026-10-23", "마시로"), ("사키하네 후야", "data/refs_후야.json", "2026-10-19", "후야")]
    for name, rf, date, who in G:
        u = url_of(date, who)
        for r in json.load(open(rf, encoding="utf8")):
            if r["date"] == date:
                rows.append(dict(key=f"refs/{date}_{who}_{int(r['start'])}", set="refs", name=name, group=f"{name}|{date}", live=1, tag="", bok=True, vno=date, src=u, t0=r["start"], t1=r["end"], lab="L"))
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf8")
    from collections import Counter
    print(len(rows), "행", Counter((r["set"], r["live"]) for r in rows), "미디어 없음", [m["key"] for m in miss])
    assert all(r["t1"] > r["t0"] + 20 for r in rows)


if __name__ == "__main__":
    main()
