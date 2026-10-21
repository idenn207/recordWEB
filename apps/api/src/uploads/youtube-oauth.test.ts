import { afterEach, describe, expect, it, vi } from 'vitest';
import { YoutubeOAuth } from './youtube-oauth.js';

const client = { client_id: 'test-client', client_secret: 'test-secret' };
const origin = 'http://localhost:5081';
afterEach(() => vi.unstubAllGlobals());

describe('YouTube 재인증', () => {
  it('LAN HTTP 콜백은 거부하고 localhost에 offline 동의와 PKCE를 요청한다', () => {
    const oauth = new YoutubeOAuth();
    expect(() => oauth.start('http://192.168.0.10:5080', client)).toThrow('HTTPS');
    const result = oauth.start(origin, client);
    const url = new URL(result.url);
    expect(url.origin).toBe('https://accounts.google.com');
    expect(url.searchParams.get('access_type')).toBe('offline');
    expect(url.searchParams.get('prompt')).toBe('consent');
    expect(url.searchParams.get('code_challenge_method')).toBe('S256');
    expect(url.searchParams.get('redirect_uri')).toBe(origin + '/api/uploads/oauth/callback');
    expect(result.url).not.toContain(client.client_secret);
  });

  it('올바른 브라우저의 일회용 state로만 교환하고 새 refresh token을 저장한다', async () => {
    const oauth = new YoutubeOAuth();
    const { state } = oauth.start(origin, client);
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ refresh_token: 'new', scope: 'https://www.googleapis.com/auth/youtube' })));
    vi.stubGlobal('fetch', fetcher);
    const save = vi.fn();
    await expect(oauth.complete(state, 'other-browser', 'code', undefined, save)).rejects.toThrow('인증');
    expect(fetcher).not.toHaveBeenCalled();
    await oauth.complete(state, state, 'code', undefined, save);
    expect(save).toHaveBeenCalledWith(JSON.stringify({ ...client, refresh_token: 'new', token_uri: 'https://oauth2.googleapis.com/token' }));
    const params = fetcher.mock.calls[0][1].body as URLSearchParams;
    expect(params.get('code_verifier')).toBeTruthy();
    expect(params.get('redirect_uri')).toBe(origin + '/api/uploads/oauth/callback');
    await expect(oauth.complete(state, state, 'code', undefined, save)).rejects.toThrow('인증');
  });

  it('취소·만료·토큰 누락·교환 실패 때 기존 토큰을 유지한다', async () => {
    const oauth = new YoutubeOAuth();
    const save = vi.fn();
    let result = oauth.start(origin, client);
    await expect(oauth.complete(result.state, result.state, '', 'access_denied', save)).rejects.toThrow('취소');
    result = oauth.start(origin, client);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}')));
    await expect(oauth.complete(result.state, result.state, 'code', undefined, save)).rejects.toThrow('refresh token');
    result = oauth.start(origin, client);
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('secret-error', { status: 400 })));
    await expect(oauth.complete(result.state, result.state, 'code', undefined, save)).rejects.toThrow('Google');
    result = oauth.start(origin, client);
    vi.spyOn(Date, 'now').mockReturnValue(Date.now() + 11 * 60_000);
    await expect(oauth.complete(result.state, result.state, 'code', undefined, save)).rejects.toThrow('인증');
    vi.restoreAllMocks();
    expect(save).not.toHaveBeenCalled();
  });

  it('콜백 origin 변조와 클라이언트 누락을 거부한다', () => {
    const oauth = new YoutubeOAuth();
    for (const bad of ['https://192.168.0.10', 'http://localhost.evil.test', 'http://user@localhost:5081', origin + '/evil', 'null']) {
      expect(() => oauth.start(bad, client)).toThrow();
    }
    expect(() => oauth.start(origin, { client_id: '', client_secret: '' })).toThrow('클라이언트');
  });

  it('내부망에서도 HTTPS 도메인을 콜백으로 사용할 수 있다', () => {
    const { url } = new YoutubeOAuth().start('https://nas.example.com', client);
    expect(new URL(url).searchParams.get('redirect_uri')).toBe('https://nas.example.com/api/uploads/oauth/callback');
  });
});
