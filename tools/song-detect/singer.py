"""가수 프로필 게이트: 구간의 Demucs 보컬 스템 -> ECAPA(speechbrain) 임베딩 -> 같은 채널 '확정 라이브' 프로필과 코사인 유사도.
낮으면 '타인 음원/다인 의심'(suspect). suspect 는 drop 이 아니라 review 로만 보낸다(듀엣/싱크룸/(w.)은 낮은 게 정상).
프로필 = 같은 스트리머의 다른 방송(videoNo/date)의 라이브 구간 임베딩 평균(같은 방송은 제외: 마이크/믹스 누수 방지).
표본: blind5+blind6 라벨(labels.json)과 나나 정답(refs.json, 1절 제외; 탐지 KEEP 중 정답/EXTRA 밖은 오탐으로 봄).
사용(도커 GPU, 스템/임베딩은 cache/exp_singer 에 캐시):
  MSYS_NO_PATHCONV=1 docker run --rm --gpus all -e TORCH_HOME=/work/cache/.torch -v "$PWD/data:/work/data" -v "$PWD/cache:/work/cache" -v "$PWD/singer.py:/work/singer.py" --entrypoint python song-detect-gpu singer.py build
  python singer.py eval      (캐시만 읽음, numpy 만 필요)     python singer.py selftest"""
import json, sys
from pathlib import Path
import numpy as np

SR, OUT = 16000, Path("cache/exp_singer")
WIN = 6        # 초, 임베딩 창(창 길이=hop)
P = dict(suspect=0.5)  # shortcut: 엄격 분할 AUC 0.50(기회 수준)이라 이 임계값은 효과 없음, route 에 연결하지 말 것. 다른 임베딩/학습(가수 식별 모델)을 쓸 때 재측정
H = lambda h, m: h * 3600 + m * 60
EXTRA = {"2026-10-16": [(H(6, 13), H(6, 17)), (H(6, 23), H(6, 27)), (H(6, 28), H(6, 32)), (H(6, 32), H(6, 36))], "2026-10-06": [(H(8, 3), H(8, 7))]}  # evaluate_refs.py 와 동일


def items():
    L = json.load(open("data/labels.json", encoding="utf8"))
    I = []
    for s in ("blind5", "blind6"):
        key = json.load(open(f"data/review/{s}/key.json", encoding="utf8"))
        for v, k in key.items():
            I.append(dict(id=f"{s}/{v}", name=k["name"], bc=str(k["videoNo"]), wav=f"data/vod/{k['videoNo']}.wav", start=k["start"], end=k["end"],
                          live=L[s][v]["live"], tag=L[s][v]["tag"] or "live", set=s))
    ov = lambda a, b, c, d: max(0, min(b, d) - max(a, c))
    refs = json.load(open("data/refs.json", encoding="utf8"))
    for d in ("2026-10-06", "2026-10-16"):
        R = [r for r in refs if r["date"] == d]
        S = [g for g in json.load(open(f"cache/detect/{d}_나나.segments.json", encoding="utf8")) if g["keep"]]
        for i, r in enumerate(R):
            if not r["title"].endswith("1절"):
                I.append(dict(id=f"nana/{d}/R{i}", name="나나", bc=d, wav=f"data/vod/legacy/{d}_나나.wav", start=r["start"], end=r["end"], live=True, tag="live", set="nana"))
        for i, g in enumerate(S):
            if any(ov(g["start"], g["end"], r["start"], r["end"]) > 0.3 * r["dur"] for r in R) or any(ov(g["start"], g["end"], a, b) > 0.5 * g["len"] for a, b in EXTRA.get(d, [])):
                continue
            I.append(dict(id=f"nana/{d}/F{i}", name="나나", bc=d, wav=f"data/vod/legacy/{d}_나나.wav", start=g["start"], end=g["end"], live=False, tag="nana_fp", set="nana"))
    return I


