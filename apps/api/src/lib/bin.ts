import fs from 'node:fs';
import path from 'node:path';
import { ROOT } from './paths.js';

// 환경변수 > Windows 개발 환경의 dependent/ 번들 > PATH 순으로 외부 바이너리를 찾는다. 도커에서는 PATH(apt/pip)를 쓴다.
const WIN: Record<string, string[]> = {
  ffmpeg: ['ffmpeg', 'bin', 'ffmpeg.exe'],
  ffprobe: ['ffmpeg', 'bin', 'ffprobe.exe'],
  streamlink: ['streamlink', 'bin', 'streamlink.exe'],
  'yt-dlp': ['yt-dlp', 'yt-dlp.exe'],
  deno: ['yt-dlp', 'deno.exe'],
};

export function bin(name: 'ffmpeg' | 'ffprobe' | 'streamlink' | 'yt-dlp' | 'deno'): string {
  const fromEnv = process.env[name.toUpperCase().replace('-', '_')];
  if (fromEnv) return fromEnv;
  if (process.platform === 'win32') {
    const p = path.join(process.env.RECORDWEB_BIN_ROOT ?? ROOT, 'dependent', ...WIN[name]);
    if (fs.existsSync(p)) return p;
  }
  return name;
}

/** PATH에 실제로 있는지(절대 경로면 파일 존재)를 확인한다. deno처럼 없어도 되는 도구용. */
export function binExists(name: Parameters<typeof bin>[0]): boolean {
  const b = bin(name);
  if (path.isAbsolute(b)) return fs.existsSync(b);
  const exts = process.platform === 'win32' ? ['.exe', '.cmd', ''] : [''];
  return (process.env.PATH ?? '').split(path.delimiter).some((d) => exts.some((e) => fs.existsSync(path.join(d, b + e))));
}
