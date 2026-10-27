"""자체 시청 검수용 그림 + 수치: 완성본 클립마다 (1) 시작/중간/끝 프레임 3장, (2) 시작 창과 끝 창의 스펙트로그램/0.25초 rms/점수, (3) 오디오 진단 수치를 만든다.
사용: python experiments/self_check_media.py [auto review ...] [--slug 부분문자열] [--only N]    -> cache/regen/media/<id>.png, cache/regen/media/diag.json
그림은 Read 로 열어 화면 유형(본인 모델/마이크, 같이보기, 게임 HUD, 대기화면)과 시작/끝(전주, 호흡, 멘트, MR 종료)을 본다. 귀로 듣는 것은 아니다(프레임/파형 수준).
shortcut: 프레임은 클립 mp4 에서 3장만 뽑아 화면 판정의 표본이 작다(중간 장면 전환은 못 봄), 스펙트로그램은 16kHz wav 라 8kHz 까지."""
import json, subprocess, sys, tempfile, wave
from pathlib import Path
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from paths import cache_of
from snap import rms_db

OUT = ROOT / "cache/regen/media"
DIRS = dict(auto="out/final", review="out/final_review")


def frame(mp4, t, tmp):
    p = Path(tmp) / f"f{t:.1f}.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(mp4), "-frames:v", "1", "-vf", "scale=640:-2", str(p)], check=True)
    return plt.imread(p)


def load(wav, t0, t1):
    w = wave.open(wav); sr = w.getframerate(); t0 = max(0.0, t0); w.setpos(int(t0 * sr))
    return t0, sr, np.frombuffer(w.readframes(int((t1 - t0) * sr)), dtype=np.int16).astype(np.float32) / 32768


def win(ax3, wav, S, t0, t1, marks, title):
    t0, sr, x = load(wav, t0, t1); t1 = t0 + len(x) / sr
    ax3[0].specgram(x, NFFT=1024, Fs=sr, noverlap=512, cmap="magma", vmin=-130, vmax=-40, xextent=(t0, t1)); ax3[0].set_ylim(0, 6000); ax3[0].set_title(title, fontsize=9)
    h = int(sr * 0.25); n = len(x) // h
    ax3[1].plot(t0 + np.arange(n) * 0.25, 20 * np.log10(np.sqrt((x[:n * h].reshape(n, h) ** 2).mean(1)) + 1e-6), "k", lw=.8); ax3[1].set_ylim(-70, 0); ax3[1].set_ylabel("rms", fontsize=7)
    i0 = int(t0 * 2); tt = np.arange(i0, min(int(t1 * 2), len(S))) / 2
    for k, c in enumerate("rbg"):                                  # Singing 빨강, Speech 파랑, Music 초록
        ax3[2].plot(tt, S[i0:i0 + len(tt), k], c, lw=.8)
    ax3[2].set_ylim(0, 1)
    for i, (t, l) in enumerate(marks):
        if t0 <= t <= t1:
            for a in ax3:
                a.axvline(t, color="cyan" if "cut" in l else "lime", ls="--", lw=1.2)
            ax3[0].text(t, 6100 + (i % 2) * 400, l, fontsize=7, clip_on=False)


def diag(wav_pcm, S, j):
    s, e, cs, ce = j["song_start"], j["song_end"], j["vod_start"], j["vod_end"]
    ref = float(np.median(rms_db(wav_pcm, s, e)[1]))
    sc = lambda a, b: S[int(a * 2):max(int(a * 2) + 1, int(b * 2))]
    f = lambda a, b: [round(float(v), 2) for v in sc(a, b).mean(0)]                      # [Singing, Speech, Music] 평균
    sp = lambda a, b: round(float((sc(a, b)[:, 1] > 0.3).mean()), 2) if b > a else 0.0     # Speech>0.3 창 비율
    return dict(song_len=round(e - s, 1), lead=round(s - cs, 2), trail=round(ce - e, 2), first10=f(s, s + 10), last10=f(e - 10, e), speech_lead=sp(cs, s), speech_trail=sp(e, ce),
                speech_first10=sp(s, s + 10), speech_last10=sp(e - 10, e), start_db=round(float(np.median(rms_db(wav_pcm, s, s + 1)[1])) - ref, 1), end_db=round(float(np.median(rms_db(wav_pcm, e - 1, e)[1])) - ref, 1),
                after_db=round(float(np.median(rms_db(wav_pcm, e, e + 1)[1])) - ref, 1))


