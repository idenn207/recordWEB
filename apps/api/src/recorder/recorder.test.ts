import { describe, expect, it } from 'vitest';
import { DEFAULT_CONFIG } from '../config/config.js';
import { ffmpegArgs, scaleFilter } from './postprocess.js';
import { recordFilename, streamlinkHeaders, ytNameQuality } from './commands.js';

const probe = { vcodec: 'h264', format: 'mpegts', width: 1920, height: 1080 };

describe('recordFilename', () => {
  const pattern = DEFAULT_CONFIG.filenamePattern;
  const base = { channelName: '유니', title: '방송/제목:1', startTime: '2026-10-22', quality: '1080p', fps: '60', ext: '.ts' };

  it('기존 Python 패턴과 같은 결과', () => {
    expect(recordFilename(pattern, base, 'chzzk')).toBe('[2026-10-22] 유니 방송_제목_1 1080p60.ts');
  });

  it('유튜브는 금칙문자를 공백으로 바꾸고 공백을 합친다', () => {
    expect(recordFilename(pattern, { ...base, title: '방송/  제목:1', ext: '.mkv' }, 'youtube')).toBe('[2026-10-22] 유니 방송 제목 1 1080p60.mkv');
  });

  it('recording_time은 YYMMDD_HHMMSS', () => {
    expect(recordFilename('{recording_time}', base, 'chzzk', new Date(2026, 9, 22, 3, 4, 5))).toBe('261022_030405');
  });
});

describe('ytNameQuality', () => {
  it('요청값 우선, best일 때만 실측으로 보정', () => {
    const meta = { height: 1440, fps: 60 } as never;
    expect(ytNameQuality('720p60', meta)).toEqual({ quality: '720p', fps: '60', ext: '.mkv' });
    expect(ytNameQuality('best', meta)).toEqual({ quality: '1440p', fps: '60', ext: '.mkv' });
    expect(ytNameQuality('best', { height: null, fps: null } as never)).toEqual({ quality: 'best', fps: '30', ext: '.mkv' });
  });
});

describe('streamlinkHeaders', () => {
  it('쿠키가 없으면 Cookie 헤더를 보내지 않는다', () => {
    expect(streamlinkHeaders({}).join(' ')).not.toContain('Cookie=');
    expect(streamlinkHeaders({ NID_AUT: 'a', NID_SES: 'b' }).join(' ')).toContain('Cookie=NID_SES=b; NID_AUT=a');
  });
});

describe('ffmpegArgs', () => {
  it('스트림복사 ts→ts: 코덱을 모르면 필터 없이 copy, h264면 기존처럼 annexb 필터(이미 Annex B면 통과)', () => {
    const a = ffmpegArgs(DEFAULT_CONFIG, 'in.ts', 'out.ts', { ...probe, vcodec: '' });
    expect(a).toContain('copy');
    expect(a).not.toContain('-bsf:v');
    expect(a.at(-1)).toBe('out.ts');
    expect(ffmpegArgs(DEFAULT_CONFIG, 'in.ts', 'out.ts', probe)).toEqual(expect.arrayContaining(['-bsf:v', 'h264_mp4toannexb']));
  });

  it('mp4 계열 입력을 ts로 복사할 때 h264_mp4toannexb', () => {
    expect(ffmpegArgs(DEFAULT_CONFIG, 'in.mp4', 'out.ts', { ...probe, format: 'mov,mp4' })).toEqual(expect.arrayContaining(['-bsf:v', 'h264_mp4toannexb']));
  });

  it('ts→mp4는 aac_adtstoasc와 faststart', () => {
    const a = ffmpegArgs(DEFAULT_CONFIG, 'in.ts', 'out.mp4', probe);
    expect(a).toEqual(expect.arrayContaining(['-bsf:a', 'aac_adtstoasc', '-movflags', '+faststart']));
  });

  it('재인코딩: 비트레이트 모드와 CRF 모드', () => {
    const enc = { ...DEFAULT_CONFIG, stream_copy: false, vbv_maxrate: '16000k', extra_ffmpeg_options: '-bf 3' };
    const a = ffmpegArgs(enc, 'in.ts', 'out.ts', probe);
    expect(a).toEqual(expect.arrayContaining(['-c:v', 'libx264', '-b:v', '1000k', '-maxrate', '16000k', '-c:a', 'aac', '-b:a', '192k', '-bf', '3']));
    const crf = ffmpegArgs({ ...enc, use_bitrate_mode: false }, 'in.ts', 'out.ts', probe);
    expect(crf).toEqual(expect.arrayContaining(['-crf', '33']));
    expect(crf).not.toContain('-b:v');
  });

  it('extra에 -vf가 있으면 해상도 스케일을 붙이지 않는다', () => {
    const a = ffmpegArgs({ ...DEFAULT_CONFIG, stream_copy: false, postprocess_resolution: '720p', extra_ffmpeg_options: '-vf yadif' }, 'in.ts', 'out.ts', probe);
    expect(a.filter((x) => x === '-vf')).toHaveLength(1);
  });
});

describe('scaleFilter', () => {
  it('다운스케일만 하고 짝수로 맞춘다', () => {
    expect(scaleFilter('720p', probe)).toBe('scale=w=1280:h=720');
    expect(scaleFilter('1080p', probe)).toBeNull(); // 같으면 생략
    expect(scaleFilter('1080p', { ...probe, width: 1280, height: 720 })).toBeNull(); // 업스케일 금지
    expect(scaleFilter('480p', { ...probe, width: 1000, height: 563 })).toBe('scale=w=852:h=478');
    expect(scaleFilter('source', probe)).toBeNull();
  });
});
