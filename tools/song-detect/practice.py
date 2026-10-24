"""연습/사운드체크 신호 (route 와 별도 모듈, 오디오만 사용). 오탐을 줄이는 쪽이라 의심되면 review 로만 보내고 drop 은 하지 않는다.
rep_near: 구간 첫 12초 크로마 창(평균 제거 코사인)이 구간 밖 +-150초에서 얼마나 닮은 곳이 있는가 = 같은 MR 시작이 근처에서 반복됨.
측정 결과(2026-10-24, cache/exp11): 끝 음량/페이드/보컬 지속 같은 완주 신호는 중도 포기 2건과 라이브 85건이 겹쳐 쓰지 않음(HANDOFF 11번).
사용: python practice.py feats <in.json [[라벨,wav,시작,끝]..]> <out.json>   (도커 song-detect 안에서, librosa 필요)
      python practice.py table <feat.json>   |   python practice.py selftest"""
import json, sys
import numpy as np

SR, W = 16000, 24                       # 크로마 간격 0.5초, 창 24개 = 12초
# shortcut: 임계값은 연습 1건(마시로 5:03:17)과 라이브 85건으로 정함. 곡 직전 사운드체크가 붙은 정상 라이브(나나 9번 0.59)도 걸리므로 review 전용
P = dict(rep_near=0.55)


def rep_near(pcm, s, e):
    import librosa
    t0 = max(0.0, s - 150)
    y = pcm[int(t0 * SR):int((e + 150) * SR)].astype(np.float32) / 32768
    C = librosa.feature.chroma_stft(y=y, sr=SR, n_fft=4096, hop_length=8000).T
    C = C - C.mean(0)
    C /= np.linalg.norm(C, axis=1, keepdims=True) + 1e-6
    X = np.stack([C[i:i + W].ravel() for i in range(len(C) - W + 1)])
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-6
    i0, i1 = int(round((s - t0) / 0.5)), int(round((e - t0) / 0.5))
    sim = X @ X[i0]
    return float(max((sim[j] for j in range(len(X)) if j < i0 - W or j > i1), default=0))


def judge(f, p=P):
    """(등급, 이유): ok / review."""
    if f["rep_near"] > p["rep_near"]:
        return "review", f"연습/사운드체크 의심: 근처에 같은 시작 {f['rep_near']:.2f}"
    return "ok", ""


def table(F):
    for k, v in F.items():
        if k.startswith("NEG"):
            print(f"{k:24} len={v['len']:4.0f} rep_near={v['rep_near']:.2f} -> {judge(v)[0]}")
    for t in ("POS", "FP"):
        G = {k: v for k, v in F.items() if k.startswith(t)}
        fl = [k for k, v in G.items() if judge(v)[0] == "review"]
        print(f"{t} {len(G)}개 중 review {len(fl)}: {fl}")


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "feats":
        from snap import pcm_of
        out = {}
        for lab, wav, s, e in json.load(open(sys.argv[2])):
            out[lab] = dict(len=e - s, rep_near=rep_near(pcm_of(wav), s, e))
            print(lab, out[lab], flush=True)
        json.dump(out, open(sys.argv[3], "w"), indent=1)
    elif c == "table":
        table(json.load(open(sys.argv[2])))
    elif c == "selftest":
        assert judge(dict(rep_near=0.6))[0] == "review" and judge(dict(rep_near=0.3))[0] == "ok"
        # 합성: 같은 12초 톤 패턴 반복 -> 높음, 노이즈 -> 낮음
        rng = np.random.default_rng(0)
        tone = (np.sin(2 * np.pi * np.cumsum(220 * 2 ** (rng.integers(0, 12, 24)[np.arange(SR * 12) // (SR // 2)] / 12)) / SR) * 8000)
        rep = np.concatenate([tone] * 5).astype("<i2")
        noise = (rng.normal(size=SR * 60) * 3000).astype("<i2")
        assert rep_near(rep, 24, 36) > 0.55 > rep_near(noise, 24, 36) + 0.2
        print("ok")
