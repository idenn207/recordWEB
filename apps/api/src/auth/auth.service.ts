import { Injectable } from '@nestjs/common';
import type { Request, Response } from 'express';
import crypto from 'node:crypto';
import fs from 'node:fs';
import { readJson, writeJson } from '../lib/json-store.js';
import { jsonPath } from '../lib/paths.js';

const LOGIN = jsonPath('login.json');
const AUDIT = jsonPath('audit.json');
export const COOKIE = 'rw_session';
const SESSION_SEC = 7 * 24 * 3600;
const MAX_FAILS = 5;
const WINDOW_MS = 15 * 60_000;

interface Account {
  username: string | null;
  password: string | null; // scrypt$salt$hash (base64url)
  secret_key: string;
  epoch?: number; // 올리면 발급된 모든 세션이 무효가 된다
}

export interface AuditEntry {
  at: string;
  type: 'login' | 'login-fail' | 'logout' | 'setup' | 'password' | 'logout-all' | 'secrets' | 'config';
  ip: string;
  detail?: string;
}

export const hashPassword = (pw: string, salt = crypto.randomBytes(16)) => `scrypt$${salt.toString('base64url')}$${crypto.scryptSync(pw, salt, 32).toString('base64url')}`;

/** 예전 Python 앱(werkzeug)이 저장한 해시: scrypt:N:r:p$솔트$해시(hex, 64바이트). 기존 계정으로 그대로 로그인하게 한다. */
const isLegacy = (stored: string) => stored.startsWith('scrypt:');

function verifyLegacy(pw: string, stored: string): boolean {
  const [method, salt, want] = stored.split('$');
  const [, n, r, p] = method.split(':').map((v, i) => (i ? Number(v) : v)) as [string, number, number, number];
  if (!salt || !want || !n || !r || !p) return false;
  const got = crypto.scryptSync(pw, salt, want.length / 2, { N: n, r, p, maxmem: 132 * n * r * p });
  const w = Buffer.from(want, 'hex');
  return got.length === w.length && crypto.timingSafeEqual(got, w);
}

export function verifyPassword(pw: string, stored: string): boolean {
  if (isLegacy(stored)) return verifyLegacy(pw, stored);
  const [alg, salt, want] = stored.split('$');
  if (alg !== 'scrypt' || !salt || !want) return false;
  const got = crypto.scryptSync(pw, Buffer.from(salt, 'base64url'), 32);
  const w = Buffer.from(want, 'base64url');
  return got.length === w.length && crypto.timingSafeEqual(got, w);
}

const DUMMY_HASH = hashPassword('dummy-password-for-timing');

const sign = (key: string, body: string) => crypto.createHmac('sha256', key).update(body).digest('base64url');

export const clientIp = (req: Request) => req.socket.remoteAddress?.replace(/^::ffff:/, '') ?? '';

export class TooMany extends Error {
  constructor(readonly retryAfter: number) {
    super(`로그인 시도가 너무 많습니다. ${Math.ceil(retryAfter / 60)}분 뒤에 다시 시도하세요.`);
  }
}

@Injectable()
export class AuthService {
  private fails = new Map<string, { n: number; first: number }>();

  /**
   * 계정 파일은 .bak 복구를 쓰지 않는다: 복구본은 계정 생성 전이나 이전 세션 번호일 수 있어
   * 계정을 가로채거나 폐기한 세션을 되살린다. 파일이 손상되면 예외로 로그인을 막는다(fail closed).
   */
  private load(): Account {
    if (!fs.existsSync(LOGIN)) return this.save({ username: null, password: null, secret_key: crypto.randomBytes(32).toString('hex'), epoch: 0 });
    const a = JSON.parse(fs.readFileSync(LOGIN, 'utf8')) as Partial<Account>;
    if (!a.secret_key) throw new Error('login.json 이 손상되었습니다.');
    return { username: a.username ?? null, password: a.password ?? null, secret_key: a.secret_key, epoch: a.epoch ?? 0 };
  }