def stem(it, models):
    """16kHz mono 보컬 스템(float16), 캐시."""
    f = OUT / "stems" / (it["id"].replace("/", "_") + ".npy")
    if f.exists():
        return np.load(f).astype(np.float32)
    import torch, torchaudio
    from demucs.apply import apply_model
    m = models["demucs"]
    with open(it["wav"], "rb") as fh:
        off = fh.read(4096).find(b"data") + 8
    pcm = np.memmap(it["wav"], dtype="<i2", mode="r", offset=off)
    end, t, out = min(it["end"], len(pcm) / SR), it["start"], []
    while t < end:
        te = min(end, t + 60)
        x = torch.from_numpy(pcm[int(t * SR):int(te * SR)].astype(np.float32) / 32768)
        x = torchaudio.functional.resample(x, SR, 44100)[None].repeat(2, 1)
        with torch.no_grad():
            v = apply_model(m, x[None], device="cuda")[0][m.sources.index("vocals")].mean(0).cpu()
        out.append(torchaudio.functional.resample(v, 44100, SR).numpy())
        t = te
    y = np.concatenate(out)
    f.parent.mkdir(parents=True, exist_ok=True)
    np.save(f, y.astype(np.float16))
    return y


def embed(it, models):
    """(클립 임베딩, 창 임베딩 N x 192). 보컬 에너지가 중앙값의 1/4 미만인 창(간주/무음)은 뺀다. 캐시."""
    f = OUT / "emb" / (it["id"].replace("/", "_") + ".npz")
    if f.exists():
        z = np.load(f)
        return z["clip"], z["win"]
    import torch
    y = stem(it, models)
    n = WIN * SR
    W = [y[i:i + n] for i in range(0, len(y) - n + 1, n)] or [y]
    rms = np.array([np.sqrt((w ** 2).mean()) for w in W])
    W = [w for w, r in zip(W, rms) if r >= np.median(rms) / 4] or W
    with torch.no_grad():
        e = np.stack([models["ecapa"].encode_batch(torch.from_numpy(np.ascontiguousarray(w))[None].cuda())[0, 0].cpu().numpy() for w in W])
    e /= np.linalg.norm(e, axis=1, keepdims=True)
    c = e.mean(0)
    c /= np.linalg.norm(c)
    f.parent.mkdir(parents=True, exist_ok=True)
    np.savez(f, clip=c, win=e)
    return c, e


def build():
    from demucs.pretrained import get_model
    from speechbrain.inference.speaker import EncoderClassifier
    models = dict(demucs=get_model("htdemucs").eval().to("cuda"),
                  ecapa=EncoderClassifier.from_hparams(source="speechbrain/spkrec-ecapa-voxceleb", savedir="cache/.torch/ecapa", run_opts={"device": "cuda:0"}))
    I = items()
    for k, it in enumerate(I):
        embed(it, models)
        print(k + 1, "/", len(I), it["id"], flush=True)


def profile(it, I, E, strict=True):
    """같은 채널 라이브 임베딩 평균(strict: 같은 방송 제외, 아니면 자기 자신만 제외). 없으면 (None, 0)."""
    c = [E[o["id"]][0] for o in I if o["live"] and o["name"] == it["name"] and o["id"] != it["id"] and (o["bc"] != it["bc"] or not strict)]
    if not c:
        return None, 0
    p = np.mean(c, 0)
    return p / np.linalg.norm(p), len(c)


def gate(score, thr=P["suspect"]):
    """None(프로필 없음)=review 쪽, 낮으면 suspect(review + 다인/타인 의심 표시), 아니면 self. drop 은 하지 않는다."""
    return "no_profile" if score is None else "suspect" if score < thr else "self"


def auc(pos, neg):
    """Mann-Whitney AUC (동점 0.5)."""
    if not len(pos) or not len(neg):
        return float("nan")
    return float(np.mean([(p > q) + 0.5 * (p == q) for p in pos for q in neg]))


def boot(pos, neg, n=2000, seed=0):
    r = np.random.default_rng(seed)
    a = [auc(r.choice(pos, len(pos)), r.choice(neg, len(neg))) for _ in range(n)]
    return float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))


