"""E3 변형 시험(읽기 전용 실험, snap.py 수정 없음).
A) deep_end 의 '뒤 4초가 ref-nxt_db 보다 조용' 기준을 12 -> N dB: 한 값으로는 #60/#112(좋은 이동)와 726(나쁜 이동)이 같이 켜지거나 같이 꺼진다.
B) 코다 보존: E3 가 끝을 무음 시작 t0 로 당긴 뒤, 무음이 끝난 곳부터 (rms >= ref-CODA_DB & Speech<0.3, 틈 1초 이하)로 이어지는 소리가 4초 이상이면 그 끝을 곡 끝으로(조용한 피아노 코다 보존).
사용: python experiments/audit_e3_variant.py [A 12 20 25 30 | B 25 22 18]"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import audit_engine as E, snap
from snap import rms_db, HOP, FR
M = json.load(open(E.ROOT / "cache/audit/master.json", encoding="utf8"))
orig = snap.deep_end
CASES = {("15761307", 724): "726(재생목록 정답 끝 1083, 곡 끝=코다 1068 근처)", ("2026-10-17_rang_1", 396): "#60 B late(정답 +33.6->+0.3)", ("2026-10-23_mary_1", 18745): "#112 B late(+6.0->+0.4)"}

def deep_end_B(pcm, a, ref, e, coda_db=25.0, minrun=4.0, gap=1.0):
    t0 = orig(pcm, a, ref, e)
    if t0 >= e - 1e-6: return e
    ts, db = rms_db(pcm, t0, min(e, t0 + 60))
    i = 0
    while i < len(ts) and db[i] < ref - 30: i += 1            # 깊은 무음이 끝나는 곳
    sp = a[np.minimum((ts / HOP).astype(int), len(a) - 1), 1]
    ok = (db >= ref - coda_db) & (sp < 0.3)
    last, bad, start = None, 0, None
    for k in range(i, len(ts)):
        if ok[k]:
            if start is None: start = k
            last, bad = k, 0
        else:
            bad += 1
            if bad * FR > gap and start is not None: break
    if last is not None and (last - start + 1) * FR >= minrun and start * FR - i * FR < 5.0:
        return float(ts[last]) + FR
    return t0

def run(label, f):
    snap.deep_end = f
    kept = ext = tot = 0
    out = []
    for r in M:
        if "only" not in r or abs(r["only"]["E3"][1]) <= 1: continue
        tot += 1
        new = E.calc(r["vid"], r["refine"][0], r["refine"][1], E.ALL - {"E3"}, False)
        d = new["song_e"] - r["v3"]["song_e"]
        kept += abs(d) > 1
        for (v, s), nm in CASES.items():
            if r["vid"] == v and abs(r["v3"]["song_s"] - s) < 8: out.append(f"{nm}: 끝 {d:+.1f}")
    print(f"{label}: E3 이동 {tot}개 중 이동 유지 {kept}개 | " + " | ".join(out))
    E._W.clear()

a = sys.argv[1:] or ["B", "25", "22", "18"]
if a[0] == "A":
    for nx in map(float, a[1:]): run(f"A nxt_db={nx:.0f}", lambda pcm, A, ref, e, nx=nx, **k: orig(pcm, A, ref, e, nxt_db=nx))
else:
    for cd in map(float, a[1:]): run(f"B coda_db={cd:.0f}", lambda pcm, A, ref, e, cd=cd, **k: deep_end_B(pcm, A, ref, e, cd))
