"""라이브 노래 구간 탐지 프로토타입. 16kHz mono wav -> 구간 목록(JSON).
오탐 최소화가 목표라 보수적으로 자른다 (놓친 구간은 수기로 찾을 수 있다).
1단계 YAMNet: Music 높고 Speech 낮은 구간이 길게 이어지는 곳을 후보로 (싸다). 'Singing' 점수는 반주가
  크면 0.03 정도로 죽어서 쓰지 않는다.
2단계 Demucs: 후보에서만 보컬 스템 에너지 비율을 본다. 순수 BGM/MR 사운드체크는 ~0, 노래는 0.7 안팎.
사용: python detect.py <wav> [--force] [device=auto|cuda|cpu]   (중간 결과는 cache/detect/<이름>.scores.npy / .vocal.json 로 캐시)
디바이스: device= 인자 또는 환경변수 SONG_DEVICE (기본 auto = torch.cuda 가능하면 cuda). cpu 는 TFLite 한 창씩(NAS 와 같은 결과), cuda 는 YAMNet 배치 GPU 추론 + Demucs GPU. yamnet_backend.py 참고."""
import csv, json, os, sys, time
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from pathlib import Path
import numpy as np
from paths import cache_of
try:
    import yamnet_backend as Y
except ImportError:      # shortcut: 옛 docker -v 목록(detect.py 만 마운트)과의 호환 - 아래 기존 TFLite 루프로 돈다. 모든 마운트와 이미지에 yamnet_backend.py 가 들어가면 지운다
    Y = None

HOP = 0.5          # 초, 점수 간격
WIN = 15600        # YAMNet 입력 (0.975s @16k)
SR = 16000
P = dict(smooth_s=6, music_min=0.5, speech_max=0.3, gap_s=20, cand_min_s=60,
         vocal_win_s=5, vocal_thr=0.3, win_speech_max=0.25, win_music_min=0.5,
         min_len_s=90, max_len_s=360, talk_break_s=15, min_cover=0.6, seg_speech_max=0.12, seg_music_min=0.6, pad_s=10,
         ext_back_s=45, ext_fwd_s=30, ext_tail_s=1.5, workers=3, yamnet_workers=0)   # yamnet_workers: CPU 에서 YAMNet 청크 병렬 프로세스 수 (0 = min(4, 코어 수), 1 = 단일). GPU 에서는 무시

DEMUCS_BATCH = 4     # GPU 에서 한 번에 묶는 60초 청크 수
here = Path(__file__).parent
MODELS = here / "models" if (here / "models").exists() else here


def _pcm(wav):
    # ffmpeg wav 는 LIST 청크가 끼어 헤더 길이가 다르다: 'data' 청크 뒤부터 int16 PCM
    with open(wav, "rb") as f:
        off = f.read(4096).find(b"data") + 8
    return np.memmap(wav, dtype="<i2", mode="r", offset=off)


def _legacy_scores(pcm):
    from ai_edge_litert.interpreter import Interpreter
    names = [r[2] for r in csv.reader(open(MODELS / "yamnet_class_map.csv", encoding="utf8"))][1:]
    want = [names.index(n) for n in ("Singing", "Speech", "Music")]
    it = Interpreter(model_path=str(MODELS / "yamnet.tflite"))
    it.allocate_tensors()
    inp, out = it.get_input_details()[0], it.get_output_details()[0]
    step = int(HOP * SR)
    res = []
    for i in range(0, len(pcm) - WIN, step):
        x = (pcm[i:i + WIN].astype(np.float32) / 32768.0)
        it.set_tensor(inp["index"], x.reshape(inp["shape"]))
        it.invoke()
        res.append(it.get_tensor(out["index"]).reshape(-1)[want])
        if len(res) % 5000 == 0:
            print(f"  {len(res) * HOP / 3600:.1f}h", file=sys.stderr, flush=True)
    return np.array(res, dtype=np.float32)


