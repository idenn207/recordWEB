"""사용자가 자른 정답 클립(data/samples/user/*.mp4)이 녹화 wav 의 어디인지 찾는다 (에너지 포락선 정규화 상호상관). 결과: data/refs.json"""
import glob, json, re, subprocess
import numpy as np

SR, FR = 16000, 800            # 50ms 프레임 (1차 탐색)
def env(y, fr):
    n = len(y) // fr
    return 20 * np.log10(np.sqrt((y[:n * fr].reshape(n, fr).astype(np.float32) ** 2).mean(1)) + 1e-5)

def load_ref(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, "<i2").astype(np.float32) / 32768

def ncc(rec, ref):
    N = len(ref); z = (ref - ref.mean()) / (ref.std() + 1e-9)
    L = 1 << int(np.ceil(np.log2(len(rec) + N)))
    num = np.fft.irfft(np.fft.rfft(rec, L) * np.conj(np.fft.rfft(z, L)), L)[:len(rec) - N + 1]
    c1, c2 = np.cumsum(np.r_[0, rec]), np.cumsum(np.r_[0, rec.astype(np.float64) ** 2])
    mean = (c1[N:] - c1[:-N]) / N; var = (c2[N:] - c2[:-N]) / N - mean ** 2
    return num / (N * np.sqrt(np.maximum(var, 1e-9)))

recs = {}
out = []
for f in sorted(glob.glob("data/samples/user/*.mp4")):
    m = re.search(r"_(26\d{4})-(.+)_001_1080p", f)
    date = "2026-10-" + m.group(1)[4:]; title = m.group(2)
    if date not in recs:
        p = f"data/vod/legacy/{date}_나나.wav"; off = open(p, "rb").read(4096).find(b"data") + 8
        recs[date] = env(np.memmap(p, dtype="<i2", mode="r", offset=off), FR)
    ref = load_ref(f); e = env(ref, FR)
    c = ncc(recs[date], e); i = int(c.argmax())
    out.append(dict(date=date, title=title, dur=len(ref) / SR, start=i * FR / SR, end=i * FR / SR + len(e) * FR / SR, corr=round(float(c[i]), 3),
                    second=round(float(np.partition(c, -50)[-50:].max() if False else np.sort(c)[-200:-100].max()), 3)))
    o = out[-1]; print(f"{date} {o['start']:8.1f}-{o['end']:8.1f} dur={o['dur']:.0f} corr={o['corr']} {title[:40]}", flush=True)
json.dump(out, open("data/refs.json", "w"), ensure_ascii=False, indent=1)
