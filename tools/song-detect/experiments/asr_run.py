"""곡 구간 전후를 faster-whisper 로 전사해 단어 타임스탬프(방송 wav 절대초)를 캐시한다. 판정에 쓰지 않는 측정용(트랙 asr).
  python experiments/asr_run.py <태그> --model small|medium|large-v3 [--set pilot|all|g1,g2] [--lang auto|ko|ja|en] [--cond 0|1] [--nsp 0.6] [--vad 0|1] [--beam 5] [--ctype float16] [--margin 60] [--multi 0|1] [--src wav|vocal]
결과: cache/proto_asr/tx/<태그>/<gid>.json {gid, t0, t1, sec, words[[start,end,word,prob]], segs[{s,e,text,alp,nsp,cr,lang}]}, 이미 있으면 건너뜀. 곡당 처리초/VRAM 은 meta.json.
shortcut: 창 = base 경계(v3 시점) +-margin 이라 현재 snap 경계와 다를 수 있다. 보컬 스템(--src vocal)은 cache/proto_asr/stem/<gid>.wav 가 있을 때만."""
import sys, os, json, time, argparse, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
import numpy as np, soundfile as sf

EXP = ROOT / "data/review/blind9/expectations.json"
TX = ROOT / "cache/proto_asr/tx"


def groups():
    return json.load(open(EXP, encoding="utf8"))["groups"]


def pick(spec, G):
    if spec == "all":
        return G
    if spec == "pilot":     # 숫자 정답 / early / late 지적 / 대조(ok)
        return [g for g in G if g["lab"] != "N" and (any(g["sides"][s]["truth"] is not None or g["sides"][s]["issue"] not in (None, "ok") for s in ("start", "end")))]
    if spec.startswith("win:"):      # win:<json> = [{gid, vno, base:[s,e]}] 임의 구간 목록(asr_windows.py)
        return [dict(g, sides={}) for g in json.load(open(spec[4:], encoding="utf8"))]
    want = {int(x) for x in spec.split(",")}
    return [g for g in G if g["gid"] in want]


def vram_mb():
    try:
        o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True, text=True).stdout
        return int(o.split()[0])
    except Exception:
        return -1


def load_audio(g, t0, t1, src, stem_dir):
    if src == "vocal":
        p = stem_dir / f"{g['gid']}.wav"
        x, sr = sf.read(p, dtype="float32")
        return x
    p = ROOT / "data/vod" / ("nas" if g["vno"].startswith("20") else "") / f"{g['vno']}.wav"
    with sf.SoundFile(p) as f:
        sr = f.samplerate
        f.seek(int(t0 * sr))
        return f.read(int((t1 - t0) * sr), dtype="float32")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tag"); ap.add_argument("--model", default="small"); ap.add_argument("--set", default="pilot")
    ap.add_argument("--lang", default="auto"); ap.add_argument("--cond", type=int, default=0); ap.add_argument("--nsp", type=float, default=0.6)
    ap.add_argument("--vad", type=int, default=0); ap.add_argument("--beam", type=int, default=5); ap.add_argument("--ctype", default="float16")
    ap.add_argument("--margin", type=float, default=60.0); ap.add_argument("--src", default="wav"); ap.add_argument("--hall", type=float, default=2.4, help="compression_ratio_threshold")
    ap.add_argument("--multi", type=int, default=0, help="구간별 언어 감지(multilingual)"); ap.add_argument("--prompt", default=""); ap.add_argument("--temp", default="0")
    a = ap.parse_args()
    from faster_whisper import WhisperModel
    out = TX / a.tag; out.mkdir(parents=True, exist_ok=True)
    G = pick(a.set, groups())
    todo = [g for g in G if not (out / f"{g['gid']}.json").exists()]
    v0 = vram_mb()
    m = WhisperModel(a.model, device="cuda", compute_type=a.ctype)
    v1 = vram_mb()
    meta = json.load(open(out / "meta.json")) if (out / "meta.json").exists() else {}
    meta.update(args=vars(a), vram_model_mb=v1 - v0)
    tot_audio = tot_sec = 0.0
    for g in todo:
        t0 = max(0.0, g["base"][0] - a.margin); t1 = g["base"][1] + a.margin
        x = load_audio(g, t0, t1, a.src, ROOT / "cache/proto_asr/stem")
        t1 = t0 + len(x) / 16000
        t = time.time()
        segs, info = m.transcribe(x, language=None if a.lang == "auto" else a.lang, beam_size=a.beam, word_timestamps=True, condition_on_previous_text=bool(a.cond),
                                  no_speech_threshold=a.nsp, vad_filter=bool(a.vad), compression_ratio_threshold=a.hall, initial_prompt=a.prompt or None,
                                  temperature=[float(v) for v in a.temp.split(",")], multilingual=bool(a.multi))
        S, W = [], []
        for s in segs:
            S.append(dict(s=round(t0 + s.start, 2), e=round(t0 + s.end, 2), text=s.text, alp=round(s.avg_logprob, 3), nsp=round(s.no_speech_prob, 3), cr=round(s.compression_ratio, 2)))
            W += [[round(t0 + w.start, 2), round(t0 + w.end, 2), w.word, round(w.probability, 3)] for w in (s.words or [])]
        sec = time.time() - t
        tot_audio += t1 - t0; tot_sec += sec
        json.dump(dict(gid=g["gid"], t0=t0, t1=t1, sec=round(sec, 2), lang=info.language, lang_p=round(info.language_probability, 3), words=W, segs=S), open(out / f"{g['gid']}.json", "w", encoding="utf8"), ensure_ascii=False)
        print(g["gid"], f"{len(W)}단어 {sec:.1f}s/{t1 - t0:.0f}s", info.language, flush=True)
    meta["vram_after_mb"] = vram_mb() - v0
    if tot_audio:
        meta.update(rtf=round(tot_sec / tot_audio, 4), n_done=len(todo), audio_sec=round(tot_audio), proc_sec=round(tot_sec))
    json.dump(meta, open(out / "meta.json", "w"), indent=1)
    print("meta", {k: meta.get(k) for k in ("vram_model_mb", "vram_after_mb", "rtf", "n_done")})


if __name__ == "__main__":
    main()
