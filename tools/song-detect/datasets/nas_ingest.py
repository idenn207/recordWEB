"""NAS(파일 API) 10월 녹화 -> data/vod/nas/<슬러그>.wav(16kHz mono) -> pipeline.py -> out/<슬러그>. 재개 가능(파일 기준).
사용: python datasets/nas_ingest.py index            목록 선택 + 길이 확인 + legacy wav 재사용 판단 -> data/nas_index.json
      python datasets/nas_ingest.py run [수집수=3] [탐지수=2]   수집(영상 비저장, 오디오만 스트림)과 탐지를 파이프라인으로 병행
      python datasets/nas_ingest.py summary         cache/nas_summary.json
      python datasets/nas_ingest.py selftest
shortcut: 'fixed_' 접두 파일만 사용(접두 없는 사본은 같은 방송의 미완성본), 길이는 TS 헤더 추정치(+-수 초), 카테고리는 제목 키워드 추정."""
import json, os, queue, re, subprocess, sys, threading, time, urllib.parse, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import limits

ROOT = Path(__file__).resolve().parent.parent
API = "http://192.168.0.10:5080/api/files"
IDX, NASDIR, FAIL = ROOT / "data/nas_index.json", ROOT / "data/vod/nas", ROOT / "cache/nas_fail.json"
STREAMERS = {"아카네 리제": "rize", "하나코 나나": "nana", "시즈키 토아": "toa", "코가네 랑": "rang", "토키노 메리": "mary", "하나요 히요리": "hiyori"}
NIN = 3             # 동시 수집 수(run 이 정한다): NAS LAN 읽기 총량 = limits.net_MBps("lan") 를 수집마다 나눠 ffmpeg -readrate 로 제한
LOW = 0x4000          # BELOW_NORMAL_PRIORITY_CLASS (윈도우 nice)


def url_of(path):
    return f"{API}/download?path={urllib.parse.quote(path, safe='')}"


def parse(name):
    """'fixed_[2026-10-24] 시즈키 토아 제목 1080p60 (1).ts' -> (날짜, 스트리머, 제목, 변형 번호)"""
    m = re.match(r"(?:fixed_)?\[(\d{4}-\d{2}-\d{2})\] (\S+ \S+) (.*?) 1080p60(?: \((\d+)\))?\.ts$", name)
    return (m[1], m[2], m[3], int(m[4] or 0)) if m else None


def duration(src):
    r = subprocess.run(["ffprobe", "-v", "error", "-rw_timeout", "20000000", "-show_entries", "format=duration", "-of", "csv=p=0", str(src)], capture_output=True, text=True)
    return float(r.stdout.strip())


def select(items):
    out = []
    for i in items:
        p = parse(i["name"])
        if p and i["name"].startswith("fixed_") and not i["locked"] and i["size"] >= 5e8 and "2026-10-01" <= p[0] <= "2026-10-24" and p[1] in STREAMERS:
            out.append((i, p))
    out.sort(key=lambda x: (x[1][0], x[1][1], x[1][3], x[0]["name"]))
    n, rows = {}, []
    for i, (d, who, title, var) in out:
        n[d, who] = n.get((d, who), 0) + 1
        rows.append(dict(slug=f"{d}_{STREAMERS[who]}_{n[d, who]}", name=i["name"], path=i["path"], streamer=who, date=d, title=title, size=i["size"], locked=i["locked"], variant=var))
    return rows


def index():
    items = json.load(urllib.request.urlopen(f"{API}/ls?path={urllib.parse.quote('/app/chzzk', safe='')}"))["items"]
    rows = select(items)
    old = {r["slug"]: r for r in json.load(open(IDX, encoding="utf8"))} if IDX.exists() else {}
    legacy = {f: duration(f) for f in (ROOT / "data/vod/legacy").glob("2026-10-*.wav")}
    for r in rows:
        r["dur"] = old.get(r["slug"], {}).get("dur") or duration(url_of(r["path"]))
        # 재사용: 같은 날짜 legacy wav 중 길이가 3초 이내로 같은 것(이름만으로는 스트리머가 불명확한 파일이 있어 길이로 확인)
        r["reuse"] = next((f.name for f, d in legacy.items() if f.name.startswith(r["date"]) and abs(d - r["dur"]) < 3), None)
        r["wav"] = str(NASDIR / f"{r['slug']}.wav")
    NASDIR.mkdir(parents=True, exist_ok=True)
    IDX.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf8")
    print(len(rows), "방송", round(sum(r["size"] for r in rows) / 1e9), "GB", round(sum(r["dur"] for r in rows) / 3600), "시간", sum(bool(r["reuse"]) for r in rows), "개 재사용")


def ingest(r):
    wav = Path(r["wav"])
    if wav.exists():
        return
    if r.get("reuse"):
        os.link(ROOT / "data/vod/legacy" / r["reuse"], wav)          # 같은 드라이브 하드링크: 용량 0
        return
    part = wav.with_suffix(".part.wav")
    rr = limits.net_MBps("lan") / NIN / (r["size"] / r["dur"] / 1e6)     # 입력 길이 대비 읽기 배속 = (MB/s 예산) / (원본 비트레이트 MB/s)
    cmd = ["ffmpeg", "-v", "error", "-y", "-threads", "2", "-readrate", f"{rr:.1f}", "-rw_timeout", "60000000", "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "10", "-i", url_of(r["path"]),
           "-vn", "-ac", "1", "-ar", "16000", "-af", "aresample=async=1:first_pts=0", "-c:a", "pcm_s16le", str(part)]
    p = subprocess.run(cmd, capture_output=True, text=True, creationflags=LOW)
    got = (part.stat().st_size - 44) / 32000 if part.exists() else 0
    if p.returncode or abs(got - r["dur"]) > 30:                      # 길이가 크게 다르면 끊긴 수집
        raise RuntimeError(f"수집 실패 rc={p.returncode} 길이 {got:.0f}/{r['dur']:.0f}s {p.stderr[-300:]}")
    part.replace(wav)


