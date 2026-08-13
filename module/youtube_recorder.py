import os
import asyncio
import aiohttp
import json
import re
import shlex
import time
import unicodedata
import subprocess
import shutil
import contextlib
import psutil
import glob
from collections import deque
import signal
import errno
import sys
import hashlib
import math

if os.name == 'nt':
    import ctypes

from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from typing import Optional, Awaitable, Callable
from pathlib import Path

from module.data_manager import (
    RecorderManager, uniqueFilename, moveDirectory, sendTelegram, last_notified_state,
    base_directory, getFFmpeg, getYtDlp, getDeno, loadConfig, ysaveCookies, toBool
)


# RecorderManager 클래스 인스턴스 생성
recorder_manager = RecorderManager()

# 재탐색 지터 전역
START_MONO = time.monotonic()
JITTER_RATIO = float(os.environ.get("RECHECK_JITTER_RATIO", "0.15"))
_JITTER_PHASE = {}  # {channel_id: phase(sec)}

# 유니코드 정규화 후 ASCII로 변환 (불필요한 문자는 제거)
def sanitize_filename(s: str) -> str:
    normalized = unicodedata.normalize('NFKC', s)
    return re.sub(r'[\\/:*?"<>|\+\[\]【】「」『』]', '_', normalized)


# 유튜브 쿠키 검증 함수
def validateCookies(cookie_path: str | None, *, include_header: bool = False):
    try:
        if not cookie_path or not os.path.exists(cookie_path):
            return (False, '쿠키 파일이 존재하지 않습니다.') if not include_header else (False, '쿠키 파일이 존재하지 않습니다.', None)

        required_cookies = ['SAPISID', '__Secure-3PSID', '__Secure-3PAPISID']

        with open(cookie_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        parsed = {}
        cookie_pairs = []  # header 만들 때 사용
        names_to_take = {
            'SAPISID','__Secure-3PSID','__Secure-3PAPISID',
            'HSID','SSID','APISID','SID','SIDCC','PAPISID',
            'CONSENT','YSC','VISITOR_INFO1_LIVE'
        }

        for line in lines:
            if not line.strip() or line.startswith('#'):
                continue
            # Netscape: domain, flag, path, secure, expires, name, value
            parts = line.strip().split('\t')
            if len(parts) >= 7:
                domain, _, _, _, _, name, value = parts[:7]
                parsed[name] = value
                if ('youtube.com' in domain or 'google.com' in domain) and (name in names_to_take or name.startswith('__Secure-')):
                    cookie_pairs.append(f"{name}={value}")

        missing = [k for k in required_cookies if k not in parsed]
        ok = not missing
        msg = '쿠키가 올바르게 설정되었습니다.' if ok else f"다음 쿠키들이 누락되었습니다: {', '.join(missing)}"

        if include_header:
            header = "; ".join(cookie_pairs) if cookie_pairs else None
            return ok, msg, header
        else:
            return ok, msg

    except Exception as e:
        print(f"쿠키 검증 중 오류 발생: {e}")
        return (False, '쿠키 검증 중 오류 발생') if not include_header else (False, '쿠키 검증 중 오류 발생', None)


#  SIGINT / CTRL-C 전송 함수
def sendInterrupt(proc: subprocess.Popen):
    if os.name == 'nt':
        try:
            # 현재 프로세스는 Ctrl 시그널 무시
            try:
                ctypes.windll.kernel32.SetConsoleCtrlHandler(None, True)
            except Exception:
                pass
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        except ValueError:
            ctypes.windll.kernel32.GenerateConsoleCtrlEvent(1, proc.pid)
        finally:
            # 다시 원복
            try:
                ctypes.windll.kernel32.SetConsoleCtrlHandler(None, False)
            except Exception:
                pass
    else:
        os.killpg(os.getpgid(proc.pid), signal.SIGINT)


# 품질별 프레임 추출 함수
def extractFps(data):
    fps_values = []
    streaming_data = data.get("streamingData", {})
    adaptive_formats = streaming_data.get("adaptiveFormats", [])
    for fmt in adaptive_formats:
        fps = fmt.get("fps")
        if fps:
            fps_values.append(fps)
    if fps_values:
        return max(fps_values)
    return None


# 최대 해상도 높이(px) 추출
def extractResolution(data):
    heights = []
    streaming_data = data.get("streamingData", {})
    adaptive_formats = streaming_data.get("adaptiveFormats", [])
    for fmt in adaptive_formats:
        if "video/" in (fmt.get("mimeType") or ""):
            h = fmt.get("height")
            if isinstance(h, int):
                heights.append(h)
            else:
                # qualityLabel: "1080p60" 등인 경우 파싱
                ql = fmt.get("qualityLabel") or ""
                m = re.match(r"^(\d+)p", ql)
                if m and m.group(1).isdigit():
                    heights.append(int(m.group(1)))
    return max(heights) if heights else None



# 기본 메타데이터 반환 함수
def default_metadata():
    return {
        'is_live': False,
        'video_id': None,
        'channel_name': 'Unknown Channel',
        'live_title': '정보 없음',
        'thumbnail_url': '/static/img/youtube_thumbnail.png', 
        'category': '카테고리 없음',
        'record_quality': 'best',
        'resolution': 'Unknown', 
        'frame_rate': 'Unknown', 
        'adult': False,
        'start_time': None, 
        'dash_manifest_url': None, 
    }


# 유튜브 라이브 메타데이터 가져오기
async def getYoutubeMetadata(channel, ycookie_path=None):
    def _default_meta():
        try:
            d = default_metadata()
        except Exception:
            d = {
                "platform": "youtube",
                "id": channel.get("id", "unknown"),
                "is_live": False,
                "live_title": "정보 없음",
                "category": "정보 없음",
                "thumbnail_url": "/static/img/youtube_thumbnail.png",
                "watch_url": None,
                "video_id": None,
                "scheduled_start_time_dt": None,
            }
        # 보강 필드
        d.setdefault("is_live_now", False)
        return d

    try:
        platform = "youtube"
        cid = channel.get("id", "").strip() or "unknown"

        # 1) 채널 LIVE URL (핸들/채널ID 모두 대응)
        ident = cid
        if ident.startswith("UC"):
            live_url = f"https://www.youtube.com/channel/{ident}/live"
        elif ident.startswith("@"):
            live_url = f"https://www.youtube.com/{ident}/live"
        else:
            live_url = f"https://www.youtube.com/@{ident}/live"

        # 2) 쿠키 준비
        ok_cookie, _, cookie_header = (
            validateCookies(ycookie_path, include_header=True) if ycookie_path
            else (False, "", None)
        )

        async def _fetch(url: str, with_cookie: bool):
            client_timeout = aiohttp.ClientTimeout(total=10.0, connect=5.0)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            }
            if with_cookie and cookie_header:
                headers["Cookie"] = cookie_header

            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                async with session.get(url, headers=headers, allow_redirects=True) as resp:
                    html = await resp.text()
                    final_url = str(resp.url)
                    return html, final_url

        # (a) 쿠키 → (b) 비쿠키
        html, final_url = None, None
        if ok_cookie and cookie_header:
            try:
                html, final_url = await _fetch(live_url, True)
            except asyncio.TimeoutError:
                html, final_url = None, None
        if html is None:
            try:
                html, final_url = await _fetch(live_url, False)
            except asyncio.TimeoutError:
                html, final_url = None, None

        if not html:
            return _default_meta()

        # 3) player JSON 추출
        def _extract_player_json(page_html: str):
            patterns = [
                r'ytInitialPlayerResponse\s*=\s*({.*?});',
                r'"ytInitialPlayerResponse"\s*:\s*({.*?})\s*,\s*"(?:ytInitialData|INNERTUBE)',
            ]
            for pat in patterns:
                m = re.search(pat, page_html, re.S)
                if m:
                    try:
                        return json.loads(m.group(1))
                    except Exception:
                        continue
            return None

        player = _extract_player_json(html)

        # 4) videoId 탐색
        video_id = None
        if isinstance(player, dict):
            video_id = ((player.get("videoDetails") or {}).get("videoId")) or None
        if not video_id:
            mv = re.search(r'"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"', html)
            if mv:
                video_id = mv.group(1)
        if not video_id and final_url and "/watch" in final_url:

            try:
                qs = parse_qs(urlparse(final_url).query)
                video_id = (qs.get("v") or [None])[0]
            except Exception:
                pass

        # 5) 메타 필드 채우기
        is_live = False
        is_live_now = False
        live_title = "정보 없음"
        category = "정보 없음"
        scheduled_dt = None
        watch_url = f"https://www.youtube.com/watch?v={video_id}" if video_id else None
        thumb = (f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id
                 else "/static/img/youtube_thumbnail.png")

        if isinstance(player, dict):
            vd = player.get("videoDetails") or {}
            micro = (player.get("microformat") or {}).get("playerMicroformatRenderer") or {}
            lb = micro.get("liveBroadcastDetails") or {}
            ps = (player.get("playabilityStatus") or {})
            status_val = (ps.get("status") or "").upper()

            # 제목/카테고리
            live_title = (vd.get("title")
                          or (micro.get("title") or {}).get("simpleText")
                          or "정보 없음")
            category = (micro.get("category") or vd.get("category") or "정보 없음")

            # 라이브 판정(엄격)
            is_live_now = bool(lb.get("isLiveNow"))
            if status_val == "LIVE_STREAM_OFFLINE":
                is_live_now = False

            # 라이브 판정(더 엄격): "진짜 라이브 중(isLiveNow=True)"만 녹화 시작 대상으로 인정
            # - 종종 '종료/처리중' 상태에서도 playabilityStatus=OK 가 나와 오인을 유발함
            # - endTimestamp가 잡히면 이미 종료된 것으로 보고 False 처리
            end_ts = lb.get("endTimestamp")
            if end_ts:
                is_live_now = False

            is_live = bool(is_live_now)

            # 예정/시작 시간
            ts = lb.get("startTimestamp") or lb.get("scheduledStartTime")
            if ts:
                try:
                    if isinstance(ts, str) and ts.endswith("Z"):
                        ts = ts[:-1] + "+00:00"
                    scheduled_dt = datetime.fromisoformat(ts) if isinstance(ts, str) else None
                except Exception:
                    scheduled_dt = None

        # 6) 최종 리턴
        fps_val = None
        res_val = None

        try:
            if isinstance(player, dict):
                fps_val = extractFps(player)
                res_val = extractResolution(player)
        except Exception:
            pass

        return {
            "platform": platform,
            "id": cid,
            "is_live": bool(is_live),
            "is_live_now": bool(is_live_now),
            "live_title": live_title or "정보 없음",
            "category": category or "정보 없음",
            "thumbnail_url": thumb or "/static/img/youtube_thumbnail.png",
            "watch_url": watch_url,
            "video_id": video_id,
            "scheduled_start_time_dt": scheduled_dt,
            "frame_rate": (int(fps_val) if isinstance(fps_val, int) else None),
            "resolution": (int(res_val) if isinstance(res_val, int) else None),
        }

    except Exception as e:
        print(f"[ERROR] getYoutubeMetadata exception: {e}")
        return _default_meta()