def scores(wav: Path, force=False, device=None, workers=1):
    cache = cache_of(wav, ".scores.npy")
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and not force:
        return np.load(cache)
    pcm = _pcm(wav)
    if Y is None:
        a = _legacy_scores(pcm)
    else:
        a = Y.scores_windows(pcm, np.arange(0, len(pcm) - WIN, int(HOP * SR)), device, workers=workers, src=wav)
    np.save(cache, a)
    return a


def runs(mask, gap_s, step):
    """True 구간을 [시작, 끝) 초로 묶는다. gap_s 이하의 틈은 이어 붙인다."""
    out, gap = [], int(gap_s / step)
    i, n = 0, len(mask)
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j, last = i, i
        while j < n and j - last <= gap:
            if mask[j]:
                last = j
            j += 1
        out.append((i * step, (last + 1) * step))
        i = last + 1
    return out


def smooth(x, sec):
    k = max(1, int(sec / HOP))
    return np.convolve(x, np.ones(k) / k, mode="same")


def walk(m, t, step, cap, dip=3.0, thr=0.5):
    """t 에서 step(+1/-1) 방향으로 Music>=thr 가 이어지는 마지막 시점. thr 미만이 dip초 이상 이어지거나 cap초를 넘으면 멈춘다."""
    i = last = int(t / HOP)
    bad = n = 0
    while n * HOP < cap and 0 <= i + step < len(m):
        i, n = i + step, n + 1
        if m[i] >= thr:
            last, bad = i, 0
        else:
            bad += 1
            if bad * HOP >= dip:
                break
    return last * HOP


def extend(a, s, e, p=P):
    """사용자 클립은 MR 시작에서 시작해 MR 끝 ~1.5초 뒤에 끝난다 -> 보컬 구간을 연속 음악 구간으로 넓힌다."""
    m = smooth(a[:, 2], 2)
    return walk(m, s, -1, p["ext_back_s"]), walk(m, e, 1, p["ext_fwd_s"]) + p["ext_tail_s"]


def candidates(a, p=P):
    mask = (smooth(a[:, 2], p["smooth_s"]) >= p["music_min"]) & (smooth(a[:, 1], p["smooth_s"]) <= p["speech_max"])
    return [(s, e) for s, e in runs(mask, p["gap_s"], HOP) if e - s >= p["cand_min_s"]]


def vocal_ratio(wav: Path, start, end, p=P, device=None):
    """[start,end) 초를 5초 창으로 나눠 창별 (보컬 스템 에너지 / 믹스 에너지)."""
    import torch, torchaudio
    from demucs.apply import apply_model
    from demucs.pretrained import get_model
    global _model
    if "_model" not in globals():
        _model = get_model("htdemucs").eval()
    dev = Y.resolve(device) if Y else ("cuda" if torch.cuda.is_available() else "cpu")    # NAS 는 CPU. 개발 PC 는 GPU 로 돌린다
    if dev == "cuda" and Y:
        Y.gpu_init()
    _model.to(dev)
    vi = _model.sources.index("vocals")
    pcm = _pcm(wav)
    w, chunk, ratios = p["vocal_win_s"], 60, []
    end = min(end, len(pcm) / SR)                                # 후보 패딩이 파일 끝을 넘으면 빈 청크로 resample 이 죽는다
    ts = [(t, min(end, t + chunk)) for t in np.arange(start, end, chunk).tolist()]
    nb = DEMUCS_BATCH if dev == "cuda" else 1                               # GPU 는 60초 청크를 묶어 한 번에 (창별 순차 호출이면 GPU 사용률 22%)
    n = int(w * 44100)
    for g in range(0, len(ts), nb):
        # 같은 길이끼리만 묶는다 (마지막 청크만 짧을 수 있다)
        xs = []
        for t, te in ts[g:g + nb]:
            x = torch.from_numpy(pcm[int(t * SR):int(te * SR)].astype(np.float32) / 32768).to(dev)
            xs.append(torchaudio.functional.resample(x, SR, 44100)[None].repeat(2, 1))   # 리샘플도 dev 에서 (CPU 텐서면 sinc 보간이 느리다)
        i = 0
        while i < len(xs):
            j = i + 1
            while j < len(xs) and xs[j].shape == xs[i].shape:
                j += 1
            t0 = time.time()
            with torch.no_grad():
                vs = apply_model(_model, torch.stack(xs[i:j]), device=dev)[:, vi].cpu()
            if dev == "cuda" and Y:
                Y.gpu_rest(t0)
            for x, v in zip(xs[i:j], vs):
                x = x.cpu()
                for k in range(0, x.shape[1] - n + 1, n):
                    ratios.append(float(v[:, k:k + n].pow(2).mean() / (x[:, k:k + n].pow(2).mean() + 1e-9)))
            i = j
    return np.array(ratios, dtype=np.float32)


