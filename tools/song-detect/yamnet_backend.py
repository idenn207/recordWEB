"""YAMNet 점수 백엔드. detect.py / refine.py 가 같이 쓴다.
scores_windows(pcm, starts, device) -> (n, 클래스 수) float32. pcm 은 int16 배열(memmap 가능), starts 는 창 시작 샘플(창 길이 WIN, 전부 파일 안).
device: "cpu" = TFLite 한 창씩(기존 경로, NAS 호환, 결과 불변) / "cuda" = yamnet.tflite 의 int8 가중치를 torch 로 옮긴 배치 추론 / "auto" = cuda 가능하면 cuda.
기본값은 환경변수 SONG_DEVICE (없으면 auto). GPU 부하 제한: SONG_GPU_LIMIT(기본 0.8 = 작업 시간 대비 가동률, 배치 사이에 쉼), SONG_GPU_MEM(기본 0.8 = VRAM 비율). GPU 경로는 tflite 의 int8 양자화(곱셈은 정수 정확, 재양자화는 XNNPACK 방식 fp32)를 그대로 흉내 낸다."""
import csv, os, time
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
from pathlib import Path
import numpy as np

SR, WIN = 16000, 15600
HERE = Path(__file__).parent
MODELS = HERE / "models" if (HERE / "models").exists() else HERE
BATCH = 256                       # GPU 한 번에 묶는 창 수
_cache = {}


def resolve(device=None):
    d = (device or os.environ.get("SONG_DEVICE") or "auto").lower()
    if d not in ("auto", "cuda", "cpu"):
        raise ValueError(f"device 는 auto|cuda|cpu: {d}")
    if d == "auto":
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"
    return d


def gpu_init():
    """VRAM 을 SONG_GPU_MEM 비율(기본 0.8)로 제한. 프로세스당 한 번."""
    if "gpu_init" not in _cache:
        import torch
        torch.cuda.set_per_process_memory_fraction(min(1.0, float(os.environ.get("SONG_GPU_MEM", 0.8))))
        _cache["gpu_init"] = 1


def gpu_rest(t0):
    """배치 하나를 t0 에 시작해 끝낸 뒤 가동률이 SONG_GPU_LIMIT(기본 0.8)을 넘지 않게 쉰다. shortcut: 배치 단위 듀티라 순간 사용률은 100% 일 수 있다."""
    import torch
    torch.cuda.synchronize()
    lim = min(1.0, max(0.05, float(os.environ.get("SONG_GPU_LIMIT", 0.8))))
    if lim < 1:
        time.sleep((time.time() - t0) * (1 / lim - 1))


def class_idx(names):
    allnames = [r[2] for r in csv.reader(open(MODELS / "yamnet_class_map.csv", encoding="utf8"))][1:]
    return [allnames.index(n) for n in names]


# ---------------- CPU: TFLite (기존 경로 그대로) ----------------
def _tflite_chunk(a):
    pcm_src, starts, want = a
    pcm = _open(pcm_src)
    if "tflite" not in _cache:                                   # refine 이 짧게 여러 번 부르므로 인터프리터는 프로세스당 한 번
        from ai_edge_litert.interpreter import Interpreter
        it = Interpreter(model_path=str(MODELS / "yamnet.tflite"))
        it.allocate_tensors()
        _cache["tflite"] = it
    it = _cache["tflite"]
    inp, out = it.get_input_details()[0], it.get_output_details()[0]
    res = []
    for i in starts:
        x = pcm[i:i + WIN].astype(np.float32) / 32768.0
        it.set_tensor(inp["index"], x.reshape(inp["shape"]))
        it.invoke()
        res.append(it.get_tensor(out["index"]).reshape(-1)[want])
    return np.array(res, dtype=np.float32).reshape(len(starts), len(want))


