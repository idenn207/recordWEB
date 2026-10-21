export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

/** JSON API 호출. 서버(Nest)의 에러 본문 message를 그대로 사용자 문구로 올린다. */
export async function api<T>(path: string, init: { method?: string; body?: unknown } = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: init.method ?? (init.body === undefined ? 'GET' : 'POST'),
    headers: init.body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
  if (!res.ok) {
    const j = (await res.json().catch(() => null)) as { message?: string | string[] } | null;
    const msg = Array.isArray(j?.message) ? j.message.join(', ') : (j?.message ?? `요청 실패 (${res.status})`);
    throw new ApiError(msg, res.status);
  }
  return (await res.json().catch(() => ({}))) as T;
}
