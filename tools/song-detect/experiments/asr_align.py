"""Whisper 세그먼트 텍스트를 torchaudio MMS_FA(CTC 강제 정렬, uroman 로마자 변환)로 다시 정렬하고 Whisper 단어 타임스탬프와 비교한다.
  python experiments/asr_align.py <전사태그> [--src wav|vocal] [--set pilot] [--max 12]
출력: 단어 시작/끝 차이(MMS - Whisper)의 중앙/90분위 절대값, 정렬 점수, 세그먼트 첫 단어/마지막 단어 차이. 결과 json: cache/proto_asr/align_<태그>_<src>.json
shortcut: 한자/가나 혼용은 uroman 이 읽는 대로 변환(정확도 미검증), 정렬은 Whisper 텍스트가 맞다고 가정하므로 환각 텍스트는 못 거른다."""
import sys, os, re, json, argparse
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT); sys.path.insert(0, str(ROOT / "experiments"))
import numpy as np, soundfile as sf, torch, torchaudio
import asr_bounds as B
from asr_run import groups, pick, load_audio

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("tag"); ap.add_argument("--src", default="wav"); ap.add_argument("--set", default="pilot"); ap.add_argument("--max", type=int, default=12)
    a = ap.parse_args()
    import uroman
    ur = uroman.Uroman()
    bundle = torchaudio.pipelines.MMS_FA
    model = bundle.get_model(with_star=False).cuda().eval()
    tok, aligner = bundle.get_tokenizer(), bundle.get_aligner()
    dd, ds, sc, first, last, rows = [], [], [], [], [], []
    for g in pick(a.set, groups())[:a.max]:
        d = B.load_tx(a.tag, g["gid"])
        if not d: continue
        ws = B.words(d, B.scores(g["vno"]))
        ly = B.lyric(ws)
        if a.src == "vocal":
            x, _ = sf.read(ROOT / "cache/proto_asr/stem" / f"{g['gid']}.wav", dtype="float32"); x0 = d["t0"]
        else:
            x0 = d["t0"]; x = load_audio(g, x0, d["t1"], "wav", None)
        # 세그먼트별: 가사로 분류된 단어가 3개 이상인 세그먼트만
        for sg in d["segs"]:
            sw = [w for w in ly if sg["s"] - .01 <= w[0] <= sg["e"] + .01]
            if len(sw) < 3 or sg["e"] - sg["s"] > 30: continue
            rom = [re.sub(r"[^a-z']", "", ur.romanize_string(w[2].strip()).lower()) for w in sw]
            keep = [i for i, r in enumerate(rom) if r]
            if len(keep) < 3: continue
            t0, t1 = max(sg["s"] - .5, x0), min(sg["e"] + .5, x0 + len(x) / 16000)
            wav = torch.from_numpy(x[int((t0 - x0) * 16000):int((t1 - x0) * 16000)])[None].cuda()
            with torch.no_grad():
                em, _ = model(wav)
                try:
                    spans = aligner(em[0], tok([rom[i] for i in keep]))
                except Exception as e:
                    continue
            ratio = wav.size(1) / em.size(1) / 16000
            for i, sp in zip(keep, spans):
                s_, e_ = t0 + sp[0].start * ratio, t0 + sp[-1].end * ratio
                dd.append(s_ - sw[i][0]); ds.append(e_ - sw[i][1]); sc.append(float(np.mean([t.score for t in sp])))
            first.append(t0 + spans[0][0].start * ratio - sw[keep[0]][0]); last.append(t0 + spans[-1][-1].end * ratio - sw[keep[-1]][1])
        print(g["gid"], len(dd), flush=True)
    dd, ds, sc, first, last = map(np.array, (dd, ds, sc, first, last))
    q = lambda x: [round(float(v), 2) for v in (np.median(np.abs(x)), np.percentile(np.abs(x), 90), np.median(x))]
    res = dict(n_words=len(dd), start_abs_med_p90_bias=q(dd), end_abs_med_p90_bias=q(ds), seg_first_abs_med_p90_bias=q(first), seg_last_abs_med_p90_bias=q(last), mean_score=float(sc.mean()), frac_start_within_0_3s=float((np.abs(dd) <= .3).mean()), frac_end_within_0_3s=float((np.abs(ds) <= .3).mean()))
    print(res)
    json.dump(res, open(ROOT / f"cache/proto_asr/align_{a.tag}_{a.src}.json", "w"), indent=1)