# 유튜브 녹화 명령 생성 함수
def buildCommand(channel, output_dir, quality, extension, metadata,
                 cookies_valid, filenamePattern=None, ycookie_path=None):
    try:
        if channel is None or metadata is None:
            print("[ERROR] 채널 또는 메타데이터가 없습니다.")
            return None, None, None, None

        # 출력 경로
        if not os.path.isabs(output_dir):
            output_dir = os.path.join(base_directory, output_dir)
        os.makedirs(output_dir, exist_ok=True)

        # 메타 요약
        is_live      = bool(metadata.get("is_live"))
        is_live_now  = bool(metadata.get("is_live_now"))
        video_id     = metadata.get("video_id")
        handle       = (channel.get("id") or "").strip()
        channel_id   = handle

        # 대상 URL 결정
        base_url = (metadata.get("watch_url") or "").strip() if isinstance(metadata.get("watch_url"), str) else ""
        if not base_url:
            if video_id:
                base_url = f"https://www.youtube.com/watch?v={video_id}"
            else:
                ident = handle
                if ident.startswith("UC"):
                    base_url = f"https://www.youtube.com/channel/{ident}/live"
                elif ident.startswith("@"):
                    base_url = f"https://www.youtube.com/{ident}/live"
                else:
                    base_url = f"https://www.youtube.com/@{ident}/live"

        # 파일명 패턴
        filenamePattern = filenamePattern or (
            "[{start_time}] {channel_name} {safe_live_title} {record_quality}{frame_rate}{file_extension}"
        )

        # 1) 날짜/시간 토큰 
        recording_time = datetime.now().strftime("%y%m%d_%H%M%S") 

        start_time_dt = None
        st_meta = metadata.get('start_time') or metadata.get('scheduled_start_time_dt')

        if isinstance(st_meta, datetime):
            start_time_dt = st_meta
        elif isinstance(st_meta, str):
            try:
                s = st_meta.replace('Z', '+00:00')
                start_time_dt = datetime.fromisoformat(s)
            except Exception:
                start_time_dt = None

        if not start_time_dt:
            start_time_dt = datetime.now()

        start_time = start_time_dt.strftime("%Y-%m-%d")  

        # 2) 채널/제목 정리
        channel_name = sanitize_filename(channel.get('name', 'Unknown Channel'))[:50]
        live_title = (metadata.get('live_title') or '녹화')

        # 개행/탭 → 공백, 앞뒤 공백 정리
        live_title = re.sub(r'[\r\n\t]+', ' ', live_title).strip()

        # 금지문자만 '공백'으로 치환 (언더바 쓰지 않음)
        safe_live_title = re.sub(r'[\\/*?:"<>|+]', ' ', live_title)

        # 다중 공백을 1칸으로 축약
        safe_live_title = re.sub(r'\s{2,}', ' ', safe_live_title).strip()

        # .format 충돌 방지용 중괄호 이스케이프 + 길이 제한
        safe_live_title = safe_live_title.replace('{', '{{').replace('}', '}}')[:55]


        # 3) 품질/프레임  (요청값 우선 → 파일명 오표기 방지)
        requested_q = (str(quality) or "best").lower()

        # 1) 기본: 요청 품질을 파일명에 반영
        m_req = re.match(r"^(\d+)p(?:60)?$", requested_q)
        if m_req:
            record_quality = f"{m_req.group(1)}p"
        else:
            record_quality = "best"  # best인 경우만 메타 보정 적용

        name_fps = 60 if requested_q.endswith("60") else 30

        # 2) 요청이 'best'일 때만 메타(실측)로 보정
        meta_fps = None
        try:
            mf = metadata.get("frame_rate")
            if mf not in (None, "Unknown", ""):
                meta_fps = int(mf)
        except Exception:
            meta_fps = None

        meta_res = 0
        try:
            mr = metadata.get("resolution")
            if mr not in (None, "Unknown", ""):
                meta_res = int(mr)
        except Exception:
            meta_res = 0

        if requested_q == "best":
            if meta_res > 0:
                record_quality = f"{meta_res}p"
            if meta_fps is not None:
                name_fps = 60 if meta_fps >= 59 else 30

        frame_rate_for_name = str(name_fps)


        # 3-1) 확장자 보강
        if requested_q == "best" and str(extension).lower() == ".mp4":
            try:
                res_hint = int(metadata.get("resolution") or 0)
            except Exception:
                res_hint = 0
            if res_hint > 1080:
                extension = ".mkv"

        if str(extension).lower() == ".mp4":
            extension = ".mkv"

        # 4) 최종 파일명/경로
        final_filename = filenamePattern.format(
            start_time=start_time,
            recording_time=recording_time,
            channel_name=channel_name,
            safe_live_title=safe_live_title,
            record_quality=record_quality,
            frame_rate=frame_rate_for_name,
            file_extension=extension
        )
        output_final_path = os.path.join(output_dir, final_filename)
        prefix_path = os.path.splitext(output_final_path)[0]

        # 파일 존재시 충돌 방지 (주의: os.path.exists("*.f*") 는 와일드카드가 동작하지 않음)
        collision = False

        # 최종파일 충돌만 검사
        if os.path.exists(prefix_path + extension):
            collision = True

        # yt-dlp 임시/조각(.f*, .part) 체크
        pp = glob.escape(prefix_path)

        if glob.glob(pp + ".f*"):
            collision = True
        if glob.glob(pp + "*.part"):
            collision = True

        if collision:
            suffix = datetime.now().strftime("%H%M%S")
            prefix_path += f"_{suffix}"
            output_final_path = prefix_path + extension

        # 5) PO 토큰(Proof-of-Origin) 로드
        ytPoToken = ""
        try:
            _cfg = loadConfig() or {}
            ytPoToken = str(_cfg.get("ytPoToken") or "").strip()
        except Exception:
            ytPoToken = ""

        # 6) yt-dlp 명령 구성
        safe_tmp_name = re.sub(r"[^0-9A-Za-z._-]+", "_", channel_id or "yt")
        tmp_dir = os.path.join(output_dir, "_ytdlp_tmp", safe_tmp_name)
        os.makedirs(tmp_dir, exist_ok=True)

        # yt-dlp는 확장자를 스스로 결정하므로 %(ext)s 템플릿을 사용
        out_template = os.path.basename(prefix_path) + ".%(ext)s"

        # SABR yt-dlp 배포본 감지
        ytSabrMode = False
        try:
            _cfg = loadConfig() or {}
            ytSabrMode = toBool(_cfg.get("ytSabrMode", False))
        except Exception:
            ytSabrMode = False

        try:
            ytdlp_dir = os.path.dirname(getYtDlp())
            if os.path.isdir(os.path.join(ytdlp_dir, "_internal")):
                ytSabrMode = True
        except Exception:
            pass

        # 품질 문자열 SABR 우선 선택 지원
        def _fmt_selector(q: str, prefer_sabr: bool = False) -> str:
            q = (q or "best").strip().lower()

            def _best_fallback() -> str:
                return "bv*+ba/b"

            # best
            if q in ("best", "highest"):
                if prefer_sabr:
                    return f"ba[protocol=sabr]+bv[protocol=sabr]/{_best_fallback()}"
                return _best_fallback()

            # 1080p60 같은 형태
            m = re.match(r"^(\d{3,4})p(\d{2})$", q)
            if m:
                h = int(m.group(1))
                fps = int(m.group(2))

                sel = f"bv*[height<={h}][fps<={fps}]+ba/b[height<={h}][fps<={fps}]"

                if prefer_sabr:
                    sel_sabr = f"bv*[protocol=sabr][height<={h}][fps<={fps}]+ba[protocol=sabr]"
                    return f"{sel_sabr}/{sel}/{_best_fallback()}"

                return f"{sel}/{_best_fallback()}"

            # 1080p 같은 형태
            m = re.match(r"^(\d{3,4})p$", q)
            if m:
                h = int(m.group(1))

                sel = f"bv*[height<={h}]+ba/b[height<={h}]"

                if prefer_sabr:
                    sel_sabr = f"bv*[protocol=sabr][height<={h}]+ba[protocol=sabr]"
                    return f"{sel_sabr}/{sel}/{_best_fallback()}"

                return f"{sel}/{_best_fallback()}"

            # 그 외는 best
            if prefer_sabr:
                return f"ba[protocol=sabr]+bv[protocol=sabr]/{_best_fallback()}"
            return _best_fallback()

        fmt = _fmt_selector(quality, prefer_sabr=ytSabrMode)

        yt_dlp_cmd = [
            getYtDlp(),
            "--ffmpeg-location", os.path.dirname(getFFmpeg()),
            "--live-from-start",
            "-f", fmt,
            "--merge-output-format", "mkv",
            "--paths", f"home:{output_dir}",
            "--paths", f"temp:{tmp_dir}",
            "-o", out_template,
            "--print", "after_move:__FINAL__:%(filepath)j",
            "--no-colors",
        ]

        # 쿠키
        if ycookie_path and os.path.isfile(ycookie_path):
            yt_dlp_cmd += ["--cookies", ycookie_path]

        # EJS/서명 계산용 JS 런타임(deno)
        deno_path = getDeno()
        if os.path.isfile(deno_path):
            yt_dlp_cmd += ["--js-runtimes", f"deno:{deno_path}"]

        def _normalize_po_token(raw: str) -> str:
            if not raw:
                return ""
            raw = str(raw).strip()
            if not raw:
                return ""

            # 쉼표/세미콜론으로 구분된 입력 허용
            parts = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]

            out: list[str] = []
            seen: set[str] = set()

            for p in parts:
                # 이미 "<client>.<scope>+<token>" 형태면 그대로
                head = p.split("+", 1)[0]
                if "+" in p and "." in head:
                    tok = p
                else:
                    # raw 토큰은 mweb.gvs로만 취급
                    tok = "mweb.gvs+" + p

                if tok not in seen:
                    out.append(tok)
                    seen.add(tok)

            return ",".join(out)

        extractor_args = []

        def _inferPoClientsFromToken(norm: str) -> list[str]:
            if not norm:
                return []
            clients = set()
            for t in [x.strip() for x in norm.split(",") if x.strip()]:
                head = t.split("+", 1)[0]          # "mweb.gvs"
                client = head.split(".", 1)[0]     # "mweb"
                if client:
                    clients.add(client)

            order = ["mweb", "web", "ios", "android", "tv"]
            out = [c for c in order if c in clients]
            # order 밖의 client도 혹시 있으면 뒤에 붙임
            for c in sorted(clients):
                if c not in out:
                    out.append(c)
            return out

        po_token_norm = _normalize_po_token(ytPoToken) if ytPoToken else ""
        po_clients = _inferPoClientsFromToken(po_token_norm)

        if not po_clients:
            player_clients = "default,mweb"
        else:
            if po_clients == ["web"]:
                player_clients = "web"
            else:
                player_clients = "default," + ",".join(po_clients)

        extractor_args.append(f"player-client={player_clients}")

        if ytSabrMode:
            extractor_args.append("formats=duplicate")

        if po_token_norm:
            extractor_args.append(f"po_token={po_token_norm}")

        yt_dlp_cmd += ["--extractor-args", "youtube:" + ";".join(extractor_args)]


        # 대기 옵션
        wait_args = []
        if wait_args:
            yt_dlp_cmd += wait_args

        if not base_url:
            raise RuntimeError("base_url is empty (video_id/watch_url missing)")
        yt_dlp_cmd.append(base_url)

        return yt_dlp_cmd, prefix_path, output_final_path, tmp_dir

    except Exception as e:
        print(f"[ERROR] buildCommand failed: {e}", flush=True)
        raise