def win_mean(a, col, t0, w, n):
    """YAMNet 점수를 vocal_ratio 의 w초 창에 맞춰 평균낸다 (n개)."""
    k = int(w / HOP)
    i0 = int(t0 / HOP)
    return np.array([a[i0 + j * k:i0 + (j + 1) * k, col].mean() for j in range(n)])


def split_at_talk(rs, sung, talk, w, min_s):
    """노래 구간 안에 '말소리를 낀 min_s초 이상의 비노래 블록'이 있으면 거기서 나눈다 (연달아 붙은 두 곡이 하나로 합쳐지는 것을 막는다).
    말소리 없는 비노래 블록(간주)은 곡 안의 쉼으로 보고 나누지 않는다."""
    out = []
    for s, e in rs:
        a, b = int(s / w), int(e / w)
        start = i = a
        while i < b:
            if sung[i]:
                i += 1
                continue
            j = i
            while j < b and not sung[j]:
                j += 1
            if talk[i:j].any() and (j - i) * w >= min_s:
                out.append((start * w, i * w))
                start = j
            i = j
        out.append((start * w, b * w))
    return [(s, e) for s, e in out if e > s]


def _vocal_job(a):
    import torch
    wav, s0, e0, p, th, dev = a
    torch.set_num_threads(th)
    return vocal_ratio(wav, s0, e0, p, dev).tolist()