def pipe(r):
    cmd = [sys.executable, "pipeline.py", r["wav"], "--id", r["slug"], "--name", r["streamer"], "--video", url_of(r["path"])]
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=28800, creationflags=LOW)
    if p.returncode:
        raise RuntimeError(f"pipeline rc={p.returncode} {(p.stdout + p.stderr)[-500:]}")


def run(nin=3, ngpu=2):
    global NIN
    NIN = nin
    rows = json.load(open(IDX, encoding="utf8"))
    done = ROOT / "cache/nas_done"
    done.mkdir(parents=True, exist_ok=True)
    qi, qg, lock = queue.Queue(), queue.Queue(), threading.Lock()
    fails = json.load(open(FAIL, encoding="utf8")) if FAIL.exists() else {}
    for r in sorted((r for r in rows if not (done / r["slug"]).exists()), key=lambda r: r["size"]):    # 작은 것부터: 결과가 일찍 나온다
        qi.put(r)

    def log(*a):
        print(time.strftime("%H:%M:%S"), *a, flush=True)

    def fail(r, e):
        with lock:
            fails[r["slug"]] = str(e)
            FAIL.write_text(json.dumps(fails, ensure_ascii=False, indent=1), encoding="utf8")
        log("실패", r["slug"], str(e)[:200])

    def wi():
        while True:
            try:
                r = qi.get_nowait()
            except queue.Empty:
                return
            t = time.time()
            for k in range(2):                                        # 네트워크 일시 오류 1회 재시도
                try:
                    ingest(r)
                    r["ingest_sec"] = round(time.time() - t)
                    log("수집", r["slug"], r["ingest_sec"], "s")
                    qg.put(r)
                    break
                except Exception as e:
                    if k:
                        fail(r, e)

    def wg():
        while True:
            r = qg.get()
            if r is None:
                return
            t = time.time()
            try:
                pipe(r)
                r["pipe_sec"] = round(time.time() - t)
                (done / r["slug"]).write_text(json.dumps(dict(ingest_sec=r.get("ingest_sec"), pipe_sec=r["pipe_sec"])))
                log("탐지", r["slug"], r["pipe_sec"], "s")
            except Exception as e:
                fail(r, e)

    ti = [threading.Thread(target=wi) for _ in range(nin)]
    tg = [threading.Thread(target=wg) for _ in range(ngpu)]
    for t in ti + tg:
        t.start()
    for t in ti:
        t.join()
    for _ in tg:
        qg.put(None)
    for t in tg:
        t.join()
    log("끝", "실패", len(fails))


def category(title):
    if re.search(r"노래|플리|가창|커버|라이브|노추|뮤직|가요", title):
        return "song"
    if re.search(r"롤|마크|마인|봉누도|아크|레이더스|디비휴|디비전|겟투워크|패들|게임|스팀|발로|캐리|큐|벌칙|공겜|합방", title):
        return "game"
    return "talk"


def summary():
    rows = json.load(open(IDX, encoding="utf8"))
    fails = json.load(open(FAIL, encoding="utf8")) if FAIL.exists() else {}
    out, tot = {}, dict(auto=0, review=0, drop=0, optional=0)
    for r in rows:
        done = ROOT / "cache/nas_done" / r["slug"]
        if not done.exists():
            continue
        cs = [json.load(open(c, encoding="utf8")) for c in sorted((ROOT / "out" / r["slug"] / "cards").glob("*.json"))]
        cnt = {t: sum(c["tier"] == t for c in cs) for t in tot}
        for t in tot:
            tot[t] += cnt[t]
        out[r["slug"]] = dict(streamer=r["streamer"], date=r["date"], title=r["title"], dur=r["dur"], category=category(r["title"]), tiers=cnt, timing=json.load(open(done)),
                              cands=[dict(idx=c["idx"], start=c["start"], end=c["end"], len=c["len"], tier=c["tier"], likely=c.get("likely", False), why=c["tier_why"], clip=c["clip"]) for c in cs])
    d = dict(total=tot, n_done=len(out), n_total=len(rows), failed=fails, bytes_wav=sum(f.stat().st_size for f in NASDIR.glob("*.wav")), broadcasts=out)
    (ROOT / "cache/nas_summary.json").write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf8")
    print(tot, "처리", len(out), "/", len(rows), "실패", len(fails))


def selftest():
    assert parse("fixed_[2026-10-21] 코가네 랑 벌을 달게 받겠습니다. 1080p60 (1).ts") == ("2026-10-21", "코가네 랑", "벌을 달게 받겠습니다.", 1)
    assert parse("[2026-10-25] 시즈키 토아 벌칙 1080p60.ts")[3] == 0
    mk = lambda s, n, b: dict(name=f"fixed_[2026-10-24] 시즈키 토아 a 1080p60{s}.ts", path="/x", size=b, locked=False)
    rows = select([mk("", 0, 9e8), mk(" (1)", 0, 3e8), mk(" (2)", 0, 2e9), dict(name="[2026-10-21] 시즈키 토아 b 1080p60.ts", path="/y", size=9e9, locked=False)])
    assert [r["slug"] for r in rows] == ["2026-10-24_toa_1", "2026-10-24_toa_2"] and category("월간 노래 추천") == "song" and category("잡담") == "talk"
    print("selftest ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    {"index": index, "summary": summary, "selftest": selftest}.get(a[0], lambda: run(*map(int, a[1:])))()
