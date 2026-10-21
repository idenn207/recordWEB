import { describe, expect, it } from 'vitest';
import { resolveQuality } from './chzzk.js';

const playback = JSON.stringify({
  media: [
    {
      encodingTrack: [
        { encodingTrackId: '1080p', videoHeight: '1080', videoFrameRate: '60.0' },
        { encodingTrackId: '720p', videoHeight: '720', videoFrameRate: '30' },
        { encodingTrackId: '480p', videoHeight: '480' },
      ],
    },
  ],
});

describe('resolveQuality', () => {
  it('best는 가장 높은 트랙', () => {
    expect(resolveQuality('best', playback)).toMatchObject({ recordQuality: '1080p', frameRate: '60', resolvedQuality: 'best', availableQualities: ['480p', '720p', '1080p'] });
  });

  it('정확히 있는 라벨은 그대로', () => {
    expect(resolveQuality('720p', playback)).toMatchObject({ recordQuality: '720p', frameRate: '30', resolvedQuality: '720p' });
  });

  it('없는 라벨은 그 이하 중 가장 높은 트랙으로', () => {
    expect(resolveQuality('900p', playback)).toMatchObject({ recordQuality: '720p', resolvedQuality: '720p' });
  });

  it('모든 트랙보다 낮게 요청하면 best로 폴백', () => {
    expect(resolveQuality('144p', playback)).toMatchObject({ recordQuality: '1080p', resolvedQuality: 'best' });
  });

  it('파싱 실패는 알 수 없음으로 두고 요청값을 유지', () => {
    expect(resolveQuality('720p', 'not json')).toMatchObject({ recordQuality: '알 수 없는 품질', resolvedQuality: '720p', availableQualities: [] });
  });
});