def detect(wav: Path, force=False, p=P, device=None, in_process=False):
    a = scores(wav, force, device, int(p["yamnet_workers"]) or min(4, os.cpu_count() or 1))
    cache_f = cache_of(wav, ".vocal.json")
    cache = json.loads(cache_f.read_text()) if cache_f.exists() and not force else {}
    out, w = [], p["vocal_win_s"]
    cands = [(cs, ce, max(0.0, cs - p["pad_s"]), ce + p["pad_s"]) for cs, ce in candidates(a, p)]
    todo = [c for c in cands if f"{c[2]}-{c[3]}" not in cache]
    import torch
    dev = Y.resolve(device) if Y else ("cuda" if torch.cuda.is_available() else "cpu")
    gpu = dev == "cuda"
    if todo:  # Demucs 가 병목: 후보는 서로 독립이라 CPU 에서는 프로세스 풀로 (shortcut: 이 PC 실측 ~1.6배, 메모리 대역폭에 막힘), GPU 는 한 프로세스
        th = max(1, (os.cpu_count() or 8) // int(p["workers"]))
        if in_process:     # 상주 서비스: 후보마다 프로세스를 띄워 모델을 다시 올리지 않고 이미 올라간 Demucs 로 (CPU 는 스레드 병렬, torch 가 GIL 을 놓는다)
            import torch
            from concurrent.futures import ThreadPoolExecutor
            torch.set_num_threads(max(1, int(os.environ.get("SONG_THREADS") or th)))
            ex, mapf = ThreadPoolExecutor(1 if gpu else int(p["workers"])), lambda c: vocal_ratio(wav, c[2], c[3], p, dev).tolist()
            it = ex.map(mapf, todo)
        else:
            ex = ProcessPoolExecutor(1 if gpu else int(p["workers"]), mp_context=multiprocessing.get_context("spawn"))
            it = ex.map(_vocal_job, [(wav, c[2], c[3], p, th, dev) for c in todo])
        with ex:
            for c, r in zip(todo, it):
                cache[f"{c[2]}-{c[3]}"] = r
                cache_f.write_text(json.dumps(cache))
                print(f"  cand {hms(c[0])}-{hms(c[1])} done", file=sys.stderr, flush=True)
    for cs, ce, s0, e0 in cands:
        r = np.array(cache[f"{s0}-{e0}"], dtype=np.float32)
        sp, mu = win_mean(a, 1, s0, w, len(r)), win_mean(a, 2, s0, w, len(r))
        # 노래 창 = 보컬 스템이 크고, 말소리가 아니고, 음악이 깔린 창 (대화/TTS 가 섞인 창은 보컬로 세지 않는다)
        sung = (r >= p["vocal_thr"]) & (sp <= p["win_speech_max"]) & (mu >= p["win_music_min"])
        for s, e in split_at_talk(runs(sung, p["gap_s"], w), sung, sp > p["win_speech_max"], w, p["talk_break_s"]):
            a_, b_ = int(s / w), int(e / w)
            cover = float(sung[a_:b_].mean())
            seg_sp, seg_mu = float(sp[a_:b_].mean()), float(mu[a_:b_].mean())
            ok_len = p["min_len_s"] <= (e - s) <= p["max_len_s"] and cover >= p["min_cover"]
            ok_gate = seg_sp <= p["seg_speech_max"] and seg_mu >= p["seg_music_min"]
            keep = ok_len and ok_gate
            s1, e1 = extend(a, s0 + s, s0 + e, p) if keep else (s0 + s, s0 + e)
            out.append(dict(start=s1, end=e1, len=e1 - s1, cover=round(cover, 2), vocal=round(float(r[a_:b_].mean()), 2),
                            speech=round(seg_sp, 2), music=round(seg_mu, 2), keep=keep,
                            why="" if keep else (("too-long" if (e - s) > p["max_len_s"] else "short") if not ok_len else "talk/music-gate")))
    cur = None                                   # 확장 후 겹치는 KEEP 조각은 같은 곡(쉼/말소리로 쪼개졌던 것)이라 합친다
    for o in sorted((o for o in out if o["keep"]), key=lambda o: o["start"]):
        if cur and o["start"] <= cur["end"]:
            cur["end"] = max(cur["end"], o["end"])
            cur["len"] = cur["end"] - cur["start"]
            o["keep"], o["why"] = False, "merged"
        else:
            cur = o
    return out


def hms(t):
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{int(t % 60):02d}"


if __name__ == "__main__":
    wav = Path(sys.argv[1])
    # 파라미터 덮어쓰기: python detect.py <wav> vocal_thr=0.2 gap_s=10  (결과는 기본 cache/detect/<이름>.segments.json, --out= 으로 지정 가능)
    over = {k: float(v) for k, v in (a.split("=") for a in sys.argv[2:] if "=" in a and not a.startswith("--") and not a.startswith("device="))}
    device = next((a[7:] for a in sys.argv if a.startswith("device=")), None)
    out_f = next((a[6:] for a in sys.argv if a.startswith("--out=")), None)
    segs = detect(wav, "--force" in sys.argv, {**P, **over}, device)
    print(f"{wav.name}")
    for s in segs:
        print(f"  {'KEEP' if s['keep'] else 'drop'} {hms(s['start'])} - {hms(s['end'])}  len={s['len']:.0f}s cover={s['cover']} vocal={s['vocal']} speech={s['speech']} music={s['music']} {s['why']}")
    (Path(out_f) if out_f else cache_of(wav, ".segments.json")).write_text(json.dumps(segs, ensure_ascii=False, indent=1))
