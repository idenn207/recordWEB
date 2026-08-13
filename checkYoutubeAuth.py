import os
import sys
import json
import time
import shutil
import subprocess


def getProjectRoot() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def absPath(relPath: str) -> str:
    return os.path.normpath(os.path.join(getProjectRoot(), relPath))


def runCmd(cmd: list[str], timeoutSec: int = 90) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeoutSec,
        )
        return p.returncode, (p.stdout or ""), (p.stderr or "")

    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if hasattr(e, "stdout") else ""
        err = (e.stderr or "") if hasattr(e, "stderr") else ""
        return -999, out, err


def loadJson(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def loadPoToken(configPath: str) -> str:
    cfg = loadJson(configPath)
    return str(cfg.get("ytPoToken") or "").strip().strip('"').strip()


def prettyBool(v: bool) -> str:
    return "OK" if v else "FAIL"


def checkCookie(ytdlpPath: str, ycookiePath: str, testTarget: str) -> tuple[bool, str]:
    testTarget = (testTarget or "").strip()
    if not testTarget:
        return False, "테스트 URL이 비어있습니다."

    if not os.path.isfile(ycookiePath):
        return False, f"쿠키 파일이 없습니다: {ycookiePath}"

    # watch URL은 쿠키 없이도 성공할 수 있으니 경고를 미리 출력
    low = testTarget.lower()
    if ("watch?v=" in low) or ("youtu.be/" in low):
        print("[COOKIE] 주의: watch URL은 로그인 없이도 성공할 수 있어 쿠키 검증이 약할 수 있습니다.", flush=True)
        print("[COOKIE] 권장: :ytsubs://user/ 또는 https://www.youtube.com/feed/subscriptions", flush=True)

    cmd = [
        ytdlpPath,
        "--cookies", ycookiePath,
        "--flat-playlist",
        "--playlist-end", "1",
        testTarget,
        "-J",
        "--no-warnings",
        "--no-colors",
    ]

    rc, out, err = runCmd(cmd, timeoutSec=60)

    # stdout JSON 파싱 시도 (로그가 섞여도 최대한 JSON 부분만 추출)
    data = None
    if out:
        s = out.strip()
        try:
            data = json.loads(s)
        except Exception:
            try:
                a = s.find("{")
                b = s.rfind("}")
                if a != -1 and b != -1 and b > a:
                    data = json.loads(s[a:b+1])
            except Exception:
                data = None

    if rc == 0 and isinstance(data, dict):
        entries = data.get("entries")
        if isinstance(entries, list) and entries:
            e0 = entries[0] if isinstance(entries[0], dict) else {}
            title = (e0.get("title") or "").strip()
            vid = (e0.get("id") or "").strip()
            if title or vid:
                return True, f"접근 성공(JSON OK) - 샘플: {title} ({vid})"
        return True, "접근 성공(JSON OK)"

    hint = (err.strip() or out.strip() or f"exit code={rc}")
    return False, f"쿠키 실패/만료/차단 가능: {hint}"


def containsInvalidGvsToken(text: str) -> bool:
    t = (text or "").lower()
    return ("requires a gvs po token" in t) or ("provided is invalid" in t) or ("gvs po token" in t)


def containsDownloadStarted(text: str) -> bool:
    t = (text or "").lower()
    if "destination:" in t:
        return True
    if "[download]" in t and ("downloading" in t or "frag" in t or "fragment" in t):
        return True
    if "m3u8" in t and "downloading" in t:
        return True
    return False


def runCmdStreaming(cmd: list[str], timeoutSec: int = 35) -> tuple[int, str]:
    start = time.monotonic()
    lines: list[str] = []

    # stdout+stderr 합치기(Deadlock 방지)
    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        universal_newlines=True,
    )

    try:
        while True:
            now = time.monotonic()

            # 타임아웃
            if now - start > timeoutSec:
                try:
                    p.kill()
                except Exception:
                    pass
                return -999, "\n".join(lines)

            line = p.stdout.readline() if p.stdout else ""
            if line:
                line = line.rstrip("\n")
                lines.append(line)

                # 너무 스팸 안 나게 핵심 줄만 출력
                low = line.lower()
                if ("error:" in low) or ("warning:" in low) or ("[download]" in low) or ("destination:" in low):
                    print("[POTOKEN] " + line, flush=True)

                # invalid 즉시 종료
                if containsInvalidGvsToken(line):
                    try:
                        p.kill()
                    except Exception:
                        pass
                    return 1, "\n".join(lines)

                # 다운로드 시작 징후면 “유효”로 간주하고 즉시 종료
                if containsDownloadStarted(line):
                    try:
                        p.kill()
                    except Exception:
                        pass
                    return 0, "\n".join(lines)

            # 프로세스 종료 확인
            rc = p.poll()
            if rc is not None:
                # 남은 출력 조금 더 읽기
                rest = p.stdout.read() if p.stdout else ""
                if rest:
                    lines.append(rest)
                return rc, "\n".join(lines)

            time.sleep(0.05)
    finally:
        try:
            if p.stdout:
                p.stdout.close()
        except Exception:
            pass


