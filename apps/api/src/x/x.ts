// X(트위터) 스페이스 감시용 헬퍼.
// 스페이스 감지는 로그인 쿠키(auth_token, ct0)가 있어야 한다 (쿠키 없이 avatar_content는 401).
// 스페이스 메타데이터/재생 주소(master URL)는 X 내부 GraphQL 대신 yt-dlp가 해석한다 — X 쪽 변경을 yt-dlp가 따라가 준다.

/** X 웹 클라이언트가 공개적으로 쓰는 bearer 토큰 (게스트 토큰 발급으로 유효성 확인됨). */
export const WEB_BEARER = 'AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36';

export interface XCookies {
  authToken: string;
  ct0: string;
}

export type XErrorKind = 'no-cookie' | 'auth' | 'rate' | 'network' | 'api' | 'lookup';

export class XError extends Error {
  constructor(
    readonly kind: XErrorKind,
    message: string,
    readonly status?: number,
  ) {
    super(message);
  }
}

/** 사용자에게 보여 줄 조치 문구. 기술 상세는 뒤에 붙인다. */
export function xErrorMessage(e: unknown): string {
  if (!(e instanceof XError)) return `알 수 없는 오류: ${(e as Error).message}`;
  switch (e.kind) {
    case 'no-cookie':
      return 'X 쿠키가 없습니다. 설정 → 계정·알림에서 auth_token과 ct0를 등록하세요.';
    case 'auth':
      return `X 로그인 쿠키가 만료되었거나 올바르지 않습니다(HTTP ${e.status}). 브라우저에서 다시 로그인한 뒤 쿠키를 새로 등록하세요.`;
    case 'rate':
      return 'X가 요청을 제한했습니다(HTTP 429). 잠시 뒤 자동으로 다시 시도합니다.';
    case 'network':
      return `X에 연결하지 못했습니다. 네트워크를 확인하세요. (${e.message})`;
    case 'lookup':
      return e.message; // 이미 조치 안내까지 담은 문구
    default:
      return `X 응답을 해석하지 못했습니다: ${e.message}`;
  }
}

/** Netscape 쿠키 파일 또는 "auth_token=...; ct0=..." 한 줄 형식을 모두 받는다. */
export function parseXCookies(text: string): XCookies | null {
  const pairs = new Map<string, string>();
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.replace(/^#HttpOnly_/, '');
    if (!line.trim() || line.startsWith('#')) continue;
    const f = line.split('\t');
    if (f.length >= 7) {
      if (/(^|\.)(x|twitter)\.com$/.test(f[0].replace(/^\./, ''))) pairs.set(f[5], f[6].trim());
      continue;
    }
    for (const part of line.split(';')) {
      const i = part.indexOf('=');
      if (i > 0) pairs.set(part.slice(0, i).trim(), part.slice(i + 1).trim());
    }
  }
  const authToken = pairs.get('auth_token');
  const ct0 = pairs.get('ct0');
  return authToken && ct0 ? { authToken, ct0 } : null;
}

/** yt-dlp --cookies 로 넘길 Netscape 형식. */
export function toNetscape(c: XCookies): string {
  const far = Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 365;
  const row = (name: string, value: string) => `.x.com\tTRUE\t/\tTRUE\t${far}\t${name}\t${value}`;
  return ['# Netscape HTTP Cookie File', row('auth_token', c.authToken), row('ct0', c.ct0), ''].join('\n');
}

/** 저장할 쿠키 텍스트: Netscape면 그대로(다른 쿠키도 yt-dlp에 유용), 한 줄 형식이면 Netscape로 변환. 검증 실패 시 예외. */
export function normalizeXCookieInput(text: string): string {
  const c = parseXCookies(text);
  if (!c) throw new Error('auth_token과 ct0가 모두 있어야 합니다. 브라우저 개발자도구 → Application → Cookies → x.com에서 복사하세요.');
  return text.includes('\t') ? text : toNetscape(c);
}

/** '@Name', 'name', 'https://x.com/Name?s=20' → '@Name' */
export function normalizeHandle(raw: string): string {
  let s = raw.trim();
  const m = /(?:x|twitter)\.com\/(@?[A-Za-z0-9_]{1,15})/i.exec(s);
  if (m) s = m[1];
  return '@' + s.replace(/^@/, '').replace(/[^A-Za-z0-9_].*$/, '');
}

export const spaceUrl = (id: string) => `https://x.com/i/spaces/${id}`;

export function xHeaders(c: XCookies): Record<string, string> {
  return {
    authorization: `Bearer ${WEB_BEARER}`,
    'x-csrf-token': c.ct0,
    cookie: `auth_token=${c.authToken}; ct0=${c.ct0}`,
    'x-twitter-auth-type': 'OAuth2Session',
    'x-twitter-active-user': 'yes',
    'x-twitter-client-language': 'en',
    'user-agent': UA,
  };
}

