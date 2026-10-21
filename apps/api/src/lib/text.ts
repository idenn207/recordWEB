import fs from 'node:fs';
import path from 'node:path';

/** Python str.format 대응: {key} 만 치환하고 모르는 키는 그대로 둔다. */
export function formatPattern(pattern: string, vars: Record<string, string | number>): string {
  return pattern.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

/** 파일명에 못 쓰는 문자를 치환하고 55자로 자른다 (치지직 제목). */
export const safeTitle = (title: string, replacement = '_') =>
  title.replace(/[\r\n]+/g, '').trim().replace(/[\/*?:"<>|+]/g, replacement).slice(0, 55);

/** 같은 이름이 있으면 'name (1).ext' 처럼 번호를 붙인다. */
export function uniqueFilename(dir: string, filename: string): string {
  const { name, ext } = path.parse(filename);
  let candidate = filename;
  for (let i = 1; fs.existsSync(path.join(dir, candidate)); i++) candidate = `${name} (${i})${ext}`;
  return candidate;
}

export function fmtDuration(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(Math.floor(s / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}`;
}

export const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve) => {
    if (signal?.aborted) return resolve();
    const t = setTimeout(done, ms);
    function done() {
      clearTimeout(t);
      signal?.removeEventListener('abort', done);
      resolve();
    }
    signal?.addEventListener('abort', done, { once: true });
  });

/** 채널별로 재탐색 시각이 겹치지 않게 흩뿌리는 결정적 지터 (기존 blake2b 위상과 같은 목적, 해시만 다름). */
export function jitteredWaitMs(channelId: string, baseSec: number, now = Date.now(), anchor = START): number {
  const base = Math.max(10, baseSec);
  const jit = Math.max(1, Math.floor(base * 0.15));
  let h = 0;
  for (const ch of channelId) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  const phase = (h % (2 * jit + 1)) - jit;
  const period = base * 1000;
  const k = Math.floor((now - (anchor + phase * 1000)) / period) + 1;
  return Math.max(1000, anchor + phase * 1000 + k * period - now);
}
const START = Date.now();