# stdout 등 디버그 신호 읽기
async def readPipe(stream, channel_id: str, ch_name: str, final_q: Optional[asyncio.Queue] = None, cwd: Optional[str] = None,
                   expected_out: Optional[str] = None, on_final: Optional[Callable[[str], Awaitable[None]]] = None,):

    # 1) 병합/리먹스 시작 신호
    merge_start_pat = re.compile(
        r"(?:Download Finished|Muxing final file|Muxing to|\[Merger\] Merging formats into|\[Merger\] Remuxing video from)\b",
        re.I)
    # 2) 병합 완료 신호 최종 파일 경로 동반
    merge_done_pat  = re.compile(
        r"(?:Final file|Merged file is|Output file|Muxed to|\[Merger\] Merging formats into|\[Merger\] Remuxing video from)\s*:?\s+\"?(.+\.(?:mp4|mkv|ts|webm))\"?",
        re.I)

    buffer = ""
    while True:
        data = await stream.read(2048)
        if not data:
            break
        chunk = data.decode(errors='replace')
        print(f"[{ch_name}] {chunk}", end='')

        buffer += chunk
        *lines, buffer = buffer.splitlines(True)
        for ln in lines:
            line = ln.rstrip("\r\n")

            # 0) __FINAL__:%(filepath)j 파싱
            if line.startswith("__FINAL__:"):
                payload = line[len("__FINAL__:"):].strip()
                # %(filepath)j 이므로 JSON 문자열로 오는 게 정상
                try:
                    p = json.loads(payload)
                except Exception:
                    p = payload.strip().strip("'\"")

                path = p if os.path.isabs(p) else os.path.join(cwd or "", p)

                if final_q:
                    await final_q.put(path)
                if on_final:
                    asyncio.create_task(on_final(path))
                continue  

            # A) 병합 시작 신호 감지 → 녹화 종료/병합 시작 텔레그램
            if merge_start_pat.search(line):
                try:
                    if last_notified_state.get(channel_id) not in ("녹화종료", "병합완료"):
                        dur = recorder_manager.get_recording_duration(channel_id)  # "HH:MM:SS"
                        fname = os.path.basename(expected_out) if expected_out else None
                        msg = (
                            f"<b>{ch_name}</b> 녹화가 <b>종료</b>되었습니다. 병합을 시작합니다."
                            + (f" (녹화시간 {dur})" if dur else "")
                            + (f"\n<code>{fname}</code>" if fname else "")
                        )
                        sendTelegram(msg)
                        last_notified_state[channel_id] = "녹화종료"
                except Exception as _e:
                    print(f"[WARN] merge-start telegram failed: {_e}")

            # B) 병합 완료 신호 감지 → 최종 파일 경로 처리
            m2 = merge_done_pat.search(line)
            if m2:
                p = m2.group(1).strip().strip("'\"")
                path = p if os.path.isabs(p) else os.path.join(cwd or "", p)
                if final_q:
                    await final_q.put(path)
                if on_final:
                    asyncio.create_task(on_final(path))

    # 종료 시 잔여 버퍼에서 완료 한 번 더 체크
    if buffer:
        # 잔여 버퍼에 __FINAL__ 라인이 남았을 수도 있으니 줄 단위로 스캔
        found_final = False
        for raw in buffer.splitlines():
            line = raw.rstrip("\r\n")
            if line.startswith("__FINAL__:"):
                payload = line[len("__FINAL__:"):].strip()
                try:
                    p = json.loads(payload)
                except Exception:
                    p = payload.strip().strip("'\"")
                path = p if os.path.isabs(p) else os.path.join(cwd or "", p)
                if final_q:
                    await final_q.put(path)
                if on_final:
                    asyncio.create_task(on_final(path))
                found_final = True
                break

        if not found_final:
            m2 = merge_done_pat.search(buffer)
            if m2:
                p = m2.group(1).strip().strip("'\"")
                path = p if os.path.isabs(p) else os.path.join(cwd or "", p)
                if final_q:
                    await final_q.put(path)
                if on_final:
                    asyncio.create_task(on_final(path))


