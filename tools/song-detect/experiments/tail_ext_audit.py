"""tail_cut 연장(큰 소리가 컷까지 이어지는 곡)이 현재 완곡 클립(out/final, out/final_review)과 승인 golden 에서 어디를 얼마나 바꾸는지 목록. 읽기 전용.
사용: python experiments/tail_ext_audit.py     -> 컷이 0.2초 넘게 늘어난 곡: 클립 id, 현재 컷 -> 새 컷, 곡 끝, 컷 뒤 말(Speech>0.3) 포함 여부"""
import json, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import make_final
from paths import cache_of
from snap import pcm_of, rms_db

nas = {r["slug"]: r for r in json.load(open(ROOT / "data/nas_index.json", encoding="utf8"))}
n = ch = 0
for t in ("final", "final_review"):
    for js in sorted((ROOT / "out" / t).glob("*/*.json")):
        if js.name.endswith("_ctx20.json"):
            continue
        j = json.load(open(js, encoding="utf8")); sl = "_".join(js.parent.name.split("_")[2:])
        wav = str(ROOT / nas[sl]["wav"]); pcm, a = pcm_of(wav), np.load(cache_of(wav, ".scores.npy"))
        e = j["song_end"]; ref = float(np.median(rms_db(pcm, j["song_start"], e)[1])); ce0 = e + j["trail"]["pad"]
        new = make_final.tail_cut(pcm, a, ref, e, ce0); n += 1
        if new - j["vod_end"] > 0.2:
            ch += 1
            sp = float((a[int(j["vod_end"] * 2):int(new * 2) + 1, 1] > 0.3).mean())
            print(f"{t[:6]:6s} {js.parent.name[:6]}_{js.parent.name.split('_')[-2]}{js.parent.name.split('_')[-1]} #{j['card_idx']:02d} 곡끝 {e:.1f} 컷 {j['vod_end']:.1f} -> {new:.1f} (+{new - j['vod_end']:.1f}, 곡끝 뒤 {new - e:.1f}) 연장구간 Speech>0.3 비율 {sp:.2f}")
print(f"검사 {n}곡, 컷이 늘어난 곡 {ch}")
