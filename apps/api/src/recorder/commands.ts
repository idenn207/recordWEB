import path from 'node:path';
import { Channel } from '../config/config.js';
import { ChzzkCookies } from '../config/store.service.js';
import { LiveMeta } from '../chzzk/chzzk.js';
import { YtMeta, extractorArgs, formatSelector } from '../youtube/youtube.js';
import { bin, binExists } from '../lib/bin.js';
import { formatPattern, safeTitle } from '../lib/text.js';

const UA = process.platform === 'win32' ? 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' : 'Mozilla/5.0 (X11; Linux x86_64)';

/** streamlink 공통 옵션: 쿠키/Referer/Origin/UA 헤더. */
export function streamlinkHeaders(c: ChzzkCookies): string[] {
  const cookie = [c.NID_SES && `NID_SES=${c.NID_SES}`, c.NID_AUT && `NID_AUT=${c.NID_AUT}`].filter(Boolean).join('; ');
  return [
    ...(cookie ? ['--http-header', `Cookie=${cookie}`] : []),
    '--http-header', 'Referer=https://chzzk.naver.com/',
    '--http-header', 'Origin=https://chzzk.naver.com',
    '--http-header', `User-Agent=${UA}`,
  ];
}

export const chzzkUrl = (id: string) => `https://chzzk.naver.com/live/${id}`;

export function chzzkRecordArgs(ch: Channel, meta: LiveMeta, cookies: ChzzkCookies, outputPath: string): string[] {
  return [
    '--ffmpeg-copyts', '--ffmpeg-ffmpeg', bin('ffmpeg'), '--progress=force',
    '--stream-segment-timeout', '15', '--stream-segment-attempts', '12',
    '--hls-segment-queue-threshold', '0', '--stream-timeout', '60',
    ...streamlinkHeaders(cookies),
    chzzkUrl(ch.id), meta.resolvedQuality || ch.quality || 'best', '-o', outputPath,
  ];
}

/** 방송이 실제로 열렸는지 첫 바이트만 받아 보는 프로브. */
export function chzzkProbeArgs(ch: Channel, cookies: ChzzkCookies, timeoutSec: number): string[] {
  return [
    ...streamlinkHeaders(cookies), chzzkUrl(ch.id), 'best', '--stdout',
    '--stream-segment-timeout', '3', '--stream-segment-attempts', '1',
    '--stream-timeout', String(timeoutSec), '--hls-playlist-reload-attempts', '1',
  ];
}

/** 녹화 파일명. 치지직은 제목 금칙문자를 '_', 유튜브는 공백으로 바꾼다. */
export function recordFilename(pattern: string, v: { channelName: string; title: string; startTime: string; quality: string; fps: string; ext: string }, platform: 'chzzk' | 'youtube', now = new Date()): string {
  const p = (n: number) => String(n).padStart(2, '0');
  const recording_time = `${String(now.getFullYear()).slice(2)}${p(now.getMonth() + 1)}${p(now.getDate())}_${p(now.getHours())}${p(now.getMinutes())}${p(now.getSeconds())}`;
  const title = platform === 'youtube' ? safeTitle(v.title.replace(/\s+/g, ' '), ' ').replace(/\s{2,}/g, ' ').trim() : safeTitle(v.title);
  return formatPattern(pattern, {
    recording_time,
    start_time: v.startTime,
    safe_live_title: title,
    channel_name: v.channelName,
    record_quality: v.quality,
    frame_rate: v.fps,
    file_extension: v.ext,
  });
}

/** 유튜브 파일명용 품질/프레임 라벨. 요청값 우선, best일 때만 실측값으로 보정. */
export function ytNameQuality(requested: string, meta: YtMeta): { quality: string; fps: string; ext: string } {
  const q = (requested || 'best').toLowerCase();
  const m = /^(\d+)p(?:60)?$/.exec(q);
  let quality = m ? `${m[1]}p` : 'best';
  let fps = q.endsWith('60') ? 60 : 30;
  if (q === 'best') {
    if (meta.height) quality = `${meta.height}p`;
    if (meta.fps != null) fps = meta.fps >= 59 ? 60 : 30;
  }
  return { quality, fps: String(fps), ext: '.mkv' };
}

export function ytDlpArgs(opts: { url: string; outDir: string; tmpDir: string; outTemplate: string; quality: string; cookieFile: string | null; poToken: string; sabr: boolean }): string[] {
  const args = [
    '--ffmpeg-location', path.dirname(bin('ffmpeg')),
    '--live-from-start', '-f', formatSelector(opts.quality, opts.sabr), '--merge-output-format', 'mkv',
    '--paths', `home:${opts.outDir}`, '--paths', `temp:${opts.tmpDir}`,
    '-o', opts.outTemplate, '--print', 'after_move:__FINAL__:%(filepath)j', '--no-colors',
  ];
  if (opts.cookieFile) args.push('--cookies', opts.cookieFile);
  if (binExists('deno')) args.push('--js-runtimes', `deno:${bin('deno')}`);
  args.push('--extractor-args', extractorArgs(opts.poToken, opts.sabr), opts.url);
  return args;
}