def normalizeTokenCandidates(rawToken: str) -> list[tuple[str, str]]:
    t = (rawToken or "").strip().strip('"').strip()
    if not t:
        return []

    # 명시형(예: web.gvs+XXX / mweb.gvs+XXX / ... )
    if "+" in t and "." in t.split("+", 1)[0]:
        return [("explicit", t)]

    # raw 토큰 → 2가지 후보
    return [
        ("mweb.gvs", f"mweb.gvs+{t}"),
        ("web.gvs",  f"web.gvs+{t}"),
    ]


def probePoTokenOnce(
    ytdlpPath: str,
    ycookiePath: str,
    testUrl: str,
    poTokenValue: str,
    preferWebClient: bool,
    workDir: str
) -> tuple[bool, str]:

    extractorArgs = []
    if preferWebClient:
        extractorArgs.append("player-client=web")
        extractorArgs.append("formats=duplicate")
    else:
        extractorArgs.append("player-client=default,mweb")

    extractorArgs.append(f"po_token={poTokenValue}")

    outTmpl = "probe.%(ext)s"

    # ✅ 느려지는 원인 제거용 네트워크/재시도 옵션
    # --socket-timeout: 포기까지 기다리는 시간 :contentReference[oaicite:7]{index=7}
    # --fragment-retries: 조각 재시도 (기본 10) :contentReference[oaicite:8]{index=8}
    baseCmd = [
        ytdlpPath,
        "--cookies", ycookiePath,
        "--socket-timeout", "10",
        "--retries", "1",
        "--file-access-retries", "1",
        "--extractor-retries", "1",
        "--fragment-retries", "1",
        "--retry-sleep", "0",
        "--no-warnings",
        "--no-colors",
    ]

    cmd = baseCmd + [
        "--extractor-args", "youtube:" + ";".join(extractorArgs),

        # ✅ 검증은 "다운로드가 시작되는지"만 보면 되므로 1MB 제한
        "--max-filesize", "1M",
        "--no-continue",
        "--no-part",

        "--paths", f"home:{workDir}",
        "--paths", f"temp:{workDir}",
        "-o", outTmpl,

        # ✅ SABR 우선 (SABR 없으면 fallback)
        "-f", "bv[protocol=sabr]+ba[protocol=sabr]/bv*+ba/b",

        testUrl,
    ]

    rc, combined = runCmdStreaming(cmd, timeoutSec=35)

    if rc == -999:
        return False, "타임아웃(35초). 네트워크 지연/해당 URL이 SABR 검증에 부적합할 수 있음"

    if containsInvalidGvsToken(combined):
        return False, "GVS PO Token invalid(쿠키/토큰 불일치 또는 토큰 만료 가능성 높음)"

    if containsDownloadStarted(combined):
        return True, "프로브 다운로드 시작 확인(토큰 유효 가능성 높음)"

    # SABR 포맷이 없는 URL이면 확정이 어려움
    if "requested format is not available" in (combined or "").lower():
        return False, "확정 불가: 이 URL에서 SABR 포맷을 못 찾음(라이브 중인 다른 URL로 재시도 권장)"

    if rc == 0:
        return True, "yt-dlp 정상 종료(토큰 유효 가능성 높음)"

    tail = combined[-600:] if combined and len(combined) > 600 else (combined or "")
    return False, f"실패/확정 불가: exit={rc}\n{tail}"


