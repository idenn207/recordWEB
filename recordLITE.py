from __future__ import annotations

import asyncio
import contextlib
import os
import random
import signal
import sys
import time
from typing import Any, Dict, List, Optional

from module.data_manager import (
    RecorderManager, loadConfig, loadChannels,
    base_directory, getFFmpeg, getYtarchive, yloadCookies,
)

from module.recording_adapter import preflightIsLive, startOneShot
from module.common_errors import printOnce, debugThrottle

# 전역 RecorderManager 인스턴스 
recorder_manager = RecorderManager()


DEFAULTS: Dict[str, Any] = {
    "scan_interval_sec": 35,              # 라운드로빈 1회 통과 최소 간격(대기시)
    "jitter_sec": 3,                      # 채널별 지터(동시 몰림 방지)
    "preflight_timeout_sec": 12,          # 프리플라이트 타임아웃
    "max_parallel_preflights": 6,         # 동시 프리플라이트(권장 4~8)
    "max_parallel_recordings": 0,         # 동시 녹화 제한(0=무제한)
    "status_ping_sec": 10,                # 상태 핑 주기(--verbose)
    "yt_monitor_on_not_live": True,       # 유튜브 비라이브도 모니터 시작
}


def _normalizeChannel(c: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(c, dict):
        return None
    plat = (c.get("platform") or "").strip().lower()
    cid  = (c.get("id") or "").strip()
    if not cid or plat not in ("chzzk", "youtube"):
        return None
    if not c.get("name"):
        c["name"] = cid
    if plat == "youtube":
        # @handle / UC... 로 정규화
        if cid and not (cid.startswith("@") or cid.startswith("UC")):
            c["id"] = "@" + cid
    # 안전 기본값
    c.setdefault("record_enabled", True)
    return c


def _loadLiteConfig() -> Dict[str, Any]:
    cfg = loadConfig() or {}
    lite = dict(DEFAULTS)
    lite.update((cfg.get("lite") or {}))
    # 하한/형식 보정
    try:
        if int(lite.get("max_parallel_preflights", 1)) < 1:
            lite["max_parallel_preflights"] = 1
        if int(lite.get("max_parallel_recordings", 0)) < 0:
            lite["max_parallel_recordings"] = 0
        if int(lite.get("scan_interval_sec", 10)) < 5:
            lite["scan_interval_sec"] = 5
        if int(lite.get("preflight_timeout_sec", 12)) < 4:
            lite["preflight_timeout_sec"] = 4
        if int(lite.get("status_ping_sec", 10)) < 5:
            lite["status_ping_sec"] = 5
        if int(lite.get("jitter_sec", 0)) < 0:
            lite["jitter_sec"] = 0
    except Exception:
        pass
    return lite



async def _statusPing(cfg: Dict[str, Any], *, verbose: bool = False):
    iv = int(cfg.get("status_ping_sec", 10) or 10)
    while True:
        try:
            if verbose:
                recs = [k for k, v in (recorder_manager.status_recording or {}).items() if v]
                rsvs = [k for k, v in (recorder_manager.status_reserved  or {}).items() if v]
                print(f"[LITE] ping  rec={len(recs)} rsv={len(rsvs)}  "
                      f"(ffmpeg={getFFmpeg()} ytarchive={getYtarchive()})")
        except Exception:
            pass
        await asyncio.sleep(iv)


async def _probeAndAct(channel: Dict[str, Any], cfg: Dict[str, Any],
                         sem_pf: asyncio.Semaphore,
                         sem_rec: Optional[asyncio.Semaphore], *,
                         verbose: bool = False):
    cid = channel.get("id") or "unknown"
    name = channel.get("name") or cid
    plat = (channel.get("platform") or "").lower()

    scan_iv  = int(cfg.get("scan_interval_sec", 35))
    jitter   = int(cfg.get("jitter_sec", 0))
    pf_to    = int(cfg.get("preflight_timeout_sec", 12))
    yt_mon   = bool(cfg.get("yt_monitor_on_not_live", True))

    # 예약으로 시작
    recorder_manager.set_status_reserved(cid, True)
    recorder_manager.set_status_recording(cid, False)

    # 공정성: 채널별 지터
    if jitter > 0:
        await asyncio.sleep(random.uniform(0, jitter))

    # 유튜브는 프리플라이트를 건너뛰고 '상시 모니터'로 전환 (명시 가드)
    if plat == "youtube":
        while True:
            try:
                if not channel.get("record_enabled", True):
                    await asyncio.sleep(max(60, scan_iv))
                    continue
                if not recorder_manager.guard_try_acquire_start(cid):
                    await asyncio.sleep(max(3, jitter))
                    continue
                try:
                    recorder_manager.set_status_reserved(cid, True)
                    recorder_manager.set_status_recording(cid, False)
                    if verbose:
                        print(f"[LITE] monitor(always): {name} (youtube) — ytarchive --monitor-channel")
                    await startOneShot(channel, plat, loadConfig() or {}, is_user_request=True)
                finally:
                    recorder_manager.set_status_recording(cid, False)
                    recorder_manager.set_status_reserved(cid, True)   # ← 종료 즉시 예약 복원(재탐색 지속)
                    recorder_manager.guard_release_start(cid)
                await asyncio.sleep(max(3, jitter))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                for delay in (15, 30, 60, 120, 300):
                    print(f"[LITE][WARN] {name}: {e} → sleep {delay}s")
                    await asyncio.sleep(delay)
                    break

    # 치지직 등은 기존 프리플라이트 → 라이브 시 즉시 녹화
    while True:
        try:
            if not channel.get("record_enabled", True):
                await asyncio.sleep(max(60, scan_iv))
                continue

 
            if verbose:
                print(f"[LITE] pf> {name} ({plat})")
            try:
                async with sem_pf:
                    live = await asyncio.wait_for(preflightIsLive(channel, plat), timeout=pf_to)
            except asyncio.TimeoutError:
                print(f"[LITE][WARN] {name} pf-timeout {pf_to}s → not-live")
                live = False
            except Exception as e:
                print(f"[LITE][WARN] {name} pf-error: {e} → not-live")
                live = False
            if verbose:
                print(f"[LITE] pf< {name} ({plat}) => {live}")

            if not live:
                debugThrottle(
                    f"lite:wait:{plat}:{cid}",
                    f"[LITE] {name} not live → {scan_iv}s",
                    min_secs=max(10, scan_iv // 2),
                    print_fn=print,
                )
                await asyncio.sleep(scan_iv)
                continue

 
            if sem_rec is not None:
                await sem_rec.acquire()
            if not recorder_manager.guard_try_acquire_start(cid):
                if sem_rec is not None:
                    with contextlib.suppress(Exception):
                        sem_rec.release()
                await asyncio.sleep(max(3, jitter))
                continue
            try:
                recorder_manager.set_status_reserved(cid, False)
                recorder_manager.set_status_recording(cid, True)
                if verbose:
                    print(f"[LITE] record start: {name} ({plat})")
                started = time.monotonic()
                await startOneShot(channel, plat, loadConfig() or {}, is_user_request=True)
                dur = int(time.monotonic() - started)
                if verbose:
                    print(f"[LITE] record end: {name} ({dur}s)")
            finally:
                recorder_manager.set_status_recording(cid, False)
                recorder_manager.set_status_reserved(cid, True)   # ← 종료 즉시 예약 복원(재탐색 지속)
                recorder_manager.guard_release_start(cid)
                if sem_rec is not None:
                    with contextlib.suppress(Exception):
                        sem_rec.release()
            await asyncio.sleep(max(3, jitter))

        except asyncio.CancelledError:
            raise
        except Exception as e:
            for delay in (15, 30, 60, 120, 300):
                print(f"[LITE][WARN] {name}: {e} → sleep {delay}s")
                await asyncio.sleep(delay)
                break



async def mainAsync(*, verbose: bool = False):
    # 환경/의존성 표시
    printOnce("[LITE] base", str(base_directory))
    try:
        printOnce("[LITE] ffmpeg", getFFmpeg())
    except Exception as e:
        print(f"[LITE][ERROR] FFmpeg 경로 확인 실패: {e}")
    try:
        printOnce("[LITE] ytarchive", getYtarchive())
    except Exception as e:
        print(f"[LITE][ERROR] ytarchive 경로 확인 실패: {e}")
    printOnce("[LITE] ycookie", yloadCookies() or "(none)")

    cfg = _loadLiteConfig()

    # 채널 로드/정규화
    raw = loadChannels() or []
    channels: List[Dict[str, Any]] = []
    for c in raw:
        nc = _normalizeChannel(c)
        if nc:
            channels.append(nc)
    if not channels:
        print("[LITE] no channels")
        return

    # RecorderManager 전역 캐시에 주입(중요)
    RecorderManager.setChannels(channels)

    # 동시성 제어자
    sem_pf  = asyncio.Semaphore(int(cfg.get("max_parallel_preflights", 6)))
    rec_lim = int(cfg.get("max_parallel_recordings", 0) or 0)
    sem_rec = None if rec_lim == 0 else asyncio.Semaphore(rec_lim)

    # 태스크 스폰 유틸(크래시 노출)
    def spawn(coro: asyncio.coroutines) -> asyncio.Task:
        t = asyncio.create_task(coro)
        def _cb(task: asyncio.Task):
            exc = task.exception()
            if exc:
                print(f"[LITE][ERROR] task crashed: {exc!r}")
        t.add_done_callback(_cb)
        return t

    # 상태 핑
    tasks: List[asyncio.Task] = []
    if verbose:
        tasks.append(spawn(_statusPing(cfg, verbose=True)))

    # 채널 워커 (라운드로빈, 채널별 무한루프)
    for ch in channels:
        print(f"[LITE] spawn: {ch.get('platform')} {ch.get('id')}  name={ch.get('name')}")
        tasks.append(spawn(_probeAndAct(ch, cfg, sem_pf, sem_rec, verbose=verbose)))

    # 종료 핸들러
    stop_evt = asyncio.Event()
    def _sig(*_):
        stop_evt.set()
    try:
        loop = asyncio.get_running_loop()
        for s in ("SIGINT", "SIGTERM"):
            if hasattr(signal, s):
                loop.add_signal_handler(getattr(signal, s), _sig)
    except NotImplementedError:
        pass

    await stop_evt.wait()
    for t in tasks:
        t.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def main():
    import argparse
    p = argparse.ArgumentParser(description="recordLITE v1.0.0— non-UI 자동녹화")
    p.add_argument("--verbose", action="store_true", help="상세 로그")
    args = p.parse_args()
    try:
        asyncio.run(mainAsync(verbose=args.verbose))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
