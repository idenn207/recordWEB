"""경계 국소 재분석 (detect.py 와 별도 모듈): KEEP 구간의 시작/끝 주변만 YAMNet 을 0.1초 간격으로 다시 돌려
Music 점수가 가장 가파르게 오르는(시작)/떨어지는(끝) 시점으로 경계를 맞춘다. 기본 탐지의 0.5초 양자화와 연속구간 확장 오차를 줄이는 것이 목표.
사용: python refine.py <wav> <segments.json 입력> <출력> [win=8] [bias_start=0.3] [bias_end=1.6] [device=auto|cuda|cpu]  (device 의미는 detect.py 와 같음)"""
import csv, json, sys
from pathlib import Path
import numpy as np
from detect import MODELS, SR, WIN, Y

FINE = 0.1                                               # 초
_it = None


def music_curve(pcm, t0, t1, device=None):
    """[t0,t1) 초 구간 YAMNet Music 점수를 FINE 간격으로. 값 하나 = 그 시점에서 시작하는 0.975초 창."""
    ts = np.arange(max(0.0, t0), t1, FINE)
    if Y is not None:
        st = [int(t * SR) for t in ts]
        st = [i for i in st if i + WIN <= len(pcm)]              # 파일 끝에서 모자라는 창부터는 버린다 (기존과 같음)
        return ts[:len(st)], Y.scores_windows(pcm, st, device, cls=("Music",))[:, 0]
    return _legacy_curve(pcm, ts)


def _legacy_curve(pcm, ts):                                      # shortcut: 옛 마운트(yamnet_backend.py 없음) 호환, 마운트가 정리되면 지운다
    global _it, _mi
    from ai_edge_litert.interpreter import Interpreter
    if _it is None:
        names = [r[2] for r in csv.reader(open(MODELS / "yamnet_class_map.csv", encoding="utf8"))][1:]
        _mi = names.index("Music")
        _it = Interpreter(model_path=str(MODELS / "yamnet.tflite"))
        _it.allocate_tensors()
    inp, out = _it.get_input_details()[0], _it.get_output_details()[0]
    res = []
    for t in ts:
        x = pcm[int(t * SR):int(t * SR) + WIN].astype(np.float32) / 32768.0
        if len(x) < WIN:
            break
        _it.set_tensor(inp["index"], x.reshape(inp["shape"]))
        _it.invoke()
        res.append(_it.get_tensor(out["index"]).reshape(-1)[_mi])
    return ts[:len(res)], np.array(res)


def steepest(ts, m, rising, min_jump=0.3, span=1.0):
    """span 초 사이에 Music 이 min_jump 이상 오르는(rising) 또는 떨어지는 가장 가파른 지점의 시각(변화 구간의 중앙). 없으면 None."""
    k = max(1, int(span / FINE))
    if len(m) <= k:
        return None
    d = m[k:] - m[:-k]
    i = int(np.argmax(d) if rising else np.argmin(d))
    if (d[i] if rising else -d[i]) < min_jump:
        return None
    return float(ts[i] + span / 2)


def refine(pcm, s, e, win=8.0, bias_start=0.3, bias_end=1.6, device=None):   # 바이어스는 나나 10-06 으로 정하고 10-16 으로 시험함
    ts, m = music_curve(pcm, s - win, s + win, device)
    ns = steepest(ts, m, True)
    ts, m = music_curve(pcm, e - win, e + win, device)
    ne = steepest(ts, m, False)
    return (ns + bias_start if ns is not None else s), (ne + bias_end if ne is not None else e)


if __name__ == "__main__":
    wav, seg_in, seg_out = sys.argv[1:4]
    kw = {k: float(v) for k, v in (a.split("=") for a in sys.argv[4:] if not a.startswith("device="))}
    kw.update({a[:6]: a[7:] for a in sys.argv[4:] if a.startswith("device=")})
    with open(wav, "rb") as f:
        off = f.read(4096).find(b"data") + 8
    pcm = np.memmap(wav, dtype="<i2", mode="r", offset=off)
    segs = json.load(open(seg_in, encoding="utf8"))
    for g in segs:
        if g["keep"]:
            g["start0"], g["end0"] = g["start"], g["end"]
            g["start"], g["end"] = refine(pcm, g["start"], g["end"], **kw)
            g["len"] = g["end"] - g["start"]
    json.dump(segs, open(seg_out, "w", encoding="utf8"), ensure_ascii=False, indent=1)
