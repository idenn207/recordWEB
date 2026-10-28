"""(c) 음악 구조 기법: 크로마+MFCC 자기유사 행렬(SSM) 의 Foote novelty 와 librosa 비트 트래킹이 사용자 정답 경계를 설명하는지 잰다(GPU: SSM/커널 합성곱은 torch).
정답 경계 = memo_audit 의 숫자 정답(라이브 곡-경계) + 사용자가 '경계 좋음'이라 한 곡의 현재 경계(ok). 창 = 경계 +-45초.
지표: (1) novelty 봉우리가 정답 +-0.5/1/3초 안에 있는 비율(recall), 창 안 봉우리 밀도(개/분), 무작위 시각 대비 우연 적중률.
      (2) 비트: 정답이 비트 격자에서 떨어진 위상(비트 길이 대비 0~0.5)의 분포 vs 무작위(평균 0.25).
사용: python experiments/bl_struct.py   (venv: C:/_tools/wt/venv/Scripts/python.exe, librosa/torch 필요)"""
import sys, os, json, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "experiments")); os.chdir(ROOT)
import numpy as np, torch, librosa
import memo_audit as M
from snap import pcm_of
from paths import cache_of
SR, HOPS = 16000, 8000                       # 0.5초 프레임
OUT = ROOT / "cache/proto_boundary"
dev = "cuda" if torch.cuda.is_available() else "cpu"


def feats(y):
    ch = librosa.feature.chroma_stft(y=y, sr=SR, hop_length=HOPS, n_fft=4096)
    mf = librosa.feature.mfcc(y=y, sr=SR, hop_length=HOPS, n_mfcc=13, n_fft=2048)[1:]
    f = np.vstack([ch / (np.linalg.norm(ch, axis=0, keepdims=True) + 1e-9), (mf - mf.mean(1, keepdims=True)) / (mf.std(1, keepdims=True) + 1e-9) / 3.5])
    return f.T.astype(np.float32)               # (프레임, 24)


def novelty(F, L):
    """Foote: 코사인 SSM 에 L 프레임 가우시안 체커보드 커널을 대각선으로 합성곱."""
    X = torch.tensor(F, device=dev)
    X = X / (X.norm(dim=1, keepdim=True) + 1e-9)
    S = X @ X.T
    k = torch.arange(-L, L, device=dev).float() + 0.5
    g = torch.exp(-(k / (L / 2)) ** 2 / 2)
    K = torch.sign(k)[:, None] * torch.sign(k)[None, :] * g[:, None] * g[None, :]
    n = S.shape[0]
    nov = torch.zeros(n, device=dev)
    for i in range(L, n - L):
        nov[i] = (S[i - L:i + L, i - L:i + L] * K).sum()
    nov = torch.clamp(nov, min=0)
    return (nov / (nov.max() + 1e-9)).cpu().numpy()


def peaks(nov, thr_sd=1.0, minsep=6):
    z = (nov - nov.mean()) / (nov.std() + 1e-9)
    p = [i for i in range(1, len(nov) - 1) if nov[i] >= nov[i - 1] and nov[i] > nov[i + 1] and z[i] >= thr_sd]
    out = []
    for i in sorted(p, key=lambda i: -nov[i]):
        if all(abs(i - j) >= minsep for j in out):
            out.append(i)
    return sorted(out)


def points():
    exp = M.jl(M.EXP)
    P = []
    for g in exp["groups"]:
        for sd in ("start", "end"):
            s = g["sides"][sd]
            if s["truth"] is not None and g["lab"] != "N":
                P.append(dict(gid=g["gid"], side=sd, t=s["truth"], vno=g["vno"], kind="truth"))
    return P


if __name__ == "__main__":
    P = points()
    rng = np.random.default_rng(0)
    res = {}
    for L in (4, 8, 16):                              # 커널 반폭: 2초, 4초, 8초
        hit = {0.5: 0, 1.0: 0, 3.0: 0}; dens = []; chance = {0.5: 0, 1.0: 0, 3.0: 0}
        for q in P:
            w = f"data/vod/nas/{q['vno']}.wav"
            pcm = pcm_of(w)
            t0 = q["t"] - 45
            y = pcm[int(t0 * SR):int((q["t"] + 45) * SR)].astype(np.float32) / 32768
            F = feats(y)
            nov = novelty(F, L)
            pk = np.array(peaks(nov)) * 0.5 + t0
            dens.append(len(pk) / 1.5)
            d = np.abs(pk - q["t"]).min() if len(pk) else 99
            for r in hit:
                hit[r] += d <= r
                # 우연 적중률: 같은 밀도의 무작위 봉우리 위치 1000번
                ru = rng.uniform(t0, t0 + 90, (1000, max(len(pk), 1)))
                chance[r] += float((np.abs(ru - q["t"]).min(1) <= r).mean())
            q[f"d{L}"] = float(d)
        res[L] = dict(n=len(P), hit=hit, chance={r: round(v, 2) for r, v in chance.items()}, dens_per_min=round(float(np.mean(dens)), 1))
        print(f"SSM novelty L={L * 0.5:g}s: 정답 {len(P)}개 중 봉우리 +-0.5/1/3초 적중 {hit[0.5]}/{hit[1.0]}/{hit[3.0]}, 같은 밀도 무작위 기대 {res[L]['chance'][0.5]}/{res[L]['chance'][1.0]}/{res[L]['chance'][3.0]}, 창 안 봉우리 {res[L]['dens_per_min']}개/분", flush=True)
    # 비트 위상
    ph = []
    for q in P:
        w = f"data/vod/nas/{q['vno']}.wav"
        pcm = pcm_of(w)
        t0 = q["t"] - 20 if q["side"] == "start" else q["t"] - 40
        y = pcm[int(max(t0, 0) * SR):int((q["t"] + 40) * SR)].astype(np.float32) / 32768
        oenv = librosa.onset.onset_strength(y=y, sr=SR, hop_length=256)
        tempo, bt = librosa.beat.beat_track(onset_envelope=oenv, sr=SR, hop_length=256)
        bt = librosa.frames_to_time(bt, sr=SR, hop_length=256) + max(t0, 0)
        if len(bt) < 4:
            q["phase"] = None; continue
        per = np.median(np.diff(bt))
        # 정답 바로 뒤 첫 온셋(곡/마디 시작은 비트 위에 있다는 가설): 정답 +-0.5초 안 onset 최대 시각
        ts = librosa.frames_to_time(np.arange(len(oenv)), sr=SR, hop_length=256) + max(t0, 0)
        m = (ts >= q["t"] - 0.5) & (ts <= q["t"] + 1.5)
        to = ts[m][np.argmax(oenv[m])] if m.any() else q["t"]
        d = (to - bt[np.argmin(np.abs(bt - to))])
        q["phase"] = float(abs(d) / per); q["tempo"] = float(np.atleast_1d(tempo)[0]); q["beat_per"] = float(per)
        ph.append(q["phase"])
    print(f"비트 위상(정답 근처 최대 온셋의 비트 격자 이탈 / 비트 길이, 무작위 평균 0.25): n={len(ph)} 평균 {np.mean(ph):.2f} 중앙 {np.median(ph):.2f}, 0.1 이내 {sum(p <= 0.1 for p in ph)}/{len(ph)}")
    (OUT / "struct.json").write_text(json.dumps(dict(ssm=res, points=P), ensure_ascii=False, indent=1, default=float), encoding="utf8")