  /** 서명 키가 들어 있으므로 소유자만 읽을 수 있게(0600) 임시 파일에 쓰고 바꿔 넣는다. */
  private save(a: Account): Account {
    const tmp = `${LOGIN}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(a, null, 2), { mode: 0o600 });
    fs.renameSync(tmp, LOGIN);
    try {
      fs.chmodSync(LOGIN, 0o600);
    } catch {
      /* shortcut: 권한 변경을 지원하지 않는 공유 폴더(SMB 등)에서는 건너뛴다 */
    }
    return a;
  }

  needsSetup(): boolean {
    const a = this.load();
    return !a.username || !a.password;
  }

  setup(username: string, password: string, ip: string): void {
    if (!this.needsSetup()) throw new Error('이미 계정이 있습니다.');
    this.assertValid(username, password);
    this.save({ ...this.load(), username, password: hashPassword(password), epoch: 0 });
    this.audit('setup', ip);
  }

  private assertValid(username: string, password: string) {
    if (!/^[A-Za-z0-9_.-]{3,32}$/.test(username)) throw new Error('아이디는 영문, 숫자, _ . - 로 3~32자 입력하세요.');
    if (password.length < 8 || password.length > 128) throw new Error('비밀번호는 8자 이상으로 입력하세요.');
  }

  /** 성공하면 세션 토큰, 아이디나 비밀번호가 틀리면 null. 같은 IP의 연속 실패는 15분에 5번까지만 받는다. */
  login(username: string, password: string, ip: string): string | null {
    for (const [k, v] of this.fails) if (Date.now() - v.first > WINDOW_MS) this.fails.delete(k); // 만료된 기록은 그때그때 버린다
    const cur = this.fails.get(ip);
    if (cur && cur.n >= MAX_FAILS) throw new TooMany(Math.ceil((WINDOW_MS - (Date.now() - cur.first)) / 1000));
    let a = this.load();
    // 아이디가 틀려도 같은 비용의 해시 계산을 해서 응답 시간으로 아이디를 알아내지 못하게 한다.
    const hit = !!a.username && username === a.username && !!a.password;
    const ok = verifyPassword(password, hit ? a.password! : DUMMY_HASH) && hit;
    if (!ok) {
      this.fails.set(ip, { n: (cur?.n ?? 0) + 1, first: cur?.first ?? Date.now() });
      this.audit('login-fail', ip, username.slice(0, 32));
      return null;
    }
    this.fails.delete(ip);
    this.audit('login', ip);
    if (isLegacy(a.password!)) a = this.save({ ...a, password: hashPassword(password) }); // 새 형식으로 바꿔 저장(세션 번호는 그대로)
    return this.token(a);
  }

  private token(a: Account): string {
    const body = Buffer.from(JSON.stringify({ u: a.username, e: a.epoch ?? 0, x: Math.floor(Date.now() / 1000) + SESSION_SEC })).toString('base64url');
    return `${body}.${sign(a.secret_key, body)}`;
  }

  /** 요청의 세션 쿠키를 검증해 사용자 이름을 돌려준다. */
  user(req: Pick<Request, 'headers'>): string | null {
    const raw = /(?:^|;\s*)rw_session=([^;]+)/.exec(req.headers.cookie ?? '')?.[1];
    if (!raw) return null;
    const [body, sig] = raw.split('.');
    const a = this.load();
    if (!body || !sig || !a.username) return null;
    const want = sign(a.secret_key, body);
    if (sig.length !== want.length || !crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(want))) return null;
    try {
      const p = JSON.parse(Buffer.from(body, 'base64url').toString());
      return p.u === a.username && p.e === (a.epoch ?? 0) && p.x > Date.now() / 1000 ? a.username : null;
    } catch {
      return null;
    }
  }

  setCookie(res: Response, token: string, req: Request) {
    const secure = req.secure || req.headers['x-forwarded-proto'] === 'https';
    res.append('Set-Cookie', `${COOKIE}=${token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${SESSION_SEC}${secure ? '; Secure' : ''}`);
  }

  clearCookie(res: Response) {
    res.append('Set-Cookie', `${COOKIE}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0`);
  }

  /** 비밀번호를 바꾸면 기존 세션은 모두 끊기고, 지금 세션만 새 토큰으로 이어진다. */
  changePassword(current: string, next: string, ip: string): string {
    const a = this.load();
    if (!a.password || !verifyPassword(current, a.password)) throw new Error('현재 비밀번호가 맞지 않습니다.');
    this.assertValid(a.username!, next);
    const upd = this.save({ ...a, password: hashPassword(next), epoch: (a.epoch ?? 0) + 1 });
    this.audit('password', ip);
    return this.token(upd);
  }

  logoutAll(ip: string): void {
    const a = this.load();
    this.save({ ...a, epoch: (a.epoch ?? 0) + 1 });
    this.audit('logout-all', ip);
  }

  audit(type: AuditEntry['type'], ip: string, detail?: string) {
    const list = readJson<AuditEntry[]>(AUDIT, []);
    list.unshift({ at: new Date().toISOString(), type, ip, detail });
    writeJson(AUDIT, list.slice(0, 100));
  }

  activity(): AuditEntry[] {
    return readJson<AuditEntry[]>(AUDIT, []).slice(0, 30);
  }
}
