import os
import re
import sys
import json
import subprocess
from urllib.parse import urlparse, parse_qs


VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def getBaseDir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def getVideoId(userInput: str) -> str:
    s = (userInput or "").strip()

    if VIDEO_ID_RE.match(s):
        return s

    try:
        u = urlparse(s)
        host = (u.netloc or "").lower()
        path = u.path or ""

        if "youtu.be" in host:
            vid = path.strip("/").split("/")[0]
            if VIDEO_ID_RE.match(vid):
                return vid

        qs = parse_qs(u.query or "")
        vid = (qs.get("v", [""])[0] or "").strip()
        if VIDEO_ID_RE.match(vid):
            return vid

        m = re.search(r"/shorts/([A-Za-z0-9_-]{11})", path)
        if m:
            return m.group(1)

    except Exception:
        pass

    m = re.search(r"(?<![A-Za-z0-9_-])([A-Za-z0-9_-]{11})(?![A-Za-z0-9_-])", s)
    if m and VIDEO_ID_RE.match(m.group(1)):
        return m.group(1)

    return ""


def runBgutil(bgutilExe: str, videoId: str) -> str:
    proc = subprocess.run(
        [bgutilExe, "--content-binding", videoId],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.stdout or ""


def parsePoToken(raw: str) -> str:
    t = (raw or "").strip()

    try:
        obj = json.loads(t)
        if isinstance(obj, dict) and obj.get("poToken"):
            return str(obj["poToken"]).strip()
    except Exception:
        pass

    m = re.search(r'"poToken"\s*:\s*"([^"]+)"', raw or "")
    if m:
        return m.group(1).strip()

    lines = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
    if lines:
        last = lines[-1]
        if last != "}":
            return last

    return ""


def promptInput(msg: str) -> str:
    try:
        return input(msg).strip()
    except EOFError:
        return ""
    except KeyboardInterrupt:
        return "q"


def mainLoop() -> int:
    base = getBaseDir()
    bgutilExe = os.path.join(base, "dependent", "bgutil-pot", "bgutil-pot-windows-x86_64.exe")

    if not os.path.isfile(bgutilExe):
        print("[ERROR] bgutil-pot 실행파일이 없습니다(autoInstall 재실행 권장):")
        print(f"        {bgutilExe}")
        print("Enter를 누르면 종료합니다.")
        input()
        return 1

    print("========================================")
    print(" 유튜브 PO 토큰 추출기")
    print(" ※ 반드시 유튜브 쿠키값과 동일한 ID로 로그인한 상태에서 추출하세요")        
    print(" 종료: q 입력")
    print("========================================")

    # 첫 입력(인자) 처리 후에도 계속 루프 유지
    first = ""
    if len(sys.argv) >= 2:
        first = str(sys.argv[1] or "").strip()

    while True:
        if first:
            userInput = first
            first = ""
        else:
            userInput = promptInput("YouTube URL 또는 Video ID(11글자) 입력 > ")

        if not userInput:
            continue

        if userInput.lower() in ("q", "quit", "exit"):
            print("종료합니다.")
            return 0

        videoId = getVideoId(userInput)
        if not videoId:
            print("[ERROR] Video ID 추출 실패")
            print(f"        입력값: {userInput}")
            continue

        print(f"[INFO] Video ID = {videoId}")
        print("[INFO] bgutil-pot로 PO 토큰 생성 중...")

        raw = runBgutil(bgutilExe, videoId)
        token = parsePoToken(raw)

        if not token:
            print("[ERROR] poToken 추출 실패")
            # 파일 저장은 안 하지만, 문제 분석용으로 마지막 몇 줄만 보여줌
            tail = "\n".join([ln for ln in (raw or "").splitlines() if ln.strip()][-8:])
            if tail:
                print("----- bgutil 출력(마지막 일부) -----")
                print(tail)
                print("-----------------------------------")
            continue

        print("")
        print("===== PO TOKEN =====")
        print(token)
        print("====================")
        print("(PO TOKEN 값을 복사하여 쿠키관리 페이지에서 입력해주세요.)")
        print("")


if __name__ == "__main__":
    raise SystemExit(mainLoop())
