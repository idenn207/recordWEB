"""활동 신호 6종의 경계 연장(사슬) 비교: 같은 사슬 규칙(간격 gap 이내로 이어지면 연장, 최대 W초)을 신호만 바꿔 적용해
  끝 early 양성 / 끝 ok 음성 / 시작 late 양성 / 시작 ok 음성에서 flag 수와, 정답이 있는 곡의 제안 오차를 본다.
신호: sing(YAMNet Singing>=0.3) / musv(Music>=0.85 & Speech<0.2, E1 과 같은 조건) / vad_mix(silero, 방송 혼합) / vad_stem(silero, Demucs 보컬 스템) / rms_stem(스템 0.25초 rms >= -40dB) / whisper(가사 단어)
  python experiments/asr_vad_eval.py [--tx t_small_auto] [--W 40 --gap 8 --min 3.0]
캐시: cache/proto_asr/act/<gid>.json (신호별 구간 목록, 방송 절대초)"""
import sys, os, json, argparse
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT); sys.path.insert(0, str(ROOT / "experiments")); sys.path.insert(0, str(ROOT))
import numpy as np, soundfile as sf
import asr_bounds as B
from asr_run import groups, load_audio

ACT = ROOT / "cache/proto_asr/act"


def merge(iv, gap=0.0):
    out = []
    for a, b in sorted(iv):
        if out and a - out[-1][1] <= gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def frames_to_iv(mask, t0, hop):
    m = np.r_[0, mask.astype(np.int8), 0]
    d = np.diff(m)
    return [[t0 + a * hop, t0 + b * hop] for a, b in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1))]


def activities(g, vad_model):
    f = ACT / f"{g['gid']}.json"
    if f.exists():
        return json.load(open(f))
    import torch
    from silero_vad import get_speech_timestamps
    t0 = max(0.0, g["base"][0] - 60.0)
    mix = load_audio(g, t0, g["base"][1] + 60.0, "wav", None)
    stem, _ = sf.read(ROOT / "cache/proto_asr/stem" / f"{g['gid']}.wav", dtype="float32")
    a = B.scores(g["vno"])
    i0, i1 = int(t0 / 0.5), int((t0 + len(mix) / 16000) / 0.5)
    S = a[i0:i1]
    out = dict(t0=t0)
    out["sing"] = frames_to_iv(S[:, 0] >= 0.3, t0, 0.5)
    out["musv"] = frames_to_iv((S[:, 2] >= 0.85) & (S[:, 1] < 0.2), t0, 0.5)
    for nm, x in (("vad_mix", mix), ("vad_stem", stem)):
        ts = get_speech_timestamps(torch.from_numpy(x), vad_model, sampling_rate=16000, return_seconds=True)
        out[nm] = [[t0 + s["start"], t0 + s["end"]] for s in ts]
    h = 4000
    n = len(stem) // h
    r = 20 * np.log10(np.sqrt((stem[:n * h].reshape(n, h) ** 2).mean(1)) + 1e-6)
    out["rms_stem"] = frames_to_iv(r >= -40, t0, 0.25)
    ACT.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(f, "w"))
    return out


def chain(iv, edge, side, W, gap, min_len):
    """edge(현재 경계) 에서 side(end/start) 방향으로 gap 이내로 이어진 활동의 끝점. edge 에서 W 안에 닿아야 한다. 반환 (끝점, 연장량) 또는 None. 연장량 < min_len 이면 None."""
    iv = merge([tuple(x) for x in iv], 0.0)
    if side == "end":
        cur = edge
        for a, b in iv:
            if b <= edge - 3: continue
            if a - cur > gap: break
            if a - edge > W: break
            cur = max(cur, b)
        r = (cur, cur - edge)
    else:
        cur = edge
        for a, b in reversed(iv):
            if a >= edge + 3: continue
            if cur - b > gap: break
            if edge - b > W: break
            cur = min(cur, a)
        r = (cur, edge - cur)
    return r if r[1] >= min_len else None


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--tx", default="t_small_auto"); ap.add_argument("--W", type=float, default=40); ap.add_argument("--gap", type=float, default=8); ap.add_argument("--min", type=float, default=3.0)
    ap.add_argument("--set", default="all")
    a = ap.parse_args()
    from silero_vad import load_silero_vad
    vm = load_silero_vad()
    G = [g for g in groups() if g["lab"] != "N"]
    rows = []
    for g in G:
        if not (ROOT / "cache/proto_asr/stem" / f"{g['gid']}.wav").exists():
            continue
        act = activities(g, vm)
        d = B.load_tx(a.tx, g["gid"])
        if d:
            ly = B.lyric(B.words(d, B.scores(g["vno"])))
            act["whisper"] = [[w[0], w[1]] for w in ly]
        rows.append((g, act))
    methods = ["sing", "musv", "vad_mix", "vad_stem", "rms_stem", "whisper"]
    for side, want in (("end", "early"), ("start", "late")):
        print(f"\n[{side}] 양성={want} 음성=ok  (W={a.W} gap={a.gap} min={a.min})")
        for m in methods:
            tp = fp = npos = nneg = 0; errs = []
            for g, act in rows:
                sd = g["sides"][side]
                if m not in act or sd["issue"] not in (want, "ok"):
                    continue
                e = g["base"][1 if side == "end" else 0]
                r = chain(act[m], e, side, a.W, a.gap, a.min)
                if sd["issue"] == want:
                    npos += 1; tp += r is not None
                else:
                    nneg += 1; fp += r is not None
                if sd["truth"] is not None and sd["issue"] == want:
                    errs.append(((r[0] if r else e) - sd["truth"]))
            print(f"  {m:9} 양성 flag {tp}/{npos}  음성 flag {fp}/{nneg}  정답 있는 {len(errs)}곡 오차(제안-정답): {[round(x, 1) for x in errs]}")
