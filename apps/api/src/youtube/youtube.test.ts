import { describe, expect, it } from 'vitest';
import { extractorArgs, formatSelector, liveUrlOf, normalizePoToken, parseLivePage } from './youtube.js';

const page = (micro: object, status = 'OK') =>
  `<script>var ytInitialPlayerResponse = ${JSON.stringify({
    playabilityStatus: { status },
    videoDetails: { videoId: 'abcdefghijk', title: '라이브 제목' },
    microformat: { playerMicroformatRenderer: { category: 'Gaming', liveBroadcastDetails: micro } },
    streamingData: { adaptiveFormats: [{ mimeType: 'video/mp4', height: 1080, fps: 60 }, { mimeType: 'video/webm', qualityLabel: '720p', fps: 30 }, { mimeType: 'audio/mp4' }] },
  })};</script>`;

describe('parseLivePage', () => {
  it('진짜 라이브 중이면 isLive', () => {
    const m = parseLivePage(page({ isLiveNow: true, startTimestamp: '2026-10-22T01:00:00+00:00' }));
    expect(m).toMatchObject({ isLive: true, videoId: 'abcdefghijk', liveTitle: '라이브 제목', category: 'Gaming', fps: 60, height: 1080, watchUrl: 'https://www.youtube.com/watch?v=abcdefghijk' });
  });

  it('endTimestamp가 있거나 LIVE_STREAM_OFFLINE이면 라이브가 아니다', () => {
    expect(parseLivePage(page({ isLiveNow: true, endTimestamp: 'x' })).isLive).toBe(false);
    expect(parseLivePage(page({ isLiveNow: true }, 'LIVE_STREAM_OFFLINE')).isLive).toBe(false);
  });

  it('플레이어 JSON이 없으면 정보 없음', () => {
    expect(parseLivePage('<html></html>')).toMatchObject({ isLive: false, liveTitle: '정보 없음', videoId: null });
  });
});

describe('yt-dlp 옵션', () => {
  it('채널 식별자별 live URL', () => {
    expect(liveUrlOf('UC123')).toBe('https://www.youtube.com/channel/UC123/live');
    expect(liveUrlOf('@h')).toBe('https://www.youtube.com/@h/live');
    expect(liveUrlOf('h')).toBe('https://www.youtube.com/@h/live');
  });

  it('품질 선택자', () => {
    expect(formatSelector('best')).toBe('bv*+ba/b');
    expect(formatSelector('1080p60')).toBe('bv*[height<=1080][fps<=60]+ba/b[height<=1080][fps<=60]/bv*+ba/b');
    expect(formatSelector('720p', true)).toContain('protocol=sabr');
    expect(formatSelector('weird')).toBe('bv*+ba/b');
  });

  it('PO 토큰은 mweb.gvs로 보정하고 클라이언트를 추론', () => {
    expect(normalizePoToken('abc')).toEqual({ token: 'mweb.gvs+abc', clients: ['mweb'] });
    expect(normalizePoToken('web.gvs+x; ios.gvs+y')).toEqual({ token: 'web.gvs+x,ios.gvs+y', clients: ['web', 'ios'] });
    expect(extractorArgs('', false)).toBe('youtube:player-client=default,mweb');
    expect(extractorArgs('web.gvs+x', false)).toBe('youtube:player-client=web;po_token=web.gvs+x');
  });
});
