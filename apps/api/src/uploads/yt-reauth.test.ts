import fs from 'node:fs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { readJson, writeJson } from '../lib/json-store.js';
import { YtUploadService } from './yt-upload.service.js';

vi.mock('../lib/json-store.js', () => ({ readJson: vi.fn(), writeJson: vi.fn() }));
const existing = { client_id: 'test-client', client_secret: 'test-secret', refresh_token: 'old', token_uri: 'https://oauth2.googleapis.com/token' };
let service: YtUploadService;
beforeEach(() => {
  vi.mocked(readJson).mockImplementation((_file, fallback) => String(_file).endsWith('yt_token.json') ? { ...existing } : fallback);
  vi.spyOn(fs, 'chmodSync').mockImplementation(() => undefined);
  service = new YtUploadService({} as never, {} as never, {} as never);
});
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.clearAllMocks(); });
const google = (body: unknown, status = 200) => {
  const mock = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }));
  vi.stubGlobal('fetch', mock);
  return mock;
};

describe('refresh token 재인증', () => {
  it('Google에서 확인한 뒤 기존 클라이언트를 유지하며 저장한다', async () => {
    const fetcher = google({ access_token: 'access', expires_in: 3600 });
    await expect(service.reauthenticate('  new-refresh  ')).resolves.toEqual({ ok: true });
    expect(fetcher.mock.calls[0][0]).toBe('https://oauth2.googleapis.com/token');
    const body = fetcher.mock.calls[0][1].body as URLSearchParams;
    expect(Object.fromEntries(body)).toEqual({ client_id: 'test-client', client_secret: 'test-secret', refresh_token: 'new-refresh', grant_type: 'refresh_token' });
    expect(writeJson).toHaveBeenCalledWith(expect.stringContaining('yt_token.json'), { ...existing, refresh_token: 'new-refresh' });
  });

  it.each(['', '   ', null, {}, ['token']])('잘못된 입력 %j는 Google에 보내지 않는다', async (value) => {
    const fetcher = google({});
    await expect(service.reauthenticate(value as string)).rejects.toThrow('refresh token');
    expect(fetcher).not.toHaveBeenCalled();
    expect(writeJson).not.toHaveBeenCalled();
  });

  it('기존 클라이언트가 없으면 전체 JSON 등록을 안내한다', async () => {
    vi.mocked(readJson).mockReturnValue(null);
    await expect(service.reauthenticate('new')).rejects.toThrow('전체 JSON');
    expect(writeJson).not.toHaveBeenCalled();
  });

  it.each([400, 401, 500])('Google HTTP %i 오류 때 기존 토큰을 보존하고 응답을 숨긴다', async (status) => {
    google({ error: 'invalid_grant', error_description: 'sensitive-example' }, status);
    await expect(service.reauthenticate('new')).rejects.toThrow(/재인증|Google/);
    expect(writeJson).not.toHaveBeenCalled();
  });

  it.each([{}, { access_token: 'access' }, { access_token: 'access', expires_in: -1 }])('불완전한 성공 응답 %j는 저장하지 않는다', async (response) => {
    google(response);
    await expect(service.reauthenticate('new')).rejects.toThrow('Google');
    expect(writeJson).not.toHaveBeenCalled();
  });

  it('네트워크 오류를 숨기고 기존 토큰을 유지한다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('sensitive-example')));
    await expect(service.reauthenticate('new')).rejects.toThrow('Google');
    expect(writeJson).not.toHaveBeenCalled();
  });
});