# 프로세스 트리를 종료하는 함수
def killProcessTree(pid):
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        for child in children:
            print(f"[DEBUG] 종료 중인 하위 프로세스 PID: {child.pid}")
            child.kill()
        parent.kill()
        print(f"[DEBUG] 프로세스 트리가 종료되었습니다. PID: {pid}")
    except psutil.NoSuchProcess:
        print(f"[WARNING] 프로세스를 찾을 수 없습니다. PID: {pid}")


# yt-dlp 임시 파일/조각 삭제 함수
def cleanupTmp(prefix_path, tmp_dir=None, keep_ts=True):

    # 1) prefix 기반 찌꺼기 정리
    pp = glob.escape(prefix_path)
    patterns = [
        pp + ".f*",
        pp + "*.part",
    ]

    if not keep_ts:
        patterns.extend([prefix_path + "*.ts"])

    for pat in patterns:
        for p in glob.glob(pat):
            try:
                if os.path.isfile(p):
                    os.remove(p)
            except Exception:
                pass

    # 2) tmp_dir 제거(성공 시에만)
    if tmp_dir and os.path.isdir(tmp_dir):
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


# 녹화 진행표시 함수
async def progressTouchLoop(progress_path: str, proc):
    # 시작 즉시 생성
    try:
        with open(progress_path, "w", encoding="utf-8") as f:
            f.write("recording...\n")
    except Exception:
        pass

    try:
        while proc.returncode is None:
            # mtime 갱신으로 탐색기/툴에서 살아있음 표시
            try:
                os.utime(progress_path, None)
            except FileNotFoundError:
                # 누가 지웠으면 다시 만든다
                with open(progress_path, "w", encoding="utf-8") as _f:
                    _f.write("recording...\n")
            await asyncio.sleep(3)
    finally:
        # 종료 시 즉시 삭제
        try:
            if os.path.exists(progress_path):
                os.remove(progress_path)
        except Exception:
            pass


# rename 재시도 함수
async def safeRename(src: str, dst: str, tries: int = 7, delay: float = 1.0):
    for i in range(tries):
        try:
            os.replace(src, dst)
            return True
        except PermissionError as e:
            if getattr(e, "winerror", None) != 32:
                raise
            await asyncio.sleep(delay)
    return False


