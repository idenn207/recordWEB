"""작업대 보조: 방송 wav 전체의 0.1초 rms(dBFS) 트랙을 cache/proto_boundary/db/<이름>.npy 로 만든다(규칙 격자 탐색 가속용, 원본 wav 는 읽기만)."""
import sys, os
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
import numpy as np
from snap import pcm_of
D = ROOT / "cache/proto_boundary/db"; D.mkdir(parents=True, exist_ok=True)
def track(wav):
    f = D / (Path(wav).stem + ".npy")
    if f.exists(): return np.load(f)
    pcm = pcm_of(wav); n = len(pcm) // 1600; out = np.empty(n, np.float32); B = 1600 * 3000
    for i in range(0, n, 3000):
        x = pcm[i * 1600:min(n, i + 3000) * 1600].astype(np.float32).reshape(-1, 1600) / 32768
        out[i:i + len(x)] = 10 * np.log10((x ** 2).mean(1) + 1e-12)
    np.save(f, out); return out
if __name__ == "__main__":
    for w in sorted(Path("data/vod/nas").glob("*.wav")):
        track(w); print(w.name, flush=True)
