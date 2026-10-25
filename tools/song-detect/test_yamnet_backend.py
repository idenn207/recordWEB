"""YAMNet 백엔드 단위 테스트 (작은 합성 신호). 도커에서(CPU 이미지로도 됨; torch 는 CPU 로 돈다):
MSYS_NO_PATHCONV=1 docker run --rm --entrypoint python -v "$PWD/test_yamnet_backend.py:/work/test_yamnet_backend.py" -v "$PWD/yamnet_backend.py:/work/yamnet_backend.py" song-detect test_yamnet_backend.py"""
import os, tempfile
import numpy as np
import yamnet_backend as Y

rng = np.random.default_rng(0)
t = np.arange(Y.SR * 200) / Y.SR                                   # 200초: 사인 화음 + 잡음 + 말소리 비슷한 변조 잡음이 번갈아
sig = 0.3 * np.sin(2 * np.pi * 440 * t) + 0.2 * np.sin(2 * np.pi * 660 * t) * (np.sin(2 * np.pi * 0.3 * t) > 0)
sig += 0.05 * rng.standard_normal(len(t)) * (1 + np.sin(2 * np.pi * 4 * t))
pcm = (np.clip(sig, -1, 1) * 32767).astype("<i2")
starts = np.arange(0, len(pcm) - Y.WIN, 1600)                      # 0.1초 간격 1900여 창

a = Y.scores_windows(pcm, starts[:300], "cpu")                     # TFLite (기존 경로)
b = Y._scores_torch(pcm, starts[:300], Y.class_idx(("Singing", "Speech", "Music")), "cpu")
assert a.shape == b.shape == (300, 3), (a.shape, b.shape)
assert np.abs(a - b).max() < 0.1, np.abs(a - b).max(axis=0)       # 실측(실제 방송 1시간): 최대 0.086, 평균 5e-4
assert all(np.corrcoef(a[:, i], b[:, i])[0, 1] > 0.99 for i in range(3))
assert Y.scores_windows(pcm, starts[:5], "cpu", cls=("Music",)).shape == (5, 1)
assert Y.scores_windows(pcm, [], "cuda" if Y.resolve("auto") == "cuda" else "cpu").shape[0] == 0

# CPU 청크 병렬은 단일 프로세스와 비트 단위로 같아야 한다 (창이 서로 독립)
with tempfile.TemporaryDirectory() as d:
    w = os.path.join(d, "x.wav")
    open(w, "wb").write(b"RIFF" + bytes(4) + b"WAVEfmt " + bytes(20) + b"data" + (len(pcm) * 2).to_bytes(4, "little") + pcm.tobytes())
    m = Y._open(w)
    assert (m[:1000] == pcm[:1000]).all()
    one = Y.scores_windows(m, starts, "cpu")
    two = Y.scores_windows(m, starts, "cpu", workers=2, src=w)
    assert np.array_equal(one, two)

os.environ["SONG_DEVICE"] = "cpu"
assert Y.resolve() == "cpu" and Y.resolve("cuda") == "cuda"
try:
    Y.resolve("tpu")
    raise SystemExit("잘못된 device 가 통과됨")
except ValueError:
    pass
print("ok")