# 사용자 중지 요청 처리 함수 
async def checkStopRequest(channel_id: str, proc):
    while True:
        await asyncio.sleep(1)
        if recorder_manager.get_is_user_stopped(channel_id):
            print(f"[DEBUG] {channel_id} 중지 요청 – 병합 시그널 전송", flush=True)
            sendInterrupt(proc)
            # 종료 대기/병합/정리는 메인 루틴에서만 수행(레이스 제거)
            break


async def tryFallbackMuxByFragments(*, output_dir: str, prefix_base: str, tmp_dir: str | None, output_path: str) -> bool:
    try:
        # 이미 최종 파일이 정상이라면 성공 처리
        try:
            if output_path and os.path.isfile(output_path) and os.path.getsize(output_path) >= 1024 * 1024:
                return True
        except Exception:
            pass

        # 후보 파일 수집(출력폴더 + tmp_dir)
        cand: list[str] = []

        pp = glob.escape(prefix_base)

        # prefix 기반 우선 스캔
        for pat in (pp + ".f*", pp + "*.part", pp + ".*.part"):
            cand.extend(glob.glob(pat))

        # output_dir 별도 지정된 경우
        if output_dir and os.path.isdir(output_dir):
            cand.extend(glob.glob(os.path.join(output_dir, "*.f*")))
            cand.extend(glob.glob(os.path.join(output_dir, "*.part")))

        if tmp_dir and os.path.isdir(tmp_dir):
            cand.extend(glob.glob(os.path.join(tmp_dir, "*.f*")))
            cand.extend(glob.glob(os.path.join(tmp_dir, "*.part")))

        # 파일만 + 중복 제거
        cand = list(dict.fromkeys([p for p in cand if os.path.isfile(p)]))

        # .part 제외
        non_part = [p for p in cand if not p.lower().endswith(".part")]
        if non_part:
            cand = non_part

        if not cand:
            return False

        audio_exts = {".m4a", ".aac", ".opus", ".weba", ".mka", ".mp3"}
        video_exts = {".mp4", ".mkv", ".webm", ".ts"}

        def _ext(p: str) -> str:
            return os.path.splitext(p)[1].lower()

        def _pick_largest(paths: list[str]) -> str | None:
            best = None
            bs = -1
            for p in paths:
                try:
                    s = os.path.getsize(p)
                    if s > bs:
                        best, bs = p, s
                except Exception:
                    pass
            return best

        audio_candidates = [p for p in cand if _ext(p) in audio_exts]
        video_candidates = [p for p in cand if _ext(p) in video_exts and p not in audio_candidates]

        v = _pick_largest(video_candidates)
        a = _pick_largest(audio_candidates)

        # 비디오만 있는경우 output_path로 복사
        if v and not a:
            try:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                if os.path.abspath(v) != os.path.abspath(output_path):
                    await asyncio.to_thread(shutil.copy2, v, output_path)
                return os.path.isfile(output_path) and os.path.getsize(output_path) >= 1024 * 1024
            except Exception:
                return False

        # 비디오+오디오가 둘 다 있어야 copy mux 가능
        if not v or not a:
            return False

        ffmpeg = getFFmpeg()
        cmd = [
            ffmpeg, "-y",
            "-i", v,
            "-i", a,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c", "copy",
            "-shortest",
            output_path,
        ]

        r = await asyncio.to_thread(
            subprocess.run,
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if r.returncode == 0 and os.path.isfile(output_path) and os.path.getsize(output_path) >= 1024 * 1024:
            return True

        tail = (r.stderr or "")[-1200:]
        print(f"[WARN] tryFallbackMuxByFragments failed. rc={r.returncode}\n{tail}", flush=True)
        return False

    except Exception as e:
        print(f"[WARN] tryFallbackMuxByFragments exception: {e}", flush=True)
        return False


# 유튜브 병합 후 파일 이동 공통 함수
async def moveAfterProcessingTask(*, mp_enabled: bool, mp_dir: str, prefix_path: str, move_src: str | None,
                                  base_dir: str = base_directory, scan_window_sec: int = 900, settle_sec: float = 5.0, 
                                  retries: int = 8, retry_delay: float = 1.2, channel_id: str | None = None, channel_name: str | None = None):

    # 0) 설정 로깅 및 빠른 실패 사유 노출
    print(f"[MOVE] enabled={mp_enabled} dest='{mp_dir}' prefix='{prefix_path}' src='{move_src}'", flush=True)
    if not mp_enabled:
        print("[MOVE] skip: moveAfterProcessingEnabled=False", flush=True)
        return
    if not mp_dir or not mp_dir.strip():
        print("[MOVE] skip: moveAfterProcessing path is empty", flush=True)
        return

    # 1) 목적지 절대경로화
    dest_dir = mp_dir.strip()
    if not os.path.isabs(dest_dir):
        dest_dir = os.path.join(base_dir, dest_dir)

    # 2) 후보 파일 확보 (우선순위: 인자로 받은 move_src → prefix 확장자 매칭 → 최근 스캔)
    candidate = move_src if (move_src and os.path.exists(move_src)) else None
    if not candidate:
        for ext in (".mp4", ".mkv", ".ts"):
            p = prefix_path + ext
            if os.path.exists(p):
                candidate = p
                break

    if not candidate:
        root_dir = os.path.dirname(prefix_path)
        now = time.time()
        cands = []
        for ext in (".mp4", ".mkv", ".ts"):
            cands.extend(glob.glob(os.path.join(root_dir, f"*{ext}")))
        # 최근 파일만
        cands = [p for p in cands if os.path.getmtime(p) >= now - scan_window_sec]
        same_stem = [p for p in cands if os.path.splitext(p)[0] == prefix_path]
        pick = same_stem[0] if same_stem else (max(cands, key=os.path.getmtime) if cands else None)
        if pick and os.path.exists(pick):
            candidate = pick

    if not candidate or not os.path.exists(candidate):
        print(f"[MOVE] no-candidate: prefix='{prefix_path}' window={scan_window_sec}s", flush=True)
        return

    # 3) 같은 폴더면 이동 불필요
    src_dir = os.path.normcase(os.path.abspath(os.path.dirname(candidate)))
    dst_dir = os.path.normcase(os.path.abspath(dest_dir))
    if src_dir == dst_dir:
        print(f"[MOVE] skip: destination equals source dir: {dst_dir}", flush=True)
        return

    # 4) 작업 안정화를 위해 잠깐 대기
    await asyncio.sleep(settle_sec)

    # 5) PermissionError(특히 WinError 32) 등에 대한 재시도 래핑
    for i in range(1, retries + 1):
        try:
            print(f"[MOVE] try {i}/{retries}: '{candidate}' → '{dest_dir}'", flush=True)
            await moveDirectory(candidate, dest_dir)
            print("[MOVE] done", flush=True)

            # 병합 완료 안전망 알림 (파이프/메인 경로에서 놓친 경우)
            try:
                if channel_id and channel_name and last_notified_state.get(channel_id) != "병합완료":
                    sendTelegram(
                        f"<b>{channel_name}</b> 유튜브 <b>병합 완료</b>\n<code>{os.path.basename(candidate)}</code>"
                    )
                    last_notified_state[channel_id] = "병합완료"
            except Exception as _e:
                print(f"[WARN] yt merge-done telegram (late-move) failed: {_e}", flush=True)

            return

        except Exception as e:

            # PermissionError면 재시도, 그 외엔 즉시 로그 후 중단
            if isinstance(e, PermissionError) or "used by another process" in str(e).lower():
                await asyncio.sleep(retry_delay)
                continue
            print(f"[MOVE] failed (non-retry): {e}", flush=True)
            return

    print(f"[MOVE] failed: all retries exhausted for '{candidate}'", flush=True)


# 유튜브용 녹화 시작 함수
async def ytStartRecording(channel, recheckInterval: int, filenamePattern: str, moveAfterProcessingEnabled: bool,
                           moveAfterProcessing: str, ycookie_path: str | None, is_user_request: bool = False):

    print("[DEBUG] youtube_recorder loaded from:", __file__, "cleanupTmp id:", id(globals().get("cleanupTmp", None)), flush=True)

    # 0) 쿠키 유효성 (항상 기본값 보장)
    cookies_valid = False

    last_video_id = None

    # 전달된 경로 검사
    if not (isinstance(ycookie_path, str) and os.path.isfile(ycookie_path)):
        ycookie_path = None
    else:
        try:
            cookies_valid, _ = validateCookies(ycookie_path)
        except Exception:
            cookies_valid = False

    # 쿠키가 무효/부재면 최소 CONSENT 쿠키 생성해 폴백
    if not cookies_valid:
        try:
            ycookie_path = ysaveCookies()                 # /json/ycookie.txt 에 작성
            cookies_valid, _ = validateCookies(ycookie_path)
            if cookies_valid:
                print("[INFO] Minimal CONSENT cookie applied for public live.")
        except Exception as _e:
            print(f"[WARN] minimal cookie create failed: {_e}")
            cookies_valid = False
            ycookie_path = None


    # 1) 채널 동기화
    state_channels = RecorderManager.getChannels() or []
    channel = next((c for c in state_channels if c["id"] == channel["id"]), None)
    if not channel or channel.get("platform") != "youtube":
        return

    channel_id = channel["id"]
    channel_name = channel["name"]

    # 2) 사용자 시작이면 stop 해제
    if is_user_request:
        recorder_manager.set_is_user_stopped(channel_id, False)
    elif recorder_manager.get_is_user_stopped(channel_id):
        return

    # 3) 이미 녹화 중이면 거절
    if recorder_manager.get_status_recording(channel_id) and recorder_manager.get_tasks_process(channel_id):
        return

    try:
        while True:
 
            # 4) 사용자 중지 즉시 탈출
            if recorder_manager.get_is_user_stopped(channel_id):
                recorder_manager.set_status_recording(channel_id, False)
                return

            # 5) 토글 최신화
            current_channels = RecorderManager.getChannels() or []
            curr = next((c for c in current_channels if c.get("id") == channel_id), None) or channel
            rec_enabled = bool(curr.get("record_enabled", True))

            # 6) 라이브 여부 확인
            metadata = await getYoutubeMetadata(curr, ycookie_path)
            is_live = bool(metadata.get("is_live"))
            last_video_id = metadata.get("video_id")

            # 7) 녹화 전 표시: 라이브가 아니면 토글에 따라 예약/대기
            if not is_live:

                if rec_enabled:
                    # 토글 ON → 예약 유지
                    recorder_manager.set_status_recording(channel_id, False)
                    recorder_manager.set_status_reserved(channel_id, True)
                    recorder_manager.recording_remove_start_time(channel_id)

                    # 예약녹화 전환 알림 
                    try:
                        new_state = "예약녹화 중"
                        if last_notified_state.get(channel_id) != new_state:
                            sendTelegram(f"<b>{channel_name}</b> 채널은 <i>예약녹화 중</i>으로 전환되었습니다.")
                            last_notified_state[channel_id] = new_state
                    except Exception as _e:
                        print(f"[WARN] yt reserved telegram failed(1): {_e}")

                    # 결정적 지터 대기 블록
                    _base = max(10, int(recheckInterval))
                    _jit  = max(1, int(_base * JITTER_RATIO))
                    _seed = int(hashlib.blake2b(str(channel_id).encode(), digest_size=4).hexdigest(), 16)

                    _phase = _JITTER_PHASE.get(channel_id)
                    if _phase is None:
                        _phase = (_seed % (2 * _jit + 1)) - _jit  # [-_jit, +_jit]
                        _JITTER_PHASE[channel_id] = _phase

                    now = time.monotonic()
                    period = _base
                    k = math.floor((now - (START_MONO + _phase)) / period) + 1
                    next_time = START_MONO + _phase + k * period
                    _sleep = max(1, int(next_time - now))

                    print(f"[DEBUG] {channel_name} 예약 유지. {_sleep}s 후 재탐색(초기위상={_phase:+d}s, 주기={period}s).")
                    await asyncio.sleep(_sleep)
                    continue

                else:
                    # 토글 OFF → 1회성: 예약 보류(대기)
                    recorder_manager.set_status_recording(channel_id, False)
                    recorder_manager.set_status_reserved(channel_id, False)
                    recorder_manager.recording_remove_start_time(channel_id)
                    print(f"[DEBUG] {channel_name} 토글 OFF(1회성). 라이브 미오픈이므로 종료.")
                    break

            # 8) 화질/확장자
            user_q = (curr.get("quality") or "best").strip().lower()
            selected_quality = user_q if re.match(r"^(?:\d+p(?:60)?|best)$", user_q) else "best"
            ext = ".mkv"

            print(f"[DEBUG] ytStartRecording: launch {channel_id} q={selected_quality} cookie={'yes' if cookies_valid else 'no'}")

            # 8-1) 이동 설정을 불리언 정규화
            mp_enabled = toBool(moveAfterProcessingEnabled, default=False)
            mp_dir     = (moveAfterProcessing or "").strip()

            print(f"[DEBUG] moveAfterProcessingEnabled(global)={mp_enabled} moveAfterProcessing(global)='{mp_dir}'", flush=True)

            # 9) yt-dlp 명령 생성
            output_dir_input = curr.get("output_dir", "output")
            record_cmd, prefix_path, output_path, tmp_dir = buildCommand(
                channel=curr,
                output_dir=output_dir_input,
                quality=selected_quality,
                extension=ext,
                metadata=metadata,
                cookies_valid=cookies_valid,
                filenamePattern=filenamePattern,
                ycookie_path=ycookie_path,
            )

            # buildCommand가 반환한 최종 경로 기준으로 output_dir를 확정
            output_dir = os.path.dirname(output_path) if output_path else output_dir_input

            # 병합 실패 분기에서도 안전하게 참조되도록 초기화
            move_src = None

            if not record_cmd or not prefix_path or not output_path or not tmp_dir:

                print("[ERROR] 명령어 생성 실패로 유튜브 녹화를 시작할 수 없습니다.", flush=True)
                return

            # 명령 생성 실패 시
            if not output_path:
                recorder_manager.set_status_recording(channel_id, False)
                recorder_manager.clear_tasks_process(channel_id)
                recorder_manager.recording_remove_start_time(channel_id)
                recorder_manager.recording_remove_filename(channel_id)

                if rec_enabled:
                    recorder_manager.set_status_reserved(channel_id, True)
                    await asyncio.sleep(recheckInterval)
                    continue
                else:
                    recorder_manager.set_status_reserved(channel_id, False)
                    print(f"[DEBUG] {channel_name} 토글 OFF(1회성). 명령 생성 실패 후 종료.")
                    break

            safe_cmd = []
            skip_next = False
            for a in record_cmd:
                if skip_next:
                    safe_cmd.append("****")
                    skip_next = False
                    continue
                # yt-dlp에서는 PO토큰을 extractor-args로 넘기므로 그 값/쿠키경로만 마스킹
                if a in ("--cookies", "--extractor-args"):
                    safe_cmd.append(a)
                    skip_next = True
                    continue
                safe_cmd.append(a)

            print("[DEBUG] yt-dlp 실행 명령:", " ".join(shlex.quote(arg) for arg in safe_cmd))

            # 10) 환경설정 및 실행
            ffmpeg_dir = os.path.dirname(getFFmpeg())
            env = os.environ.copy()
            env["PATH"] = os.pathsep.join([ffmpeg_dir, env.get("PATH", "")])

            kwargs = {}
            if os.name == "nt":
                kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                import os as _posix_os
                kwargs["preexec_fn"] = _posix_os.setsid

            cwd_dir = tmp_dir if (tmp_dir and os.path.isdir(tmp_dir)) else os.path.dirname(prefix_path)

            proc = await asyncio.create_subprocess_exec(
                *record_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd_dir,  
                env=env,
                limit=2 ** 20,
                **kwargs,
            )

            recorder_manager.set_tasks_process(channel_id, proc)
            recorder_manager.recording_set_filename(channel_id, output_path)

            # 진행 표시 파일 루프 시작
            progress_path = prefix_path + ".recording"
            progress_task = asyncio.create_task(progressTouchLoop(progress_path, proc))

            # 11) 프로세스 핸들 확보 후에만 녹화 중으로 승격
            recorder_manager.set_status_recording(channel_id, True)
            recorder_manager.set_status_reserved(channel_id, False)
            recorder_manager.recording_set_start_time(channel_id)
            sendTelegram(f"<b>{channel_name}</b> 채널의 녹화가 시작되었습니다.")

            # 이 회차 시작 시, 과거 병합완료 가드 초기화 + 세션 플래그
            with contextlib.suppress(Exception):
                last_notified_state.pop(channel_id, None)
            merge_notified = False

            # 내부 로거
            def logger(msg: str, flush: bool = True):
                print(msg, flush=flush)

            final_q = asyncio.Queue()

            # 최종 산출 경로 그대로 사용
            expected_out = output_path or (f"{prefix_path}.mkv")

            err_task = asyncio.create_task(
                readPipe(proc.stderr, channel_id, channel_name, final_q,
                        cwd=os.path.dirname(prefix_path), expected_out=expected_out)
            )
            out_task = asyncio.create_task(
                readPipe(proc.stdout, channel_id, channel_name, final_q,
                        cwd=os.path.dirname(prefix_path), expected_out=expected_out)
            )

            stop_task = asyncio.create_task(checkStopRequest(channel_id, proc))


            # 13) 프로세스 종료 대기
            print("[DEBUG] await proc.wait() ...", flush=True)
            await proc.wait()
            print("[DEBUG] proc.wait() returned", flush=True)

            # stop 플래그 스냅샷
            stop_req = recorder_manager.get_is_user_stopped(channel_id)

            # 14) 리더 태스크 정리 (가능하면 자연종료까지 기다림)
            print("[DEBUG] join pipe readers ...", flush=True)

            # proc가 끝났으면 보통 pipe reader도 EOF로 곧 종료됨.
            # Windows/버퍼 상황에서 마지막 로그가 늦게 도착할 수 있어 timeout을 약간 늘림.
            done, pending = await asyncio.wait({err_task, out_task}, timeout=15.0)

            # 남은 태스크는 취소 후 합류
            for t in pending:
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await t

            # stop 감시 태스크도 정리
            if not stop_task.done():
                stop_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await stop_task

            print(f"[DEBUG] readers joined. done={len(done)} pending_canceled={len(pending)}", flush=True)

            print("[DEBUG] checkpoint A: before progress_task cancel", flush=True)
            if 'progress_task' in locals():
                try:
                    progress_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await asyncio.wait_for(progress_task, timeout=3.0)
                except asyncio.TimeoutError:
                    print("[WARN] progress_task cancel timeout; continue", flush=True)

            print("[DEBUG] entering post-merge handling", flush=True)

            # 유효 파일 판정 기준: 1MB 미만이면 깨진 파일/0KB로 간주
            MIN_OK_SIZE = 1024 * 1024  # 1MB

            def is_ok(p: str) -> bool:
                try:
                    return bool(p) and os.path.isfile(p) and os.path.getsize(p) >= MIN_OK_SIZE
                except Exception:
                    return False

            # 15-0) 프로세스 종료 보장
            try:
                await asyncio.wait_for(proc.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                logger(f"[WARN] yt-dlp proc wait timeout. killing...", flush=True)
                try:
                    proc.kill()
                except Exception:
                    pass
                await proc.wait()

            rc = proc.returncode
            logger(f"[INFO] yt-dlp exit code={rc}", flush=True)

            # 15-1) 최종 파일 경로 확정
            move_src: str | None = None
            merge_ok = False

            # (1) __FINAL__:%(filepath)j 로 받은 최종경로 우선
            final_path = None
            try:
                while True:
                    final_path = final_q.get_nowait()
            except Exception:
                pass

            if final_path and os.path.isfile(final_path):
                move_src = final_path
                merge_ok = True

            # (2) output_path가 실제로 생겼으면 그걸 사용
            if (not move_src) and output_path and os.path.isfile(output_path):
                move_src = output_path
                merge_ok = True

            # (3) 그래도 못 찾으면 prefix 기반으로 마지막 산출물 스캔
            if not move_src:
                # mkv 우선, 그 다음 mp4/webm
                candidates = []
                for ext in (".mkv", ".mp4", ".webm", ".ts"):
                    p = prefix_path + ext
                    if os.path.isfile(p):
                        candidates.append(p)

                # output_dir/tmp_dir에도 혹시 다른 이름으로 떨어진 경우 대비
                def _pick_best_from_dir(d: str | None):
                    if not d or not os.path.isdir(d):
                        return None

                    # prefix 파일명 시작하는 파일만 추려서 가장 큰 파일을 우선
                    base = os.path.basename(prefix_path)
                    best = None
                    best_size = -1
                    for fn in os.listdir(d):
                        if base not in fn:
                            continue
                        full = os.path.join(d, fn)
                        if os.path.isfile(full):
                            sz = 0
                            try:
                                sz = os.path.getsize(full)
                            except Exception:
                                sz = 0
                            if sz > best_size:
                                best_size = sz
                                best = full
                    return best

                cand2 = _pick_best_from_dir(output_dir) or _pick_best_from_dir(tmp_dir)
                if cand2:
                    candidates.append(cand2)

                # 후보 중 가장 큰 파일을 채택
                if candidates:
                    best = None
                    best_size = -1
                    for p in candidates:
                        try:
                            sz = os.path.getsize(p)
                        except Exception:
                            sz = 0
                        if sz > best_size:
                            best_size = sz
                            best = p
                    if best and os.path.isfile(best):
                        move_src = best
                        merge_ok = True

            # (4) 그래도 안되면 조각 기반 강제 병합 시도 
            if not move_src:
                try:
                    ok = await tryFallbackMuxByFragments(
                        output_dir=output_dir,
                        prefix_base=prefix_path,
                        tmp_dir=tmp_dir,
                        output_path=output_path,
                    )
                    if ok and output_path and os.path.isfile(output_path):
                        move_src = output_path
                        merge_ok = True
                except Exception as e:
                    logger(f"[WARN] fallback mux failed: {e}", flush=True)

            # 15-2) 임시 조각 정리
            try:
                cleanupTmp(prefix_path, tmp_dir=tmp_dir, keep_ts=not merge_ok)
            except Exception:
                pass

            # 16) 후처리 이후 파일 자동이동 (옵션 ON일 때만)
            if merge_ok and move_src and os.path.isfile(move_src):
                try:
                    await moveAfterProcessingTask(
                        mp_enabled=mp_enabled,
                        mp_dir=(curr.get("moveToDir") or mp_dir),
                        prefix_path=prefix_path,
                        move_src=move_src,
                        channel_id=channel_id,
                        channel_name=channel_name,
                    )

                except Exception as e:
                    logger(f"[WARN] moveAfterProcessingTask failed: {e}", flush=True)
            else:
                logger(f"[INFO] skip moveAfterProcessing (merge_ok={merge_ok}, move_src={move_src})", flush=True)

            # 병합완료 텔레그램 누락 시 한 번 더 시도
            if not merge_notified:
                final_hint = move_src or output_path
                if final_hint and os.path.exists(final_hint):
                    try:
                        sendTelegram(
                            f"<b>{channel_name}</b> 유튜브 <b>병합 완료</b>\n<code>{os.path.basename(final_hint)}</code>"
                        )
                        merge_notified = True
                        last_notified_state[channel_id] = "병합완료"
                    except Exception as _e:
                        print(f"[WARN] yt merge-done telegram failed(2nd): {_e}")

            # 17) 세션 종료 컨텍스트 정리
            stop_req = recorder_manager.get_is_user_stopped(channel_id)
            try:
                auto_cfg = (loadConfig() or {}).get("autoRecordingMode", False)
            except Exception:
                auto_cfg = False
            rec_enabled_dbg = bool(curr.get("record_enabled", True))

            print(
                f"[REC-END] {channel_name} auto={auto_cfg} "
                f"enabled={rec_enabled_dbg} stop_requested={stop_req}"
            )

            # 만약 파이프에서 녹화종료를 못 보낸 경우에만 한 번 더 보냄
            try:
                if last_notified_state.get(channel_id) not in ("녹화종료", "병합완료"):
                    dur = recorder_manager.get_recording_duration(channel_id)
                    msg = (
                        f"<b>{channel_name}</b> 녹화가 <b>종료</b>되었습니다. 병합을 시작합니다."
                        + (f" (녹화시간 {dur})" if dur else "")
                        + (f"\n<code>{os.path.basename(output_path)}</code>" if output_path else "")
                    )
                    sendTelegram(msg)
                    last_notified_state[channel_id] = "녹화종료"

            except Exception as _e:
                print(f"[WARN] yt record-done telegram failed: {_e}")

            try:
                recorder_manager.set_status_recording(channel_id, False)
                recorder_manager.recording_remove_start_time(channel_id)
                recorder_manager.recording_remove_filename(channel_id)
                recorder_manager.clear_tasks_process(channel_id)

            except Exception as _e:
                print(f"[WARN] end-of-session cleanup failed: {_e}")

            if not stop_req:
                recorder_manager.set_is_user_stopped(channel_id, False)

            print(f"[DEBUG] {channel_name} 세션 종료. FSM 후속 전이")

            # 종료 후 분기(지속 감시 vs 종료)
            latest = RecorderManager.getChannels() or []
            latest_ch = next((c for c in latest if c.get("id") == channel_id), None) or curr
            latest_rec_enabled = bool(latest_ch.get("record_enabled", True))

            if stop_req:
                recorder_manager.set_status_reserved(channel_id, False)
                break

            if latest_rec_enabled:
                recorder_manager.set_status_reserved(channel_id, True)

                # 예약녹화 전환 알림
                try:
                    new_state = "예약녹화 중"
                    if last_notified_state.get(channel_id) != new_state:
                        sendTelegram(f"<b>{channel_name}</b> 채널은 <i>예약녹화 중</i>으로 전환되었습니다.")
                        last_notified_state[channel_id] = new_state
                except Exception as _e:
                    print(f"[WARN] yt reserved telegram failed(2): {_e}")

                _base = max(10, int(recheckInterval))
                _jit  = max(1, int(_base * JITTER_RATIO))
                _seed = int(hashlib.blake2b(str(channel_id).encode(), digest_size=4).hexdigest(), 16)

                _phase = _JITTER_PHASE.get(channel_id)
                if _phase is None:
                    _phase = (_seed % (2 * _jit + 1)) - _jit
                    _JITTER_PHASE[channel_id] = _phase

                now = time.monotonic()
                period = _base
                k = math.floor((now - (START_MONO + _phase)) / period) + 1
                next_time = START_MONO + _phase + k * period
                _sleep = max(1, int(next_time - now))

                print(f"[DEBUG] {channel_name} 종료 → 예약 유지. {_sleep}s 후 재탐색(초기위상={_phase:+d}s, 주기={period}s).")
                await asyncio.sleep(_sleep)

                continue

            else:
                recorder_manager.set_status_reserved(channel_id, False)
                print(f"[DEBUG] {channel_name} 토글 OFF(1회성). 종료.")
                break

    except Exception as e:
        print(f"[ERROR] {channel_name} 녹화 중 예외: {e}")

    finally:
        with contextlib.suppress(Exception):
            recorder_manager.set_status_recording(channel_id, False)
            recorder_manager.clear_tasks_process(channel_id)
            recorder_manager.recording_remove_start_time(channel_id)
            recorder_manager.recording_remove_filename(channel_id)

        try:
            # merge_ok 플래그가 있을 때만 성공 cleanup 수행
            if 'merge_ok' in locals() and merge_ok:
                print(f"[DEBUG] call cleanupTmp(finally) prefix='{prefix_path}', tmp_dir='{tmp_dir}'", flush=True)
                cleanupTmp(prefix_path, tmp_dir)

            # 진행파일 삭제 안전망
            with contextlib.suppress(Exception):
                progress_path = prefix_path + ".recording"
                if os.path.exists(progress_path):
                    os.remove(progress_path)

        except Exception:
            pass

        if is_user_request:
            recorder_manager.set_is_user_stopped(channel_id, False)

        try:
            latest = RecorderManager.getChannels() or []
            latest_ch = next((c for c in latest if c.get("id") == channel_id), None) or {}
            if bool(latest_ch.get("record_enabled", True)):
                if not recorder_manager.get_is_user_stopped(channel_id):
                    recorder_manager.set_status_reserved(channel_id, True)

        except Exception:
            pass


# 유튜브용 녹화 중지 함수
async def ytStopRecording(channel_id: str):
    print(f"[DEBUG] ytStopRecording 시작 - 채널 ID: {channel_id}")

    # 이미 요청이 들어가 있으면 아무 것도 하지 않음
    if recorder_manager.get_is_user_stopped(channel_id):
        return

    # 중지 요청 플래그만 세우고 리턴
    recorder_manager.set_is_user_stopped(channel_id, True)
    print(f"[DEBUG] {channel_id} 중지 요청 플래그 설정 완료")