import { describe, expect, it } from 'vitest';
import { normalizeHandle, normalizeXCookieInput, parseLiveSpaceId, parseXCookies, spaceUrl, toNetscape, xErrorMessage, XError } from './x.js';

describe('normalizeHandle', () => {
  it('@ 접두사와 URL, 공백을 정리한다', () => {
    expect(normalizeHandle('HanayoHiyori')).toBe('@HanayoHiyori');
    expect(normalizeHandle('  @HanayoHiyori ')).toBe('@HanayoHiyori');
    expect(normalizeHandle('https://x.com/HanayoHiyori?s=20')).toBe('@HanayoHiyori');
    expect(normalizeHandle('https://twitter.com/@abc_123/status/1')).toBe('@abc_123');
  });
});

describe('parseXCookies', () => {
  it('한 줄 형식', () => {
    expect(parseXCookies('auth_token=AAA; ct0=BBB; twid=u%3D1')).toEqual({ authToken: 'AAA', ct0: 'BBB' });
  });

  it('Netscape 형식(HttpOnly 접두사 포함)과 다른 도메인 무시', () => {
    const t = ['# Netscape HTTP Cookie File', '#HttpOnly_.x.com\tTRUE\t/\tTRUE\t0\tauth_token\tAAA', '.x.com\tTRUE\t/\tTRUE\t0\tct0\tBBB', '.example.com\tTRUE\t/\tTRUE\t0\tauth_token\tZZZ'].join('\n');
    expect(parseXCookies(t)).toEqual({ authToken: 'AAA', ct0: 'BBB' });
  });

  it('둘 중 하나라도 없으면 null (헤더만 있는 기존 xcookie.txt 포함)', () => {
    expect(parseXCookies('auth_token=AAA')).toBeNull();
    expect(parseXCookies('# Netscape HTTP Cookie File')).toBeNull();
    expect(parseXCookies('')).toBeNull();
  });
});

describe('normalizeXCookieInput', () => {
  it('한 줄 형식은 Netscape로 바꾸고, Netscape는 그대로 둔다', () => {
    const converted = normalizeXCookieInput('auth_token=AAA; ct0=BBB');
    expect(converted).toContain('\tauth_token\tAAA');
    expect(parseXCookies(converted)).toEqual({ authToken: 'AAA', ct0: 'BBB' });
    const netscape = toNetscape({ authToken: 'A', ct0: 'B' });
    expect(normalizeXCookieInput(netscape)).toBe(netscape);
  });

  it('필수 쿠키가 없으면 조치 안내가 담긴 예외', () => {
    expect(() => normalizeXCookieInput('auth_token=AAA')).toThrow(/auth_token과 ct0/);
  });
});

describe('parseLiveSpaceId', () => {
  const live = { users: { '123': { user_id: '123', spaces: { live_content: { audiospace: { broadcast_id: '1AbCdEf', is_space_available_for_replay: false } } } } } };

  it('라이브 스페이스의 broadcast_id', () => {
    expect(parseLiveSpaceId(live, '123')).toBe('1AbCdEf');
  });

  it('스페이스가 없으면 null', () => {
    expect(parseLiveSpaceId({ users: { '123': { user_id: '123' } } }, '123')).toBeNull();
    expect(parseLiveSpaceId({}, '123')).toBeNull();
  });

  it('spaces 밖의 broadcast_id(예: 일반 라이브 방송)는 스페이스로 보지 않는다', () => {
    expect(parseLiveSpaceId({ users: { '123': { fleets: { broadcast_id: 'XYZ' } } } }, '123')).toBeNull();
  });

  it('다른 사용자 ID로 응답이 와도 첫 사용자를 본다', () => {
    expect(parseLiveSpaceId(live, '999')).toBe('1AbCdEf');
  });
});

describe('기타', () => {
  it('스페이스 URL', () => {
    expect(spaceUrl('1AbCdEf')).toBe('https://x.com/i/spaces/1AbCdEf');
  });

  it('오류 문구는 다음 행동을 알려 준다', () => {
    expect(xErrorMessage(new XError('no-cookie', ''))).toContain('설정');
    expect(xErrorMessage(new XError('auth', '', 401))).toContain('401');
    expect(xErrorMessage(new XError('auth', '', 401))).toContain('다시 로그인');
  });

  it('사용자 ID 조회 실패는 원인을 단정하지 않고 직접 입력을 안내한다', () => {
    const msg = xErrorMessage(new XError('lookup', '@a 의 사용자 ID를 알아내지 못했습니다. 숫자 사용자 ID를 직접 입력하면 됩니다.'));
    expect(msg).toContain('직접 입력');
    expect(msg).not.toContain('다시 로그인');
  });
});
