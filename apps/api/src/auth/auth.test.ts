import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { expect, it, vi } from 'vitest';

async function fresh() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'rw-auth-'));
  fs.mkdirSync(path.join(root, 'json'));
  vi.stubEnv('RECORDWEB_ROOT', root);
  vi.resetModules();
  const { AuthService } = await import('./auth.service.js');
  const auth = new AuthService();
  const asReq = (token: string | null) => ({ headers: { cookie: token ? `rw_session=${token}` : '' } });
  return { auth, asReq, root };
}

it('계정이 없으면 설정이 필요하고, 만든 뒤에는 다시 만들 수 없다', async () => {
  const { auth } = await fresh();
  expect(auth.needsSetup()).toBe(true);
  expect(() => auth.setup('ab', 'longenough1', 'ip')).toThrow(); // 아이디가 너무 짧다
  expect(() => auth.setup('owner', 'short', 'ip')).toThrow(); // 비밀번호가 너무 짧다
  auth.setup('owner', 'longenough1', 'ip');
  expect(auth.needsSetup()).toBe(false);
  expect(() => auth.setup('other', 'longenough1', 'ip')).toThrow();
});

it('로그인 토큰은 검증되고, 변조하거나 모든 기기 로그아웃을 하면 무효가 된다', async () => {
  const { auth, asReq } = await fresh();
  auth.setup('owner', 'longenough1', 'ip');
  const token = auth.login('owner', 'longenough1', 'ip')!;
  expect(auth.user(asReq(token))).toBe('owner');
  expect(auth.user(asReq(token.slice(0, -2) + 'xx'))).toBeNull();
  expect(auth.user(asReq(null))).toBeNull();
  auth.logoutAll('ip');
  expect(auth.user(asReq(token))).toBeNull();
});

it('틀린 비밀번호는 null, 5번 틀리면 잠기고 비밀번호는 평문으로 저장되지 않는다', async () => {
  const { auth, root } = await fresh();
  auth.setup('owner', 'longenough1', 'ip');
  for (let i = 0; i < 5; i++) expect(auth.login('owner', 'wrong-pass', '1.2.3.4')).toBeNull();
  expect(() => auth.login('owner', 'longenough1', '1.2.3.4')).toThrow(/너무 많습니다/);
  expect(auth.login('owner', 'longenough1', '5.6.7.8')).not.toBeNull(); // 다른 IP는 영향 없음
  expect(fs.readFileSync(path.join(root, 'json', 'login.json'), 'utf8')).not.toContain('longenough1');
});

it('비밀번호를 바꾸면 이전 세션은 끊기고 새 세션은 유효하다', async () => {
  const { auth, asReq } = await fresh();
  auth.setup('owner', 'longenough1', 'ip');
  const old = auth.login('owner', 'longenough1', 'ip')!;
  expect(() => auth.changePassword('wrong-pass', 'brandnew-pass', 'ip')).toThrow();
  const next = auth.changePassword('longenough1', 'brandnew-pass', 'ip');
  expect(auth.user(asReq(old))).toBeNull();
  expect(auth.user(asReq(next))).toBe('owner');
  expect(auth.login('owner', 'brandnew-pass', 'ip')).not.toBeNull();
});

it('계정 파일이 손상되면 .bak 복구나 재설정 없이 막힌다', async () => {
  const { auth, root } = await fresh();
  auth.setup('owner', 'longenough1', 'ip');
  fs.writeFileSync(path.join(root, 'json', 'login.json'), '{ 깨짐');
  fs.writeFileSync(path.join(root, 'json', 'login.json.bak'), JSON.stringify({ secret_key: 'x', username: null, password: null }));
  expect(() => auth.needsSetup()).toThrow();
});

it('계정 파일은 소유자만 읽을 수 있게 저장한다', async () => {
  if (process.platform === 'win32') return; // 윈도우는 POSIX 권한이 없다
  const { auth, root } = await fresh();
  auth.setup('owner', 'longenough1', 'ip');
  expect(fs.statSync(path.join(root, 'json', 'login.json')).mode & 0o077).toBe(0);
});
