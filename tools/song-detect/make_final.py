"""완성본 라이브 클립 제작기: pipeline 증거 카드(out/<id>/cards/*.json)의 최종 start/end 로 원본 영상(NAS URL 또는 로컬)에서 곡마다
  (a) 완성본 mp4  : 최종 start~end 재인코딩(프레임 정확), 시작은 페이드 없이 20ms 오디오 디클릭만, 끝은 0.8초 오디오+비디오 페이드아웃
  (b) _ctx20.mp4  : 앞뒤 20초 맥락 포함(챕터 START/END 로 위치 표시)
  (c) .json       : 원본, 구간, tier, 근거, 경계 신호, 측정값(컷 오차, A/V 싱크), 곡 길이
파일명 YYMMDD_스트리머_HHMMSS-HHMMSS_곡길이.mp4 (시각 = 원본 녹화 파일 안의 위치). 출력 out/final/<YYMMDD_스트리머_id>/.
사용: python make_final.py <id> --src <URL|파일> [--wav data/vod/<id>.wav] [--off <초>] [--tiers auto,review,optional] [--only 1,3] [--out out/final] [--jobs 2] [--name 이름] [--date YYYY-MM-DD]
  카드의 시각은 wav(치지직 VOD) 기준이다. --src 가 다른 녹화(NAS)면 오디오 상호상관으로 오프셋(VOD - 원본)을 3지점에서 재서 쓴다(--off 로 직접 지정 가능, 카드가 원본 기준이면 --off 0).
  멱등(json ok 이면 건너뜀), 실패 3회 재시도, 인코더는 h264_nvenc 우선 실패 시 libx264. HTTP 는 -ss 를 입력 앞에 둬서 곡 구간(+여유)만 읽는다.
  python make_final.py selftest
shortcut: 카드/원본이 같은 방송이고 오프셋이 일정(드리프트 없음)하다고 본다(3지점 일치 검사로 확인, 어긋나면 중단). 영상 컷 시각은 -ss 정확 디코드(<=1프레임)에 맡기고 오디오 상호상관 + 스트림 시작 차로 간접 측정."""
import glob, hashlib, json, os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
SR, FADE, DECLICK, CTX, PRE = 16000, 0.8, 0.02, 20.0, 10.0
import limits
THREADS, READRATE = max(1, limits.cpu_cores() // 2), limits.net_MBps("lan") / 2 / 1.1    # shortcut: 동시 2작업 가정(--jobs 기본), 원본 최대 ~1.06MB/s(NAS 61개 실측)라서 배속 = (LAN 예산/작업수)/1.1; --jobs 를 올리면 같이 조정
LOW = 0x4000  # BELOW_NORMAL_PRIORITY_CLASS (Windows). 다른 OS 에서는 무시
_cf = dict(creationflags=LOW) if os.name == "nt" else {}


def sh(cmd, retries=3, text=True):
    for k in range(retries):
        r = subprocess.run([str(c) for c in cmd], capture_output=True, text=text, **_cf)
        if r.returncode == 0:
            return r
        time.sleep(2 * (k + 1))
    raise RuntimeError(f"실패 {retries}회: {' '.join(map(str, cmd))[:200]}\n{(r.stderr or '')[-600:]}")


def probe(path):
    j = json.loads(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=codec_type,start_time,nb_frames,width,height,r_frame_rate", "-of", "json", path]).stdout)
    s = {x["codec_type"]: x for x in j["streams"]}
    return dict(dur=float(j["format"]["duration"]), size=int(j["format"]["size"]), v0=float(s["video"]["start_time"]), a0=float(s["audio"]["start_time"]),
                nb=int(s["video"].get("nb_frames") or 0), wh=(s["video"]["width"], s["video"]["height"]), fps=s["video"]["r_frame_rate"])


def audio(src, t, d):
    """src 의 t초부터 d초 16kHz mono float32 (-ss 입력 앞: HTTP 에서 필요한 구간만 읽음)."""
    r = sh(["ffmpeg", "-v", "error", "-ss", f"{max(t, 0):.3f}", "-t", f"{d:.3f}", "-i", src, "-vn", "-ac", "1", "-ar", SR, "-f", "s16le", "-"], text=False)
    return np.frombuffer(r.stdout, "<i2").astype(np.float32)


def xcorr(x, ref):
    """ref 안에서 x 가 가장 닮은 위치(표본)와 피크/중앙값 비. 순수 파형 상관(같은 방송의 다른 인코딩이면 ms 이하로 맞는다)."""
    n = 1 << int(np.ceil(np.log2(len(ref) + len(x))))
    c = np.fft.irfft(np.fft.rfft(ref, n) * np.conj(np.fft.rfft(x, n)), n)[:len(ref) - len(x) + 1]
    i = int(c.argmax())
    return i, float(c[i] / (np.median(np.abs(c)) + 1e-9))


def offset(src, wav, win=300.0):
    """VOD(wav) 시각 - 원본(src) 시각. 3지점(15/50/85%)이 0.05초 안에서 일치하고 피크가 뚜렷해야 반환."""
    from snap import pcm_of
    w = pcm_of(wav)
    dur = float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src]).stdout)
    res = []
    for f in (0.15, 0.5, 0.85):
        t = dur * f
        x = audio(src, t, 40)
        lo = max(0.0, t - win)
        i, q = xcorr(x, np.asarray(w[int(lo * SR):int((t + win + 40) * SR)], np.float32))
        res.append((lo + i / SR - t, q))
    offs = [r[0] for r in res]
    assert max(offs) - min(offs) < 0.05 and min(r[1] for r in res) > 30, f"오프셋 불일치/불확실(같은 방송이 아니거나 드리프트): {res}"
    return float(np.median(offs))


