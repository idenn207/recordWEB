"""완성본 클립의 음량이 원본(방송 wav)과 같은지: 곡 안쪽 구간(앞뒤 3초 제외)의 rms(dB)를 클립 오디오와 원본 wav 에서 재서 차이를 낸다. 원본 음량 유지(리미터 없음) 확인용.
사용: python experiments/regen_loudness.py [최대허용dB=1.0]      (out/final, out/final_review 의 현재 RULE 클립 전부; 종료코드 1 = 허용 초과 클립 있음)
shortcut: 클립 오디오는 16kHz 모노로 내려서 잰다(wav 가 16kHz 라 같은 조건), 인코딩 손실은 평균 -0.1dB(최대 0.22) 로 보인다."""
import glob, json, subprocess, sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from snap import pcm_of
from make_final import RULE

lim = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
nas = {r["slug"]: r for r in json.load(open(ROOT / "data/nas_index.json", encoding="utf8"))}
db = lambda x: 20 * np.log10(np.sqrt((x.astype(np.float64) ** 2).mean()) + 1e-12)
rows = []
for f in sorted(glob.glob(str(ROOT / "out/final*/*/*.json"))):
    if f.endswith("_ctx20.json") or "stale" in f:
        continue
    j = json.load(open(f, encoding="utf8"))
    if j.get("rule") != RULE or not j.get("ok"):
        continue
    sl = "_".join(Path(f).parent.name.split("_")[2:])
    a, b = j["song_start"] + 3, j["song_end"] - 3
    off = j["song_start"] - j["vod_start"]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{off + 3:.3f}", "-t", f"{b - a:.3f}", "-i", f[:-5] + ".mp4", "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True, check=True).stdout
    c = np.frombuffer(raw, np.int16)
    w = pcm_of(nas[sl]["wav"] if Path(nas[sl]["wav"]).is_absolute() else str(ROOT / nas[sl]["wav"]))[int(a * 16000):int(b * 16000)]
    rows.append((db(c) - db(w), Path(f).stem, len(c) / 16000, b - a))
d = np.array([r[0] for r in rows])
assert len(rows) > 0
bad = [r for r in rows if abs(r[0]) > lim]
print(f"클립 {len(rows)}개, 클립-원본 rms 차이 평균 {d.mean():+.2f}dB 최소 {d.min():+.2f} 최대 {d.max():+.2f}, 허용({lim}dB) 초과 {len(bad)}개")
for r in bad:
    print(f"  {r[1]} {r[0]:+.2f}dB (비교 길이 클립 {r[2]:.1f}초 / 원본 {r[3]:.1f}초)")
sys.exit(1 if bad else 0)
