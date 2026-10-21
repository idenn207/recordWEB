import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { Channel } from '../config/config.js';
import { isDone, playlistOf, selectCandidates, splitName, titleOf, UploadState } from './yt-upload.js';

describe('titleOf', () => {
  it('날짜를 YYYY MM DD로 바꾸고 fixed_ 접두사와 확장자를 뗀다', () => {
    expect(titleOf('fixed_[2026-09-09] 하나코 나나 게임.ts', new Set())).toBe('2026 09 09 하나코 나나 게임');
  });

  it('분할 조각은 1부, 2부', () => {
    const names = new Set(['[2026-01-02] t.ts', '[2026-01-02] t (1).ts']);
    expect(titleOf('[2026-01-02] t.ts', names)).toBe('2026 01 02 t (1부)');
    expect(titleOf('[2026-01-02] t (1).ts', names)).toBe('2026 01 02 t (2부)');
  });

  it('100자 제한과 < > 제거', () => {
    expect(titleOf('[2026-01-02] ' + 'ㅋ'.repeat(300) + '.ts', new Set())).toHaveLength(100);
    expect(titleOf('[2026-01-02] <a>.ts', new Set())).toBe('2026 01 02 a');
  });

  it('splitName', () => {
    expect(splitName('fixed_a.ts')).toEqual({ pre: 'fixed_', name: 'a', ext: '.ts' });
    expect(splitName('a.mp4')).toEqual({ pre: '', name: 'a', ext: '.mp4' });
  });
});

describe('selectCandidates', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'rw-up-'));
  const dir = path.join(root, 'chzzk');
  fs.mkdirSync(path.join(dir, '_over12h'), { recursive: true });
  const old = new Date(Date.now() - 3600_000);
  const mk = (name: string, aged = true) => {
    const p = path.join(dir, name);
    fs.writeFileSync(p, 'x');
    if (aged) fs.utimesSync(p, old, old);
    return p;
  };
  const want = mk('fixed_[2026-10-22] 유니 방송.ts');
  mk('[2026-10-22] 유니 방송.ts'); // fixed_ 변환본이 있어 제외
  mk('fixed_[2026-09-01] 유니 옛날.ts'); // auto_since 이전
  mk('fixed_[2026-10-23] 다른사람 방송.ts'); // 채널명 불일치
  mk('fixed_[2026-10-24] 유니 방금.ts', false); // mtime 불안정
  const ch: Channel = { platform: 'chzzk', id: 'c', name: '유니', output_dir: dir, quality: 'best', extension: '.ts', record_enabled: true, recordWatchParty: false, watchPartyExcludeTags: [], yt_auto_upload: true };
  const s = { auto_since: '2026-10-01', stable_sec: 300 };

  it('자동: 켜진 채널의 안정된 최근 파일만', () => {
    expect(selectCandidates([ch], {}, () => false, s)).toEqual(new Set([want]));
  });

  it('꺼진 채널과 잠긴 파일은 제외', () => {
    expect(selectCandidates([{ ...ch, yt_auto_upload: false }], {}, () => false, s).size).toBe(0);
    expect(selectCandidates([ch], {}, (p) => p === want, s).size).toBe(0);
  });

  it('수동 큐는 채널 설정과 무관하고, 이미 올린 건 제외', () => {
    const manual = mk('수동.ts');
    const state: Record<string, UploadState> = { '수동.ts': { path: manual }, 'done.ts': { path: want, video_id: 'v' } };
    expect(selectCandidates([], state, () => false, s)).toEqual(new Set([manual]));
  });
});

describe('isDone', () => {
  const ch = { name: '유니', yt_playlist_id: 'PL1' } as Channel;
  it('재생목록이 있는 채널은 playlisted까지 끝나야 완료', () => {
    expect(playlistOf('x 유니 y.ts', [ch])).toBe('PL1');
    expect(isDone('x 유니 y.ts', { video_id: 'v' }, [ch])).toBe(false);
    expect(isDone('x 유니 y.ts', { video_id: 'v', playlisted: true }, [ch])).toBe(true);
    expect(isDone('x 다른 y.ts', { video_id: 'v' }, [ch])).toBe(true);
    expect(isDone('x 유니 y.ts', {}, [ch])).toBe(false);
  });
});