def ev():
    I = items()
    E = {it["id"]: tuple(np.load(OUT / "emb" / (it["id"].replace("/", "_") + ".npz"))[k] for k in ("clip", "win")) for it in I}
    res = {}
    for strict in (True, False):
        S = {}
        for it in I:
            p, n = profile(it, I, E, strict)
            if p is not None:
                S[it["id"]] = (float(E[it["id"]][0] @ p), n)
        res[strict] = S
    by = {it["id"]: it for it in I}
    for strict, S in res.items():
        pos = [s for i, (s, n) in S.items() if by[i]["live"]]
        neg = [s for i, (s, n) in S.items() if not by[i]["live"]]
        print(f"\n== {'엄격(같은 방송 제외)' if strict else '느슨(자기만 제외, 같은 방송 누수 있음)'}: 프로필 있는 라이브 {len(pos)}, 오탐 {len(neg)}")
        if pos and neg:
            lo, hi = boot(np.array(pos), np.array(neg))
            print(f"  AUC {auc(pos, neg):.3f} [95% 부트스트랩(항목 단위, 방송 상관 무시) {lo:.2f}-{hi:.2f}]")
        for nm in sorted({by[i]["name"] for i in S}):
            ps = [s for i, (s, n) in S.items() if by[i]["name"] == nm and by[i]["live"]]
            ns = [s for i, (s, n) in S.items() if by[i]["name"] == nm and not by[i]["live"]]
            print(f"  {nm}: 라이브 {len(ps)} 평균 {np.mean(ps):.2f}  오탐 {len(ns)}" + (f" 평균 {np.mean(ns):.2f}  AUC {auc(ps, ns):.2f}" if ns and ps else ""))
        for tg in sorted({by[i]["tag"] for i in S}):
            v = [s for i, (s, n) in S.items() if by[i]["tag"] == tg]
            print(f"  유형 {tg:16} n={len(v):2} 평균 {np.mean(v):.2f} 범위 {min(v):.2f}~{max(v):.2f}")
        if strict:
            print("  임계값 표(suspect = 점수 < t): t  라이브 suspect 수 / 오탐 suspect 수")
            for t in (0.3, 0.4, 0.5, 0.6, 0.7):
                print(f"    {t}: {sum(s < t for s in pos)}/{len(pos)}  {sum(s < t for s in neg)}/{len(neg)}")
    # 교차 채널 impostor: 다른 스트리머 라이브 구간을 해당 채널 프로필(엄격)에 대보기. 오탐 유형(커버/같이보기)의 대리 지표일 뿐
    imp, own = [], []
    for it in I:
        if not it["live"]:
            continue
        for nm in {o["name"] for o in I if o["live"]} - {it["name"]}:
            c = [E[o["id"]][0] for o in I if o["live"] and o["name"] == nm and o["bc"] != it["bc"]]
            if c:
                p = np.mean(c, 0)
                imp.append(float(E[it["id"]][0] @ (p / np.linalg.norm(p))))
    own = [s for i, (s, n) in res[True].items() if by[i]["live"]]
    print(f"\n== 교차 채널 impostor(다른 스트리머 라이브 -> 이 채널 프로필): {len(imp)}쌍, 평균 {np.mean(imp):.2f} / 본인 라이브 {len(own)}개 평균 {np.mean(own):.2f}  AUC {auc(own, imp):.3f}")
    json.dump({("strict" if k else "loose"): {i: v for i, v in S.items()} for k, S in res.items()}, open(OUT / "scores.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
    toa = [(i, s) for i, (s, n) in res[True].items() if i.startswith("blind6") and by[i]["name"] == "시즈키 토아"]
    print(f"\n== 토아 싱크룸 blind6(정상 클립, 토아 목소리 아닌 것 포함): 프로필 라이브 {res[True][toa[0][0]][1] if toa else 0}개 근거, 점수", sorted(round(s, 2) for _, s in toa))


def selftest():
    assert auc([3, 4], [1, 2]) == 1 and auc([1], [1]) == 0.5
    a = np.eye(3)
    I = [dict(id="a", name="x", bc="1", live=True), dict(id="b", name="x", bc="1", live=True), dict(id="c", name="x", bc="2", live=True), dict(id="d", name="y", bc="3", live=True)]
    E = {"a": (a[0],), "b": (a[1],), "c": (a[2],), "d": (a[0],)}
    p, n = profile(I[0], I, E)           # a 의 엄격 프로필 = 다른 방송 c 만
    assert n == 1 and np.allclose(p, a[2])
    assert profile(I[3], I, E)[0] is None and gate(None) == "no_profile" and gate(0.1) == "suspect" and gate(0.9) == "self"
    print("selftest ok")


if __name__ == "__main__":
    {"build": build, "eval": ev, "selftest": selftest}[sys.argv[1]]()
