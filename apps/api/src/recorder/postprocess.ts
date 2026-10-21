import { execFile, spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { promisify } from 'node:util';
import { Config } from '../config/config.js';
import { bin } from '../lib/bin.js';
import { absFromRoot } from '../lib/paths.js';
import { uniqueFilename } from '../lib/text.js';

const execFileP = promisify(execFile);

export interface Probe {
  vcodec: string;
  format: string;
  width: number;
  height: number;
}

export async function probeFile(file: string): Promise<Probe> {
  try {
    const { stdout } = await execFileP(bin('ffprobe'), ['-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=codec_name,width,height:format=format_name', '-of', 'json', file], { timeout: 10000 });
    const j = JSON.parse(stdout);
    return { vcodec: j.streams?.[0]?.codec_name ?? '', format: j.format?.format_name ?? '', width: j.streams?.[0]?.width ?? 0, height: j.streams?.[0]?.height ?? 0 };
  } catch {
    return { vcodec: '', format: '', width: 0, height: 0 };
  }
}

const TARGET: Record<string, [number, number]> = { '1080p': [1920, 1080], '720p': [1280, 720], '480p': [854, 480] };

/** 업스케일은 하지 않는다. 같거나 더 작으면 null(필터 생략). */
export function scaleFilter(res: string, p: Probe): string | null {
  const t = TARGET[res];
  if (!t) return null;
  if (p.width <= 0 || p.height <= 0) return `scale=w='min(iw\\,${t[0]})':h='min(ih\\,${t[1]})':force_original_aspect_ratio=decrease`;
  const s = Math.min(1, t[0] / p.width, t[1] / p.height);
  if (s >= 0.999999) return null;
  const even = (n: number) => Math.max(2, Math.trunc((n * s) / 2) * 2);
  return `scale=w=${even(p.width)}:h=${even(p.height)}`;
}

/** 출력 확장자와 입력 코덱에 맞춰 ffmpeg 인자를 만든다 (스트림복사 또는 소프트웨어 재인코딩). */
export function ffmpegArgs(cfg: Config, input: string, output: string, probe: Probe): string[] {
  const inExt = path.extname(input).toLowerCase();
  const outExt = path.extname(output).toLowerCase();
  const args = ['-y', '-nostdin', '-fflags', '+genpts+discardcorrupt', '-err_detect', 'ignore_err', '-i', input, '-map', '0:v:0?', '-map', '0:a:0?'];

  if (cfg.stream_copy) {
    args.push('-c:v', 'copy', '-c:a', 'copy');
    const fromMp4 = /mp4|mov|ism|m4a/.test(probe.format) || ['h264', 'avc1', 'hevc', 'h265', 'hev1', 'hvc1'].includes(probe.vcodec);
    if (['.ts', '.m2ts', '.mts'].includes(outExt) && fromMp4) {
      if (['h264', 'avc1', ''].includes(probe.vcodec)) args.push('-bsf:v', 'h264_mp4toannexb');
      else args.push('-bsf:v', 'hevc_mp4toannexb');
    }
    if (outExt === '.mp4' && ['.ts', '.m2ts', '.mts'].includes(inExt)) args.push('-bsf:a', 'aac_adtstoasc');
  } else {
    args.push('-c:v', cfg.video_codec, '-preset', cfg.preset);
    const extra = cfg.extra_ffmpeg_options.trim() ? cfg.extra_ffmpeg_options.trim().split(/\s+/) : [];
    const hasVf = extra.some((t) => /^-(vf|filter:v)(=|$)/.test(t));
    const vf = hasVf ? null : scaleFilter(cfg.postprocess_resolution, probe);
    if (vf) args.push('-vf', vf);
    if (cfg.use_bitrate_mode) {
      args.push('-b:v', cfg.video_bitrate);
      if (cfg.vbv_maxrate) args.push('-maxrate', cfg.vbv_maxrate);
      if (cfg.vbv_bufsize) args.push('-bufsize', cfg.vbv_bufsize);
    } else {
      args.push('-crf', String(cfg.video_quality));
    }
    if (cfg.audio_bitrate.toLowerCase() === 'copy') args.push('-c:a', 'copy');
    else args.push('-c:a', cfg.audio_codec, '-b:a', cfg.audio_bitrate);
    args.push(...extra);
  }
  if (outExt === '.mp4') args.push('-movflags', '+faststart');
  args.push(output);
  return args;
}

function runFfmpeg(args: string[]): Promise<void> {
  return new Promise((resolve, reject) => {
    const p = spawn(bin('ffmpeg'), ['-hide_banner', '-loglevel', 'error', ...args], { stdio: ['ignore', 'ignore', 'pipe'] });
    let err = '';
    p.stderr.on('data', (d) => (err = (err + d).slice(-4000)));
    p.on('error', reject);
    p.on('close', (code) => (code === 0 ? resolve() : reject(new Error(`ffmpeg ${code}: ${err.trim().split('\n').slice(-5).join(' | ')}`))));
  });
}

/** 같은 이름이 있으면 번호를 붙여 옮긴다. */
function moveInto(file: string, destDir: string): string {
  fs.mkdirSync(destDir, { recursive: true });
  const { name, ext } = path.parse(file);
  let dest = path.join(destDir, path.basename(file));
  for (let i = 1; fs.existsSync(dest); i++) dest = path.join(destDir, `${name}(${i})${ext}`);
  try {
    fs.renameSync(file, dest);
  } catch {
    fs.copyFileSync(file, dest); // 다른 볼륨 간 이동
    fs.rmSync(file);
  }
  return dest;
}

/**
 * 녹화 후처리: fixed_ 파일 생성 → 검증 → (원본 삭제) → (fixed_ 접두사 제거) → (이동).
 * 실패하면 원본을 남기고 null을 반환한다. 성공하면 최종 경로.
 */
export async function postProcess(input: string, cfg: Config, log: (m: string) => void): Promise<string | null> {
  const dir = path.dirname(input);
  const base = path.basename(input);
  let outBase = base.startsWith('fixed_') ? base : `fixed_${base}`;

  if (!cfg.stream_copy && cfg.postprocess_resolution !== 'source') {
    // 실제로 다운스케일될 때만 파일명의 해상도 태그를 바꾼다
    const th = Number(cfg.postprocess_resolution.slice(0, -1));
    const p = await probeFile(input);
    if (p.height > th) outBase = outBase.replace(/(2160|1440|1080|720|480)p(\d{2,3})?(?=\.[^.]+$)/, `${cfg.postprocess_resolution}$2`);
  }
  const output = path.join(dir, uniqueFilename(dir, outBase));

  try {
    await runFfmpeg(ffmpegArgs(cfg, input, output, await probeFile(input)));
  } catch (e) {
    log(`[POST][FAIL] ${base}: ${(e as Error).message}`);
    fs.rmSync(output, { force: true });
    return null;
  }
  if (!fs.existsSync(output) || fs.statSync(output).size === 0) {
    log(`[POST][FAIL] 출력 파일이 없거나 0KB입니다: ${output}. 원본을 유지합니다.`);
    return null;
  }

  let result = output;
  try {
    if (cfg.deleteAfterPostProcessing) fs.rmSync(input, { force: true });
    if (cfg.removeFixedPrefix) {
      const renamed = path.join(dir, path.basename(output).replace('fixed_', ''));
      // 원본을 지우지 않은 경우 같은 이름이 있을 수 있다 — 덮어쓰지 않고 fixed_ 이름을 유지한다.
      if (!fs.existsSync(renamed)) {
        fs.renameSync(output, renamed);
        result = renamed;
      }
    }
    if (cfg.moveAfterProcessingEnabled && cfg.moveAfterProcessing) result = moveInto(result, absFromRoot(cfg.moveAfterProcessing));
  } catch (e) {
    log(`[POST][FAIL] 파일 정리 단계 오류: ${(e as Error).message}`);
    return null;
  }
  log(`[POST][OK] ${path.basename(result)}`);
  return result;
}

export { moveInto };
