import { describe, expect, it } from 'vitest';
import { normalizeChannels, normalizeConfig } from './config.js';

describe('normalizeConfig', () => {
  it('빈 입력은 기본값, 모르는 키는 보존한다', () => {
    const c = normalizeConfig({ legacyGpuKey: 'keep' }) as unknown as Record<string, unknown>;
    expect(c.recheckInterval).toBe(60);
    expect(c.legacyGpuKey).toBe('keep');
  });

  it('타입을 보정하고 recheckInterval은 10초 이상', () => {
    const c = normalizeConfig({ recheckInterval: '5', stream_copy: 'false', postprocess_resolution: '4k', fileManagerRoots: ' /a ' });
    expect(c.recheckInterval).toBe(10);
    expect(c.stream_copy).toBe(false);
    expect(c.postprocess_resolution).toBe('source');
    expect(c.fileManagerRoots).toEqual(['/a']);
  });

  it('fileManagerEnabled는 loginMode와 무관하다', () => {
    expect(normalizeConfig({ loginMode: false, fileManagerEnabled: true }).fileManagerEnabled).toBe(true);
  });
});

describe('normalizeChannels', () => {
  it('잘못된 항목을 버리고 (platform,id) 중복은 먼저 나온 것을 남긴다', () => {
    const out = normalizeChannels([
      { platform: 'chzzk', id: 'a', name: '첫째' },
      { platform: 'chzzk', id: 'a', name: '중복' },
      { platform: 'twitch', id: 'b' },
      { platform: 'chzzk', id: '' },
    ]);
    expect(out.map((c) => c.name)).toEqual(['첫째']);
  });

  it('유튜브는 .mkv 고정, 같이보기 끔, 태그 중복 제거', () => {
    const [y] = normalizeChannels([{ platform: 'youtube', id: '@x', name: 'y', extension: '.ts', recordWatchParty: true }]);
    expect(y.extension).toBe('.mkv');
    expect(y.recordWatchParty).toBe(false);
    const [c] = normalizeChannels([{ platform: 'chzzk', id: 'c', name: 'n', watchPartyExcludeTags: 'LCK, lck , VCT' }]);
    expect(c.watchPartyExcludeTags).toEqual(['LCK', 'VCT']);
  });

  it('업로드 필드는 있을 때만 유지한다', () => {
    const [c] = normalizeChannels([{ platform: 'chzzk', id: 'c', name: 'n', yt_auto_upload: 'true', yt_playlist_id: ' PL1 ' }]);
    expect(c.yt_auto_upload).toBe(true);
    expect(c.yt_playlist_id).toBe('PL1');
    expect('yt_auto_upload' in normalizeChannels([{ platform: 'chzzk', id: 'd', name: 'n' }])[0]).toBe(false);
  });
});