def probePoToken(
    ytdlpPath: str,
    ycookiePath: str,
    rawToken: str,
    testUrl: str
) -> None:
    candidates = normalizeTokenCandidates(rawToken)
    if not candidates:
        print("[POTOKEN] ytPoToken이 비어있습니다.")
        return

    workDir = absPath(r"_ytdlp_probe_tmp")
    os.makedirs(workDir, exist_ok=True)

    try:
        for label, poValue in candidates:
            # explicit이면 내부 label에 web/mweb 여부를 추론
            preferWeb = False
            if label == "explicit":
                left = poValue.split("+", 1)[0].strip().lower()
                preferWeb = left.startswith("web.")
            else:
                preferWeb = (label.startswith("web."))

            ok, msg = probePoTokenOnce(
                ytdlpPath=ytdlpPath,
                ycookiePath=ycookiePath,
                testUrl=testUrl,
                poTokenValue=poValue,
                preferWebClient=preferWeb,
                workDir=workDir
            )

            print(f"[POTOKEN:{label}] {prettyBool(ok)} - {msg}")
            if ok:
                # 하나라도 OK면 추가 테스트는 선택사항
                pass
    finally:
        try:
            shutil.rmtree(workDir, ignore_errors=True)
        except Exception:
            pass


def prompt(msg: str) -> str:
    try:
        return input(msg).strip()
    except EOFError:
        return ""
    except KeyboardInterrupt:
        return ""


def printMenu() -> None:
    print("")
    print("========================================")
    print(" YouTube 쿠키 / PO토큰 상태 점검기")
    print(" (사용자가 종료하기 전까지 유지)")
    print("========================================")
    print(" 1) 쿠키 유효성 검사(테스트 URL 필요)")
    print(" 2) PO토큰 유효성 검사(테스트 URL 필요)")
    print(" 3) 쿠키 + PO토큰 모두 검사")
    print(" 0) 종료")
    print("")


def mainLoop() -> None:
    ytdlpPath   = absPath(r"dependent\yt-dlp\yt-dlp.exe")
    ycookiePath = absPath(r"json\ycookie.txt")
    configPath  = absPath(r"json\config.json")

    if not os.path.isfile(ytdlpPath):
        print(f"[FATAL] yt-dlp.exe 경로가 잘못되었습니다: {ytdlpPath}")
        print("Enter를 누르면 종료합니다.")
        input()
        return

    while True:
        printMenu()
        sel = prompt("선택> ").strip()

        if sel == "0":
            print("종료합니다.")
            return

        if sel not in ("1", "2", "3"):
            print("잘못된 선택입니다.")
            continue

        cookieOk = False

        if sel in ("1", "3"):
            cookieTest = ""
            while not cookieTest:
                cookieTest = prompt(
                    "쿠키 검사용 URL 입력(:ytsubs://user/ 또는 https://www.youtube.com/feed/subscriptions) 둘 중 하나를 그대로 입력> "
                ).strip()
                if not cookieTest:
                    print("[COOKIE] URL을 입력해야 합니다.")
            ok, msg = checkCookie(ytdlpPath, ycookiePath, cookieTest)
            cookieOk = ok
            print(f"[COOKIE] {prettyBool(ok)} - {msg}")

        # PO토큰 검사: 매번 새 URL을 입력(
        if sel in ("2", "3"):
            rawToken = loadPoToken(configPath)
            if not rawToken:
                print("[POTOKEN] config.json의 ytPoToken이 비어있습니다.")
            else:
                if sel == "3" and not cookieOk:
                    print("[POTOKEN] 쿠키가 유효하지 않아 PO토큰 검증을 건너뜁니다(쿠키 갱신 후 재시도 권장).")
                else:
                    testUrl = ""
                    while not testUrl:
                        testUrl = prompt(
                            "PO토큰 검사용 테스트 URL 입력(현재 라이브중인 유튜브 주소 youtube.com/watch?v=VIDEO ID) > "
                        ).strip()
                        if not testUrl:
                            print("[POTOKEN] URL을 입력해야 합니다.")
                    probePoToken(ytdlpPath, ycookiePath, rawToken, testUrl)

        print("")
        print("계속하려면 Enter, 종료하려면 0 입력 후 Enter")
        x = prompt("> ").strip()
        if x == "0":
            print("종료합니다.")
            return


if __name__ == "__main__":
    try:
        mainLoop()
    except KeyboardInterrupt:
        print("\n사용자 중지(Ctrl+C). 종료합니다.")