def _open(src):
    """프로세스 사이에는 배열 대신 wav 경로를 넘긴다 (memmap 은 피클되지 않는다)."""
    if not isinstance(src, (str, Path)):
        return src
    with open(src, "rb") as f:
        off = f.read(4096).find(b"data") + 8
    return np.memmap(src, dtype="<i2", mode="r", offset=off)


def _scores_tflite(pcm, starts, want, workers=1, src=None):
    starts = [int(s) for s in starts]
    if workers > 1 and src is not None and len(starts) >= 2000:     # shortcut: 창이 서로 독립이라 청크로 나눠도 결과 동일. 작은 입력은 프로세스 기동이 더 비싸다
        k = -(-len(starts) // workers)
        parts = [(str(src), starts[i:i + k], want) for i in range(0, len(starts), k)]
        with ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("spawn")) as ex:
            return np.concatenate(list(ex.map(_tflite_chunk, parts)))
    return _tflite_chunk((pcm, starts, want))


# ---------------- GPU: torch (tflite int8 그래프 재현) ----------------
def _load_params():
    from ai_edge_litert.interpreter import Interpreter
    it = Interpreter(model_path=str(MODELS / "yamnet.tflite"))
    it.allocate_tensors()
    td = {t["index"]: t for t in it.get_tensor_details()}
    q = lambda i: (float(td[i]["quantization_parameters"]["scales"][0]), int(td[i]["quantization_parameters"]["zero_points"][0]))
    P = dict(hann=it.get_tensor(11), mel=it.get_tensor(22), melb=it.get_tensor(23), layers=[])
    P["in_q"] = q(28)
    for o in it._get_ops_details():
        n = o["op_name"]
        if n in ("CONV_2D", "DEPTHWISE_CONV_2D", "FULLY_CONNECTED") and o["index"] >= 16 and len(o["inputs"]) == 3:
            x, w, b = (int(v) for v in o["inputs"])
            y = int(o["outputs"][0])
            ws = td[w]["quantization_parameters"]["scales"]
            P["layers"].append(dict(kind=n, w=it.get_tensor(w), b=it.get_tensor(b), ws=ws, xq=q(x), yq=q(y),
                                    stride=2 if td[x]["shape"][1] > td[y]["shape"][1] else 1))
        elif n == "MEAN":
            P["mean"] = (q(int(o["inputs"][0])), q(int(o["outputs"][0])))
        elif n == "LOGISTIC":
            P["sig"] = (q(int(o["inputs"][0])), q(int(o["outputs"][0])))
    return P


def _model(dev):
    if dev in _cache:
        return _cache[dev]
    import torch
    P = _load_params()
    torch.backends.cudnn.allow_tf32 = False      # TF32 면 정수 누적이 깨진다
    dt = torch.float32       # shortcut: int8 누적을 fp32 로 (합이 2^24 를 넘으면 틀린다; 실측 fp64 와 점수 동일), 의심되면 float64
    T = lambda a, d=dt: torch.as_tensor(np.asarray(a), dtype=d, device=dev)
    M = dict(hann=T(P["hann"], torch.float32), mel=T(P["mel"], torch.float32), melb=T(P["melb"], torch.float32), in_q=P["in_q"],
             mean=P["mean"], sig=P["sig"], layers=[])
    for L in P["layers"]:
        (sx, zx), (sy, zy) = L["xq"], L["yq"]
        mult = (np.float32(sx) * np.asarray(L["ws"], dtype=np.float32) / np.float32(sy)).astype(np.float32)
        w = L["w"]
        if L["kind"] == "CONV_2D":
            w = w.transpose(0, 3, 1, 2)
        elif L["kind"] == "DEPTHWISE_CONV_2D":
            w = w.transpose(3, 0, 1, 2)
        M["layers"].append(dict(kind=L["kind"], w=T(w), b=T(L["b"]), mult=T(mult, torch.float32), zx=zx, zy=zy, stride=L["stride"]))
    _cache[dev] = M
    return M


