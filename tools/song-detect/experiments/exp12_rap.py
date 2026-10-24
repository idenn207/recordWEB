"""90초 미만 랩 하한 완화 실험: 캐시된 scores/vocal 로 구간화만 다시 돌린다 (Demucs 안 돈다).
사용(도커): python experiments/exp12_rap.py <cand_min_s> <min_len_s,...> <출력폴더>  -> <출력>/<min_len>/<이름>.segments.json
후보 캐시가 없으면 건너뛴다(shortcut: cand_min_s 를 60 밖으로 바꾸면 새 후보가 생기므로 전체 실행 --gpu 가 필요)."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent)); sys.path.insert(0, str(Path(__file__).resolve().parent))
import detect as D
from paths import CACHE, DATA

def main():
    cand_min, mins, out = float(sys.argv[1]), [float(x) for x in sys.argv[2].split(",")], Path(sys.argv[3])
    gpu_ok = "--gpu" in sys.argv
    stems = sorted(f.name[:-11] for f in (CACHE / "detect").glob("*.scores.npy"))
    for m in mins:
        (out / f"{m:g}").mkdir(parents=True, exist_ok=True)
        for st in stems:
            wav = next(iter([*DATA.glob(f"vod/{st}.wav"), *DATA.glob(f"vod/legacy/{st}.wav")]), DATA / "vod" / f"{st}.wav")
            p = {**D.P, "vocal_thr": 0.2, "cand_min_s": cand_min, "min_len_s": m}
            a = D.scores(wav)
            vf = D.cache_of(wav, ".vocal.json")
            cache = json.loads(vf.read_text()) if vf.exists() else {}
            miss = [c for c in D.candidates(a, p) if f"{max(0.0, c[0] - p['pad_s'])}-{c[1] + p['pad_s']}" not in cache]
            if miss and not gpu_ok:
                print(f"skip {st} min={m:g}: 캐시 없는 후보 {len(miss)}개", flush=True)
                continue
            json.dump(D.detect(wav, p=p), open(out / f"{m:g}" / f"{st}.segments.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":  # spawn 풀이 이 파일을 다시 import 한다
    main()
