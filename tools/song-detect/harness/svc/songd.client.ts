// NestJS(apps/api)에서 쓸 songd 클라이언트 시제품. 의존성 없음(Node 18+ 내장 fetch). 사용: new SongdClient().run('replay', { registry: false })
export type SongdMode = 'cap80' | 'unlimited';
export interface SongdJob<T = unknown> {
  id: string;
  op: string;
  status: 'queued' | 'running' | 'done' | 'error';
  result?: T;
  error?: string;
  queue_ms: number;
  run_ms: number;
}

export class SongdClient {
  private readonly base: string;

  constructor(base = process.env.SONGD_URL ?? 'http://127.0.0.1:8790') {
    this.base = base; // 매개변수 프로퍼티는 Node 타입 제거 실행이 못 읽어서 필드로 둠
  }

  private async req<R>(method: string, path: string, body?: unknown): Promise<R> {
    const res = await fetch(this.base + path, { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
    if (!res.ok) throw new Error(`songd ${method} ${path} -> ${res.status} ${await res.text()}`);
    return (await res.json()) as R;
  }

  /** 끝날 때까지 기다려 결과를 돌려준다(짧은 작업용). 실패하면 예외. */
  async run<T = unknown>(op: string, args: unknown = {}): Promise<T> {
    const job = await this.req<SongdJob<T>>('POST', '/jobs?wait=1', { op, args });
    if (job.status !== 'done') throw new Error(`songd ${op}: ${job.error ?? job.status}`);
    return job.result as T;
  }

  /** 긴 작업: id 만 받고 get 으로 확인한다. */
  submit(op: string, args: unknown = {}): Promise<{ id: string }> {
    return this.req('POST', '/jobs', { op, args });
  }

  get<T = unknown>(id: string): Promise<SongdJob<T>> {
    return this.req('GET', `/jobs/${id}`);
  }

  setMode(mode: SongdMode): Promise<{ mode: SongdMode; workers: number }> {
    return this.req('POST', '/mode', { mode });
  }

  health(): Promise<{ mode: SongdMode; workers: number; queued: number; done: number; cpus: number }> {
    return this.req('GET', '/healthz');
  }
}