def hms6(t):
    return f"{int(t // 3600):02d}{int(t % 3600 // 60):02d}{int(t % 60):02d}"


def encode(src, t0, t1, out, vf=None, af=None, chap=None, gpu=True, br="8M", mr="10M"):
    """src 의 [t0,t1] 를 프레임 정확하게 재인코딩. 입력 -ss 로 PRE 초 앞까지 빠르게 점프(HTTP 는 그 구간부터만 읽음) 후 출력 -ss 로 정확 컷."""
    s0 = max(0.0, t0 - PRE)
    # 비트레이트 상한이 없으면 nvenc cq 가 원본(8Mbps)의 25배로 부풀어 오른다(실측 750MB/3분47초)
    v = ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "23", "-b:v", br, "-maxrate", mr, "-bufsize", "20M"] if gpu else ["-c:v", "libx264", "-preset", "medium", "-crf", "21", "-maxrate", mr, "-bufsize", "20M"]
    # 출력 -ss 는 필터 뒤에서 잘라 fade 시각이 어긋난다(실측: 오디오 fade 가 10초 일찍 시작) -> 필터 안에서 trim 후 pts 를 0 으로 맞추고 fade
    rel = f"{t0 - s0:.4f}"
    vf = f"trim=start={rel},setpts=PTS-STARTPTS" + (f",{vf}" if vf else "") + (",scale=1280:720" if chap else "")   # 확인용(ctx20)은 720p
    af = f"atrim=start={rel},asetpts=PTS-STARTPTS" + (f",{af}" if af else "")
    cmd = ["ffmpeg", "-v", "error", "-y", "-threads", str(THREADS)] + (["-readrate", f"{READRATE:.1f}"] if str(src).startswith("http") else []) + ["-ss", f"{s0:.3f}", "-i", src] + (["-i", chap] if chap else []) + ["-t", f"{t1 - t0:.3f}", "-map", "0:v:0", "-map", "0:a:0"]
    cmd += ["-vf", vf, "-af", af] + v + ["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-map_chapters", "1" if chap else "-1", "-movflags", "+faststart", out + ".part.mp4"]
    try:
        sh(cmd, retries=2)
    except RuntimeError:
        if not gpu:
            raise
        return encode(src, t0, t1, out, vf, af, chap, False, br, mr)
    os.replace(out + ".part.mp4", out)
    return "h264_nvenc" if gpu else "libx264"