def _requant(acc, b, mult, zy, shape):
    import torch
    y = (acc + b.view(shape)).float() * mult.view(shape)
    return (torch.round(y) + zy).clamp(-128, 127)       # torch.round = 짝수 반올림 (XNNPACK lrintf)


def _forward(M, x):
    """x: (B, 15600) float32 [-1,1) -> (B, 521) float32 확률."""
    import torch, torch.nn.functional as F
    fr = x.unfold(1, 400, 160) * M["hann"]                                   # (B, 96, 400)
    mag = torch.fft.rfft(F.pad(fr, (0, 112)), dim=-1).abs()                  # (B, 96, 257)
    lm = torch.log(mag @ M["mel"].T + M["melb"])                             # (B, 96, 64)
    s, z = M["in_q"]
    h = (torch.round(lm / s) + z).clamp(-128, 127).unsqueeze(1)     # (B, 1, 96, 64) 양자화 값
    for L in M["layers"]:
        if L["kind"] == "FULLY_CONNECTED":
            acc = (h - L["zx"]) @ L["w"].T
            h = _requant(acc, L["b"], L["mult"], L["zy"], (1, -1))
            break
        d = h - L["zx"]
        k = L["w"].shape[-1]      # 정사각 3x3 / 1x1; TF SAME 패딩(스트라이드 2 에 짝수 크기면 뒤쪽 1칸)
        h, stride = d, L["stride"]
        H, W = h.shape[-2:]
        ph, pw = max((-(-H // stride) - 1) * stride + k - H, 0), max((-(-W // stride) - 1) * stride + k - W, 0)
        h = F.pad(h, (pw // 2, pw - pw // 2, ph // 2, ph - ph // 2))
        g = L["w"].shape[0] if L["kind"] == "DEPTHWISE_CONV_2D" else 1
        acc = F.conv2d(h, L["w"], stride=stride, groups=g)
        h = _requant(acc, L["b"], L["mult"], L["zy"], (1, -1, 1, 1))
        if L is M["layers"][-2]:                                             # 마지막 conv 뒤: 평균 풀링 (int8 -> int8, 스케일 변환)
            (s0, z0), (s1, z1) = M["mean"]
            h = (torch.round((h - z0).mean((2, 3)) * (s0 / s1)) + z1).clamp(-128, 127)
    (si, zi), (so, zo) = M["sig"]
    p = torch.sigmoid((h - zi) * si)
    return (torch.round(p / so) + zo).clamp(-128, 127).sub(zo).mul(so).float()


def scores_windows(pcm, starts, device=None, cls=("Singing", "Speech", "Music"), workers=1, src=None):
    """starts: 창 시작 샘플 목록. src: pcm 의 wav 경로 (workers>1 일 때만 필요)."""
    want = class_idx(cls)
    dev = resolve(device)
    if dev == "cpu":
        return _scores_tflite(pcm, starts, want, workers, src)
    return _scores_torch(pcm, starts, want, dev)


def _scores_torch(pcm, starts, want, dev):
    import torch
    if dev == "cuda":
        gpu_init()
    M = _model(dev)
    starts = np.asarray(starts, dtype=np.int64)
    out = []
    for i in range(0, len(starts), BATCH):
        t0 = time.time()
        s = starts[i:i + BATCH]
        lo, hi = int(s.min()), int(s.max()) + WIN
        seg = torch.from_numpy(np.array(pcm[lo:hi])).to(dev)           # int16 로 올려 GPU 에서 변환
        idx = torch.as_tensor(s - lo, device=dev)[:, None] + torch.arange(WIN, device=dev)
        x = seg[idx].float() / 32768.0
        with torch.no_grad():
            out.append(_forward(M, x)[:, want].cpu().numpy())
        if dev == "cuda":
            gpu_rest(t0)
    return np.concatenate(out) if out else np.zeros((0, len(want)), np.float32)
