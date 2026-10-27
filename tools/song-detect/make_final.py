"""완성본 라이브 클립 제작기: pipeline 증거 카드(out/<id>/cards/*.json)의 최종 start/end 로 원본 영상(NAS URL 또는 로컬)에서 곡마다
  (a) 완성본 mp4  : 최종 start~end 재인코딩(프레임 정확), 시작은 페이드 없이 20ms 오디오 디클릭만, 끝은 곡 끝 이후 1.0~1.5초 오디오+비디오 페이드아웃(컷 >= 곡 끝+1.0초, 곡 소리는 깎지 않음, 리미터 없음: --limiter 또는 SONG_LIMITER=1 로 켬)
  (b) _ctx20.mp4  : 앞뒤 20초 맥락 포함(챕터 START/END 로 위치 표시)
  (c) .json       : 원본, 구간, tier, 근거, 경계 신호, 측정값(컷 오차, A/V 싱크), 곡 길이
파일명 YYMMDD_스트리머_HHMMSS-HHMMSS_곡길이.mp4 (시각 = 원본 녹화 파일 안의 위치). 출력 out/final/<YYMMDD_스트리머_id>/.
사용: python make_final.py <id> --src <URL|파일> [--wav data/vod/<id>.wav] [--off <초>] [--tiers auto,review,optional] [--only 1,3] [--out out/final] [--jobs 2] [--name 이름] [--date YYYY-MM-DD] [--likely] [--no-ctx] [--limiter]
  카드의 시각은 wav(치지직 VOD) 기준이다. --src 가 다른 녹화(NAS)면 오디오 상호상관으로 오프셋(VOD - 원본)을 3지점에서 재서 쓴다(--off 로 직접 지정 가능, 카드가 원본 기준이면 --off 0).
  멱등(json ok 이면 건너뜀), 실패 3회 재시도, 인코더는 h264_nvenc 우선 실패 시 libx264. HTTP 는 -ss 를 입력 앞에 둬서 곡 구간(+여유)만 읽는다.
  --likely: review 중 카드의 likely(route.mark_likely) 인 곡만(파일명 끝 '_likely미검증', 메타 tier=likely; 사람 검수 전). --no-ctx: _ctx20 맥락본을 만들지 않는다.
  python make_final.py selftest
shortcut: 카드/원본이 같은 방송이고 오프셋이 일정(드리프트 없음)하다고 본다(3지점 일치 검사로 확인, 어긋나면 중단). 영상 컷 시각은 -ss 정확 디코드(<=1프레임)에 맡기고 오디오 상호상관 + 스트림 시작 차로 간접 측정."""
import glob, hashlib, json, os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
SR, FADE, DECLICK, CTX, PRE = 16000, 1.5, 0.02, 20.0, 10.0      # FADE = 종료 페이드 최대 길이, 최소 여유는 TAIL
TAIL = 1.0                                                      # 종료 컷은 곡 끝보다 최소 이 만큼 뒤
LIMITER = os.environ.get("SONG_LIMITER") == "1" or "--limiter" in sys.argv      # 기본 꺼짐: alimiter 는 보컬 구간에서 음량을 눌러 펌핑(사용자 불만)
import limits
THREADS, READRATE = max(1, limits.cpu_cores() // 2), limits.net_MBps("lan") / 2 / 1.1    # 실측(2026-10-26): -readrate 는 1080p60 ts 에서 처리를 3배 느리게 했다(60초 클립 37초 -> 12.7초). 원본 비트레이트가 1MB/s 급이라 읽기량은 상한(100MB/s)보다 훨씬 작아 제거. shortcut: 동시 2작업 가정(--jobs 기본), 원본 최대 ~1.06MB/s(NAS 61개 실측)라서 배속 = (LAN 예산/작업수)/1.1; --jobs 를 올리면 같이 조정
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
    v = ["-c:v", "h264_nvenc", "-preset", "p3", "-rc", "vbr", "-cq", "23", "-b:v", br, "-maxrate", mr, "-bufsize", "20M"] if gpu else ["-c:v", "libx264", "-preset", "medium", "-crf", "21", "-maxrate", mr, "-bufsize", "20M"]
    # 출력 -ss 는 필터 뒤에서 잘라 fade 시각이 어긋난다(실측: 오디오 fade 가 10초 일찍 시작) -> 필터 안에서 trim 후 pts 를 0 으로 맞추고 fade
    rel = f"{t0 - s0:.4f}"
    vf = f"trim=start={rel},setpts=PTS-STARTPTS" + (f",{vf}" if vf else "") + (",scale=1280:720" if chap else "")   # 확인용(ctx20)은 720p
    af = f"atrim=start={rel},asetpts=PTS-STARTPTS" + (f",{af}" if af else "")
    cmd = ["ffmpeg", "-v", "error", "-y", "-threads", str(THREADS)] + (["-hwaccel", "cuda"] if gpu else []) + ["-ss", f"{s0:.3f}", "-i", src] + (["-i", chap] if chap else []) + ["-t", f"{t1 - t0:.3f}", "-map", "0:v:0", "-map", "0:a:0"]
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


RULE = "v4-faithful"     # 규칙 버전: 멱등 키(json.rule 이 다르면 다시 만든다). v3 = 음성 없음 폴백 + 출력 리미터, v4 = 원본 음량 유지(리미터 기본 꺼짐) + 종료 컷을 곡 끝 +1.0초 이상, 페이드는 곡 끝 이후에만
PAD_WIN, PAD_MIN, PAD_EDGE = 2.0, 0.3, 0.05      # 여유 탐색 창(초), 이보다 짧은 공백은 여유 없음, 공백 시작 뒤 앞소리 꼬리 제외(초)
CODE = [("새 채널", "NEW"), ("정지 화면", "IDLE"), ("장면 멀지만", "FAR"), ("장면 애매", "AMB"), ("짧음", "SHORT"), ("김", "LONG"), ("장면 거리를 못", "NOSCENE"), ("피아노", "PIANO"), ("승인 라이브지만", "BD")]


def code_of(why):
    return next((c for k, c in CODE if (why or "").startswith(k)), "ETC")


def gaps(pcm, a, ref, t0, t1, free=False):
    """[t0,t1) 0.1초 프레임 중 공백의 연속 구간 [(시작, 길이)]과 말소리(Speech>=0.3) 프레임 시각들.
    free=False: 무음(곡 중앙값보다 25dB 낮고 Speech<0.3, snap.quiet 기준). free=True: 음성 없음(Speech<0.3 이고 Singing<0.3, 배경음/MR 은 허용)."""
    from snap import rms_db, HOP, FR
    ts, db = rms_db(pcm, t0, t1)
    ix = [min(int(t / HOP), len(a) - 1) for t in ts]
    sp = a[ix, 1]
    q = (sp < 0.3) & ((a[ix, 0] < 0.3) if free else (db < ref - 25))
    G, i = [], 0
    while i < len(ts):
        j = i
        while j < len(ts) and q[j] == q[i]:
            j += 1
        if q[i]:
            G.append((float(ts[i]), (j - i) * FR))
        i = j
    return G, ts[sp >= 0.3]


def pick(pcm, a, ref, t0, t1, ok):
    """무음 공백 우선, 0.3초 이상이 없으면 음성 없음 공백으로 폴백. ok(공백, 말소리 시각들)가 후보 조건(말소리를 건너지 않음). (선택 공백|None, 종류, 후보 기록)"""
    for kind, free in (("quiet", False), ("free", True)):
        G, spk = gaps(pcm, a, ref, t0, t1, free)
        best = max((g for g in G if ok(g, spk)), key=lambda g: g[1], default=None)
        if best and best[1] >= PAD_MIN:
            return best, kind, [[round(x, 2), round(y, 2)] for x, y in G]
    return None, None, [[round(x, 2), round(y, 2)] for x, y in G]


def lead_pad(pcm, a, ref, s):
    """시작 여유: s 앞 PAD_WIN 초에서 마지막 말소리 뒤의 공백(무음 우선, 없으면 음성 없음) 중 가장 긴 것의 시작+PAD_EDGE 를 클립 시작으로(0.3초 미만이면 s). (시작, 기록)
    shortcut: 앞 곡 소리 조각은 말소리(Speech)와 음성 없음 판정의 Singing 으로만 가려낸다, MR 카운트인/숨소리는 곡 쪽 소리로 허용."""
    best, kind, G = pick(pcm, a, ref, s - PAD_WIN, s, lambda g, spk: g[0] > (float(spk.max()) if len(spk) else -1e9))
    cut = min(best[0] + PAD_EDGE, s) if best else s
    return cut, dict(gaps=G, chosen=[round(best[0], 2), round(best[1], 2)] if best else None, kind=kind, pad=round(s - cut, 2))


def trail_pad(pcm, a, ref, e):
    """종료 여유: e 뒤 PAD_WIN 초에서 첫 말소리 앞의 공백(무음 우선, 없으면 음성 없음) 중 가장 긴 것의 가운데를 종료점으로(0.3초 미만이면 e)."""
    best, kind, G = pick(pcm, a, ref, e, e + PAD_WIN, lambda g, spk: g[0] < (float(spk.min()) if len(spk) else 1e9))
    cut = e
    if best:
        cut = max(e, best[0] + max(PAD_EDGE, (best[1] - PAD_EDGE) / 2))
    return cut, dict(gaps=G, chosen=[round(best[0], 2), round(best[1], 2)] if best else None, kind=kind, pad=round(cut - e, 2))


def stages_of(card, st):
    """카드의 snap 규칙 이동(boundary.stages, 없는 옛 카드는 빈 목록) + 컷 단계 이동 st. 원본 경계(refine)에서 컷까지 이동한 모든 초가 규칙 이름을 가진다."""
    return ((card.get("boundary") or {}).get("stages") or []) + st


def make(card, src, off, wav, slug_dir, name, date, enc_log, likely=False, no_ctx=False):
    s, e, tier = card["start"], card["end"], card["tier"]
    pcm = a = None
    adj, lead, trail = [], dict(pad=0.0), dict(pad=0.0)
    st = []                                               # 카드 경계 -> 컷의 규칙별 이동(snap_quiet, lead_pad, trail_pad, tail)
    if wav:
        from paths import cache_of
        from snap import mv, pcm_of, rms_db
        pcm, a = pcm_of(wav), np.load(cache_of(wav, ".scores.npy"))
        ref = float(np.median(rms_db(pcm, s, e)[1]))
        s2, m1 = snap_quiet(pcm, a, s, ref)
        e2, m2 = snap_quiet(pcm, a, e, ref)
        adj = [("start", s, s2) if m1 else None, ("end", e, e2) if m2 else None]
        mv(st, "snap_quiet", "start", s, s2)
        mv(st, "snap_quiet", "end", e, e2)
        s, e = s2, e2
        cs, lead = lead_pad(pcm, a, ref, s)
        ce, trail = trail_pad(pcm, a, ref, e)
        mv(st, "lead_pad", "start", s, cs)
        mv(st, "trail_pad", "end", e, ce)
    else:
        cs, ce = s, e
    song_s, song_e = s, e                                 # 곡 자체 경계(여유 제외); 이후 s, e = 실제 컷
    if wav:
        mv(st, "tail", "end", ce, max(ce, song_e + TAIL))
    ce = max(ce, song_e + TAIL) if wav else ce        # 페이드는 곡 끝 이후 여유에서만 -> 컷을 곡 끝 +1.0초 이상으로(wav 없으면 카드 e 를 곡 끝으로 보고 그대로)
    s, e = cs, ce
    ns, ne = s - off, e - off
    dur = e - s
    sfx = f"_{'R' if tier == 'review' else 'O'}_{code_of(card.get('tier_why'))}" + ("-L" if card.get("likely") else "") if tier in ("review", "optional") else ""    # 등급 약어(R/O)+근거 코드, -L = likely 조건 통과
    base = f"{date[2:4]}{date[5:7]}{date[8:10]}_{name.replace(' ', '')}_{hms6(ns)}-{hms6(ne)}_{int(dur // 60)}m{int(dur % 60):02d}s{sfx}" + ("_likely미검증" if likely else "")
    mp4, ctx, js = (slug_dir / f"{base}{x}" for x in (".mp4", "_ctx20.mp4", ".json"))
    if js.exists() and (j0 := json.loads(js.read_text(encoding="utf8"))).get("ok") and j0.get("rule") == RULE and mp4.exists() and (no_ctx or ctx.exists()):
        return j0
    t_start = time.time()
    fade_st = song_e - s if wav else dur - TAIL       # 곡 끝에서 시작
    fade_d = min(FADE, dur - fade_st)                 # 곡 끝~컷 여유(>=1.0초) 안에서만
    assert fade_st >= 0 and fade_d >= TAIL - 1e-6 and fade_st + fade_d <= dur + 1e-6, (fade_st, fade_d, dur)
    vf = f"fade=t=out:st={fade_st:.3f}:d={fade_d:.3f}"
    af = f"afade=t=in:d={DECLICK},afade=t=out:st={fade_st:.3f}:d={fade_d:.3f}" + (",alimiter=limit=0.891:level=0" if LIMITER else "")      # 리미터는 옵션(-1dBFS, level=0 = 자동 음량 보정 끔)
    enc = encode(src, ns, ne, str(mp4), vf, af)
    c0, c1 = max(0.0, ns - CTX), ne + CTX
    ch = slug_dir / f"{base}.ffmeta"
    if not no_ctx:
        ch.write_text(f";FFMETADATA1\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND={int((ns - c0) * 1000)}\ntitle=앞 맥락\n[CHAPTER]\nTIMEBASE=1/1000\nSTART={int((ns - c0) * 1000)}\nEND={int((ne - c0) * 1000)}\ntitle=곡 (START~END)\n"
                      f"[CHAPTER]\nTIMEBASE=1/1000\nSTART={int((ne - c0) * 1000)}\nEND={int((c1 - c0) * 1000)}\ntitle=뒤 맥락\n", encoding="utf8")
        encode(src, c0, c1, str(ctx), chap=str(ch), br="2M", mr="3M")
        ch.unlink()
    m = check(mp4, dur, s, e, wav, fade_st)
    meta = dict(rule=RULE, src=str(src), card_idx=card["idx"], vod_start=s, vod_end=e, card_start=card["start"], card_end=card["end"], offset=off, src_start=ns, src_end=ne, song_len=song_e - song_s, clip_len=dur,
                song_start=song_s, song_end=song_e, lead=lead, trail=trail, tier="likely" if likely else tier, likely=card.get("likely"), code=code_of(card.get("tier_why")),
                tier_why=card.get("tier_why"), why=[x for x in adj if x], boundary=card.get("boundary"), stages=stages_of(card, st), signals=card.get("signals"), scene=card.get("scene"), multi=card.get("multi"),
                ctx_start_in_ctx=ns - c0, limiter=LIMITER, fade=[round(fade_st, 3), round(fade_d, 3)], encoder=enc, check=m, ok=m["ok"], files=dict(final=mp4.name, ctx20=None if no_ctx else ctx.name), note="likely, 미검증 (사람 검수 전, route.mark_likely 조건만 통과)" if likely else None)
    tmp = js.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf8")
    os.replace(tmp, js)                                   # 재생 중인 파일이 깨지지 않게 임시 이름으로 만든 뒤 교체(mp4 는 encode 가 .part.mp4 -> replace)
    pass  # 휴지 불필요: NVDEC+nvenc p3 는 GPU 사용률 30% 안팎(실측), 80% 상한 아래            # GPU(nvenc) 가동률 약 80%: 인코딩 시간의 25% 만큼 쉰다
    return meta


def check(mp4, dur, s, e, wav, fade_st):
    """깨짐/크기/길이/A-V 시작 차/프레임 수 + (wav 가 있으면) 컷 위치 오차: 출력 오디오 앞 8초/끝(페이드 시작 직전) 7초를 wav 에서 상호상관으로 찾아 요청 s/e 와 비교(초)."""
    p = probe(str(mp4))
    sh(["ffmpeg", "-v", "error", "-i", mp4, "-f", "null", "-"], retries=1)          # 디코드 오류가 있으면 stderr 로 실패
    r = dict(size=p["size"], dur=p["dur"], dur_err=p["dur"] - dur, av_start_diff=p["v0"] - p["a0"], frames=p["nb"], frames_exp=round(dur * 60), res=p["wh"], fps=p["fps"])
    r["ok"] = bool(p["size"] > 1e6 and abs(r["dur_err"]) < 0.1 and abs(r["av_start_diff"]) < 0.05 and abs(p["nb"] - r["frames_exp"]) <= 2 and p["wh"][1] >= 1080)
    if wav:
        from snap import pcm_of
        w = pcm_of(wav)
        x0, x1 = audio(str(mp4), 0.1, 8), audio(str(mp4), fade_st - 7, 7)    # 앞 0.1초는 디클릭 페이드 구간이라 제외
        for k, x, t in (("start_err", x0, s + 0.1), ("end_err", x1, s + fade_st - 7)):
            lo = t - 3
            i, q = xcorr(x, np.asarray(w[int(max(lo, 0) * SR):int((t + len(x) / SR + 3) * SR)], np.float32))
            r[k], r[k + "_q"] = max(lo, 0) + i / SR - t, q
        from snap import rms_db
        ref = float(np.median(rms_db(w, s, e)[1]))                                    # 컷 지점 음량(곡 중앙값 대비 dB): 시작 앞 0.2초, 페이드 직전 0.3초. 정보용(끝이 음악 한가운데면 페이드로 마무리됨)
        db = lambda v: float(20 * np.log10(np.sqrt((v ** 2).mean()) / 32768 + 1e-9))
        r["start_rel_db"], r["end_rel_db"] = db(audio(str(mp4), 0.02, 0.2)) - ref, db(x1[-int(0.3 * SR):]) - ref
        r["ok"] = r["ok"] and abs(r["start_err"]) <= 0.1 and abs(r["end_err"]) <= 0.1
    return r


def main(vid, src, wav, off, tiers, only, outroot, jobs, name, date, likely=False, no_ctx=False):
    os.chdir(ROOT)
    cards = [json.load(open(p, encoding="utf8")) for p in sorted(glob.glob(f"out/{vid}/cards/*.json"))]
    cards = [c for c in cards if c["tier"] in tiers and (not only or c["idx"] in only) and (not likely or c.get("likely")) and not (c["tier"] == "review" and c.get("weak"))]    # weak(움직임 25~34.5) review 는 만들지 않음
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
        for c, m in zip(cards, ex.map(lambda c: make(c, src, off, wav, d, name, date, None, likely, no_ctx), cards)):
            k = m["check"]
            print(f"  #{c['idx']:02d} {m['tier']:6s} {m['files']['final']} ok={m['ok']} dur_err={k['dur_err']:+.3f} av={k['av_start_diff']:+.3f} start_err={k.get('start_err', float('nan')):+.3f} end_err={k.get('end_err', float('nan')):+.3f}")
    return d


def selftest():
    x = np.random.default_rng(1).standard_normal(SR * 60).astype(np.float32)
    i, q = xcorr(x[SR * 20:SR * 28], x)
    assert i == SR * 20 and q > 50
    assert hms6(3725.4) == "010205"
    assert FADE >= TAIL >= 1.0 and RULE == "v4-faithful"
    assert stages_of({}, [1]) == [1] and stages_of({"boundary": {"stages": [0]}}, [1]) == [0, 1]
    print("selftest ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["selftest"]:
        selftest()
        sys.exit()
    opt = lambda k: a[a.index(k) + 1] if k in a else None
    only = {int(x) for x in opt("--only").split(",")} if opt("--only") else None
    main(a[0], opt("--src"), opt("--wav"), float(opt("--off")) if opt("--off") else None, (opt("--tiers") or ("review" if "--likely" in a else "auto")).split(","), only, opt("--out") or "out/final", int(opt("--jobs") or 2), opt("--name"), opt("--date"), "--likely" in a, "--no-ctx" in a)