async function xGet(url: string, c: XCookies): Promise<any> {
  let res: Response;
  try {
    res = await fetch(url, { headers: xHeaders(c), signal: AbortSignal.timeout(15_000) });
  } catch (e) {
    throw new XError('network', (e as Error).message);
  }
  if (res.status === 401 || res.status === 403) throw new XError('auth', `HTTP ${res.status}`, res.status);
  if (res.status === 429) throw new XError('rate', 'rate limited', 429);
  if (!res.ok) throw new XError('api', `HTTP ${res.status}`, res.status);
  try {
    return await res.json();
  } catch {
    throw new XError('api', 'JSON이 아닌 응답 (X가 요청을 막았을 수 있습니다)', res.status);
  }
}

/**
 * 핸들 → 숫자 사용자 ID. 공식 REST 엔드포인트를 차례로 시도한다.
 * X 쪽 변경으로 모두 실패하면 호출하는 쪽이 사용자 ID를 직접 입력받는다.
 */
export async function resolveUserId(handle: string, c: XCookies): Promise<{ id: string; via: string }> {
  const name = encodeURIComponent(handle.replace(/^@/, ''));
  const tries: [string, (j: any) => string | undefined][] = [
    [`https://x.com/i/api/1.1/users/show.json?screen_name=${name}`, (j) => j?.id_str],
    [`https://x.com/i/api/1.1/users/lookup.json?screen_name=${name}`, (j) => j?.[0]?.id_str],
  ];
  let denied: number | undefined;
  let last: unknown;
  for (const [url, pick] of tries) {
    try {
      const id = pick(await xGet(url, c));
      if (id) return { id, via: new URL(url).pathname.split('/').pop()! };
    } catch (e) {
      if (e instanceof XError && (e.kind === 'rate' || e.kind === 'network')) throw e; // 다른 엔드포인트로 바꿔도 소용없는 오류
      if (e instanceof XError && e.kind === 'auth') denied = e.status; // 쿠키 문제인지 X가 이 API를 막은 건지 여기서는 구분할 수 없다
      else last = e;
    }
  }
  // 이 단계의 401/403은 쿠키 만료일 수도, X가 구형 조회 API를 막은 것일 수도 있다. 원인을 단정하지 않고 우회 방법을 알려 준다.
  const why = denied ? `X가 조회를 거부했습니다(HTTP ${denied}). 쿠키가 만료됐거나 X가 이 조회 방식을 막았을 수 있습니다.` : `조회에 실패했습니다${last ? ` (${(last as Error).message})` : ''}.`;
  throw new XError('lookup', `${handle} 의 사용자 ID를 알아내지 못했습니다. ${why} 숫자 사용자 ID를 직접 입력하면 이 단계를 건너뜁니다.`);
}

/** avatar_content 응답에서 라이브 스페이스 ID(broadcast_id)를 찾는다. 응답 구조가 조금 바뀌어도 찾도록 재귀로 훑는다. */
export function parseLiveSpaceId(json: any, userId?: string): string | null {
  const root = userId && json?.users?.[userId] ? json.users[userId] : json?.users ? Object.values(json.users)[0] : json;
  const found: string[] = [];
  const walk = (v: any, inSpaces: boolean) => {
    if (!v || typeof v !== 'object') return;
    for (const [k, x] of Object.entries(v)) {
      if (k === 'broadcast_id' && typeof x === 'string' && inSpaces) found.push(x);
      else walk(x, inSpaces || k === 'spaces' || k === 'audiospace');
    }
  };
  walk(root, false);
  return found[0] ?? null;
}

export async function fetchLiveSpaceId(userId: string, c: XCookies): Promise<string | null> {
  const json = await xGet(`https://x.com/i/api/fleets/v1/avatar_content?user_ids=${encodeURIComponent(userId)}&only_spaces=true`, c);
  return parseLiveSpaceId(json, userId);
}

export interface XCheckStep {
  name: string;
  ok: boolean;
  detail: string;
}

/** 연결 확인: 단계별 결과를 돌려줘서 어디에서 막혔는지 바로 알 수 있게 한다. */
export async function checkX(handle: string, c: XCookies | null, knownUserId?: string): Promise<{ steps: XCheckStep[]; userId?: string; spaceId?: string | null }> {
  const steps: XCheckStep[] = [];
  if (!c) {
    steps.push({ name: '쿠키', ok: false, detail: xErrorMessage(new XError('no-cookie', '')) });
    return { steps };
  }
  steps.push({ name: '쿠키', ok: true, detail: 'auth_token, ct0 확인됨' });

  let userId = knownUserId?.trim();
  try {
    if (userId) steps.push({ name: '사용자 ID', ok: true, detail: `${userId} (직접 입력)` });
    else {
      const r = await resolveUserId(handle, c);
      userId = r.id;
      steps.push({ name: '사용자 ID', ok: true, detail: `${r.id} (${r.via})` });
    }
  } catch (e) {
    steps.push({ name: '사용자 ID', ok: false, detail: xErrorMessage(e) });
    return { steps };
  }

  try {
    const spaceId = await fetchLiveSpaceId(userId, c);
    steps.push({ name: '스페이스 조회', ok: true, detail: spaceId ? `진행 중인 스페이스가 있습니다 (${spaceId})` : '지금 진행 중인 스페이스는 없습니다 (조회 성공)' });
    return { steps, userId, spaceId };
  } catch (e) {
    steps.push({ name: '스페이스 조회', ok: false, detail: xErrorMessage(e) });
    return { steps, userId };
  }
}