def snap_quiet(pcm, a, t, ref):
    """컷 지점 t 가 무음이 아니면(곡 중앙값보다 25dB 낮지 않음) +-2초 안의 가장 가까운 무음(snap.quiet 기준)으로. (새 t, 이동 여부)"""
    from snap import quiet, rms_db
    if np.median(rms_db(pcm, t, t + 0.1)[1]) < ref - 25:
        return t, False
    q = quiet(pcm, a, ref, t - 2, t + 2)
    return (float(q[np.abs(q - t).argmin()]), True) if len(q) else (t, False)


def make(card, src, off, wav, slug_dir, name, date, enc_log):
    s, e, tier = card["start"], card["end"], card["tier"]
    pcm = a = None
    adj = []
    if wav:
        from paths import cache_of
        from snap import pcm_of, rms_db
        pcm, a = pcm_of(wav), np.load(cache_of(wav, ".scores.npy"))
        ref = float(np.median(rms_db(pcm, s, e)[1]))
        s2, m1 = snap_quiet(pcm, a, s, ref)
        e2, m2 = snap_quiet(pcm, a, e, ref)
        adj = [("start", s, s2) if m1 else None, ("end", e, e2) if m2 else None]
        s, e = s2, e2
    ns, ne = s - off, e - off
    dur = e - s
    base = f"{date[2:4]}{date[5:7]}{date[8:10]}_{name.replace(' ', '')}_{hms6(ns)}-{hms6(ne)}_{int(dur // 60)}m{int(dur % 60):02d}s"
    mp4, ctx, js = (slug_dir / f"{base}{x}" for x in (".mp4", "_ctx20.mp4", ".json"))
    if js.exists() and json.loads(js.read_text(encoding="utf8")).get("ok") and mp4.exists() and ctx.exists():
        return json.loads(js.read_text(encoding="utf8"))
    vf = f"fade=t=out:st={dur - FADE:.3f}:d={FADE}"
    af = f"afade=t=in:d={DECLICK},afade=t=out:st={dur - FADE:.3f}:d={FADE}"
    enc = encode(src, ns, ne, str(mp4), vf, af)
    c0, c1 = max(0.0, ns - CTX), ne + CTX
    ch = slug_dir / f"{base}.ffmeta"
    ch.write_text(f";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND={int((ns - c0) * 1000)}\ntitle=앞 맥락\n[CHAPTER]\nTIMEBASE=1/1000\nSTART={int((ns - c0) * 1000)}\nEND={int((ne - c0) * 1000)}\ntitle=곡 (START~END)\n"
                  f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={int((ne - c0) * 1000)}\nEND={int((c1 - c0) * 1000)}\ntitle=뒤 맥락\n", encoding="utf8")
    encode(src, c0, c1, str(ctx), chap=str(ch), br="2M", mr="3M")
    ch.unlink()
    m = check(mp4, dur, s, e, wav)
    meta = dict(src=str(src), card_idx=card["idx"], vod_start=s, vod_end=e, card_start=card["start"], card_end=card["end"], offset=off, src_start=ns, src_end=ne, song_len=dur, tier=tier,
                tier_why=card.get("tier_why"), why=[x for x in adj if x], boundary=card.get("boundary"), signals=card.get("signals"), scene=card.get("scene"), multi=card.get("multi"),
                ctx_start_in_ctx=ns - c0, encoder=enc, check=m, ok=m["ok"], files=dict(final=mp4.name, ctx20=ctx.name))
    js.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf8")
    return meta


def check(mp4, dur, s, e, wav):
    """깨짐/크기/길이/A-V 시작 차/프레임 수 + (wav 가 있으면) 컷 위치 오차: 출력 오디오 앞 8초/끝(페이드 직전) 7초를 wav 에서 상호상관으로 찾아 요청 s/e 와 비교(초)."""
    p = probe(str(mp4))
    sh(["ffmpeg", "-v", "error", "-i", mp4, "-f", "null", "-"], retries=1)          # 디코드 오류가 있으면 stderr 로 실패
    r = dict(size=p["size"], dur=p["dur"], dur_err=p["dur"] - dur, av_start_diff=p["v0"] - p["a0"], frames=p["nb"], frames_exp=round(dur * 60), res=p["wh"], fps=p["fps"])
    r["ok"] = bool(p["size"] > 1e6 and abs(r["dur_err"]) < 0.1 and abs(r["av_start_diff"]) < 0.05 and abs(p["nb"] - r["frames_exp"]) <= 2 and p["wh"][1] >= 1080)
    if wav:
        from snap import pcm_of
        w = pcm_of(wav)
        x0, x1 = audio(str(mp4), 0.1, 8), audio(str(mp4), p["dur"] - FADE - 7, 7)    # 앞 0.1초는 디클릭 페이드 구간이라 제외
        for k, x, t in (("start_err", x0, s + 0.1), ("end_err", x1, e - FADE - 7)):
            lo = t - 3
            i, q = xcorr(x, np.asarray(w[int(max(lo, 0) * SR):int((t + len(x) / SR + 3) * SR)], np.float32))
            r[k], r[k + "_q"] = max(lo, 0) + i / SR - t, q
        from snap import rms_db
        ref = float(np.median(rms_db(w, s, e)[1]))                                    # 컷 지점 음량(곡 중앙값 대비 dB): 시작 앞 0.2초, 페이드 직전 0.3초. 정보용(끝이 음악 한가운데면 페이드로 마무리됨)
        db = lambda v: float(20 * np.log10(np.sqrt((v ** 2).mean()) / 32768 + 1e-9))
        r["start_rel_db"], r["end_rel_db"] = db(audio(str(mp4), 0.02, 0.2)) - ref, db(x1[-int(0.3 * SR):]) - ref
        r["ok"] = r["ok"] and abs(r["start_err"]) <= 0.1 and abs(r["end_err"]) <= 0.1
    return r


def main(vid, src, wav, off, tiers, only, outroot, jobs, name, date):
    os.chdir(ROOT)
    cards = [json.load(open(p, encoding="utf8")) for p in sorted(glob.glob(f"out/{vid}/cards/*.json"))]
    cards = [c for c in cards if c["tier"] in tiers and (not only or c["idx"] in only)]
    wav = wav or (f"data/vod/{vid}.wav" if Path(f"data/vod/{vid}.wav").exists() else None)
    if name is None or date is None:
        v = next((v for p in glob.glob("data/vods*.json") for v in json.load(open(p, encoding="utf8")) if str(v["videoNo"]) == vid), {})
        name, date = name or v.get("name", "unknown"), date or v.get("date", "0000-00-00")
    if off is None:
        off = offset(src, wav) if wav else 0.0
    print(f"{vid} {name} {date} 카드 {len(cards)}개 오프셋(VOD-원본) {off:+.3f}s")
    d = Path(outroot) / f"{date[2:4]}{date[5:7]}{date[8:10]}_{name.replace(' ', '')}_{vid}"
    d.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(jobs) as ex:
        for c, m in zip(cards, ex.map(lambda c: make(c, src, off, wav, d, name, date, None), cards)):
            k = m["check"]
            print(f"  #{c['idx']:02d} {m['tier']:6s} {m['files']['final']} ok={m['ok']} dur_err={k['dur_err']:+.3f} av={k['av_start_diff']:+.3f} start_err={k.get('start_err', float('nan')):+.3f} end_err={k.get('end_err', float('nan')):+.3f}")
    return d


def selftest():
    x = np.random.default_rng(1).standard_normal(SR * 60).astype(np.float32)
    i, q = xcorr(x[SR * 20:SR * 28], x)
    assert i == SR * 20 and q > 50
    assert hms6(3725.4) == "010205"
    print("selftest ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["selftest"]:
        selftest()
        sys.exit()
    opt = lambda k: a[a.index(k) + 1] if k in a else None
    only = {int(x) for x in opt("--only").split(",")} if opt("--only") else None
    main(a[0], opt("--src"), opt("--wav"), float(opt("--off")) if opt("--off") else None, (opt("--tiers") or "auto").split(","), only, opt("--out") or "out/final", int(opt("--jobs") or 2), opt("--name"), opt("--date"))
