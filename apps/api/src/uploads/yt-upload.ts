import fs from 'node:fs';
import path from 'node:path';
import { Channel } from '../config/config.js';
import { absFromRoot } from '../lib/paths.js';

export const EXTS: Record<string, string> = { '.ts': 'video/mp2t', '.mp4': 'video/mp4' };

export interface UploadSettings {
  pool: number;
  rate_mbps: number;
  scan_interval_sec: number;
  stable_sec: number;
  max_sec: number;
  privacy: 'unlisted' | 'private' | 'public';
  tags: string[];
  description: string;
  auto_since: string;
}

export const DEFAULT_UPLOAD_SETTINGS: Omit<UploadSettings, 'auto_since'> = {
  pool: 3,
  rate_mbps: 120,
  scan_interval_sec: 300,
  stable_sec: 300,
  max_sec: 12 * 3600 - 600, // YouTube 길이 상한 12시간 (여유 10분)
  privacy: 'unlisted',
  tags: ['#스텔라이브'],
  description: '스텔라이브 개인용 다시보기 채널입니다.\n\n[유니버스]\n아카네 리제 : https://www.youtube.com/@akanelize\n\n[클리셰]\n하나코 나나 : https://www.youtube.com/@hanako_nana',
};

export interface UploadState {
  path?: string; // 수동 큐에 넣은 파일의 전체 경로
  session?: string;
  video_id?: string;
  privacy?: string;
  playlisted?: boolean;
}

/** ('fixed_' 접두사, 이름, 확장자) */
export function splitName(fn: string): { pre: string; name: string; ext: string } {
  const ext = path.extname(fn);
  const stem = fn.slice(0, fn.length - ext.length);
  const pre = stem.startsWith('fixed_') ? 'fixed_' : '';
  return { pre, name: stem.slice(pre.length), ext };
}

/** 'YYYY MM DD 제목' (YouTube 제목 100자 제한). 분할 조각은 (1부), (2부)가 붙는다. */
export function titleOf(fn: string, names: Set<string>): string {
  const { pre, ext } = splitName(fn);
  let { name } = splitName(fn);
  let part = '';
  const m = /^(.*) \((\d+)\)$/.exec(name);
  if (m) {
    name = m[1];
    part = ` (${Number(m[2]) + 1}부)`;
  } else if (names.has(`${pre}${name} (1)${ext}`)) {
    part = ' (1부)';
  }
  const d = /^\[(\d{4})-(\d\d)-(\d\d)\] (.*)$/s.exec(name);
  const t = ((d ? `${d[1]} ${d[2]} ${d[3]} ${d[4]}` : name) + part).replace(/[<>]/g, '');
  return t.length <= 100 ? t : t.slice(0, 99) + '…';
}

export const recDate = (fn: string) => /\[(\d{4}-\d\d-\d\d)\]/.exec(fn)?.[1] ?? null;

export const playlistOf = (fn: string, channels: Channel[]) => channels.find((c) => c.name && fn.includes(c.name))?.yt_playlist_id || null;

export function isDone(fn: string, st: UploadState | undefined, channels: Channel[]): boolean {
  return Boolean(st?.video_id) && (Boolean(st?.playlisted) || !playlistOf(fn, channels));
}

/** 이번 스캔에서 올릴 파일 {전체 경로}. 자동(채널 설정) + 수동 큐(state.path). */
export function selectCandidates(
  channels: Channel[],
  state: Record<string, UploadState>,
  busy: (p: string) => boolean,
  s: Pick<UploadSettings, 'auto_since' | 'stable_sec'>,
  now = Date.now(),
): Set<string> {
  const out = new Set<string>();
  const ok = (p: string) => {
    try {
      const st = fs.statSync(p);
      return st.isFile() && !busy(p) && now - st.mtimeMs >= s.stable_sec * 1000;
    } catch {
      return false;
    }
  };
  for (const ch of channels) {
    if (ch.platform !== 'chzzk' || !ch.yt_auto_upload) continue;
    const dir = absFromRoot(ch.output_dir);
    let names: string[];
    try {
      names = fs.readdirSync(dir);
    } catch {
      continue;
    }
    const set = new Set(names);
    for (const fn of names) {
      const { pre, ext } = splitName(fn);
      if (!(ext.toLowerCase() in EXTS) || fn.startsWith('_') || !ch.name || !fn.includes(ch.name)) continue;
      if (!pre && set.has('fixed_' + fn)) continue; // fixed_ 변환본이 있으면 그쪽만 올린다
      if ((recDate(fn) ?? '') >= s.auto_since && ok(path.join(dir, fn))) out.add(path.join(dir, fn));
    }
  }
  for (const st of Object.values(state)) if (st.path && !st.video_id && ok(st.path)) out.add(st.path);
  return out;
}