def run(tiers, slug=None, only=None):
    OUT.mkdir(parents=True, exist_ok=True)
    nas = {r["slug"]: r for r in json.load(open(ROOT / "data/nas_index.json", encoding="utf8"))}
    dj = OUT / "diag.json"
    D = json.load(open(dj, encoding="utf8")) if dj.exists() else {}
    from snap import pcm_of
    for t in tiers:
        for js in sorted((ROOT / DIRS[t]).glob("*/*.json")):
            if js.name.endswith("_ctx20.json") or (slug and slug not in js.parent.name):
                continue
            j = json.load(open(js, encoding="utf8"))
            if not j.get("ok") or j.get("rule") != "v5-bounds":
                continue
            sl = js.parent.name
            cid = f"{t}_{sl.split('_')[-3] if False else sl[:6]}_{sl.split('_')[1][:4]}{sl.split('_')[-1]}_{j['card_idx']:02d}"
            if only and j["card_idx"] != only:
                continue
            wav = str(ROOT / nas[sl]["wav"]); mp4 = js.with_suffix(".mp4"); S = np.load(cache_of(wav, ".scores.npy"))
            D[cid] = dict(tier=t, slug=sl, idx=j["card_idx"], mp4=str(mp4.relative_to(ROOT)), dur=j["clip_len"], fade=j["fade"], tail=round(j["vod_end"] - j["song_end"], 2), why=j.get("tier_why"),
                          code=j.get("code"), likely=j.get("likely"), signals=j.get("signals"), stages=[x for x in (j.get("stages") or []) if abs(x.get("shift", x.get("after", 0) - x.get("before", 0))) > 0.5] if j.get("stages") else None,
                          **diag(pcm_of(wav), S, j))
            cs, s, e, ce = j["vod_start"], j["song_start"], j["song_end"], j["vod_end"]
            fig = plt.figure(figsize=(17, 9.5)); gs = fig.add_gridspec(4, 6, height_ratios=[2.4, 2.6, 0.9, 0.9], hspace=0.35)
            with tempfile.TemporaryDirectory() as tmp:
                for k, tt in enumerate((min(3.0, j["clip_len"] / 4), j["clip_len"] / 2, j["clip_len"] - 2.0)):
                    ax = fig.add_subplot(gs[0, 2 * k:2 * k + 2]); ax.imshow(frame(mp4, tt, tmp)); ax.axis("off"); ax.set_title(f"clip {tt:.0f}s ({['start', 'mid', 'end'][k]})", fontsize=8)
            for k, (a, b, ti) in enumerate(((cs - 3, s + 12, "START window (cut / song)"), (e - 12, ce + 3, "END window (song / cut)"))):
                ax3 = [fig.add_subplot(gs[r, 3 * k:3 * k + 3]) for r in (1, 2, 3)]
                win(ax3, wav, S, a, b, [(cs, "cut"), (s, "song"), (e, "song"), (ce, "cut")], f"{cid} {ti}")
            fig.suptitle(f"{cid}  {js.stem}  len {j['clip_len']:.0f}s  {j.get('tier_why') or ''}", fontsize=9)
            fig.savefig(OUT / f"{cid}.png", dpi=62, bbox_inches="tight"); plt.close(fig)
            print(cid, flush=True)
    json.dump(D, open(dj, "w", encoding="utf8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    a = sys.argv[1:]
    run([x for x in a if x in DIRS] or list(DIRS), a[a.index("--slug") + 1] if "--slug" in a else None, int(a[a.index("--only") + 1]) if "--only" in a else None)
