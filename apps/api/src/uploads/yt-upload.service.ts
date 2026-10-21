import { Injectable, OnApplicationBootstrap, OnApplicationShutdown } from '@nestjs/common';
import { execFile } from 'node:child_process';
import fs from 'node:fs';
import https from 'node:https';
import path from 'node:path';
import { Readable, Transform } from 'node:stream';
import { promisify } from 'node:util';
import { Channel } from '../config/config.js';
import { StoreService } from '../config/store.service.js';
import { bin } from '../lib/bin.js';
import { jsonPath, normPath } from '../lib/paths.js';
import { readJson, writeJson } from '../lib/json-store.js';
import { sleep } from '../lib/text.js';
import { NotifierService } from '../recorder/notifier.service.js';
import { RecorderService } from '../recorder/recorder.service.js';
import { DEFAULT_UPLOAD_SETTINGS, EXTS, UploadSettings, UploadState, isDone, playlistOf, selectCandidates, splitName, titleOf } from './yt-upload.js';

const execFileP = promisify(execFile);
const TOKEN = jsonPath('yt_token.json');
const STATE = jsonPath('yt_upload_state.json');
const SETTINGS = jsonPath('yt_upload.json');
const SETTING_KEYS = new Set([...Object.keys(DEFAULT_UPLOAD_SETTINGS), 'auto_since']);

class Fatal extends Error {}
class LimitHit extends Error {}

interface HttpRes {
  status: number;
  headers: Record<string, string | string[] | undefined>;
  text: string;
}

/** fetch는 Content-Length를 직접 지정한 스트림 PUT에 불안정해서 https로 직접 보낸다. */
function request(url: string, method: string, headers: Record<string, string>, body?: Readable | string): Promise<HttpRes> {
  return new Promise((resolve, reject) => {
    const req = https.request(url, { method, headers, timeout: 300_000 }, (res) => {
      let text = '';
      res.setEncoding('utf8');
      res.on('data', (d) => (text += d));
      res.on('end', () => resolve({ status: res.statusCode ?? 0, headers: res.headers, text }));
    });
    req.on('timeout', () => req.destroy(new Error('요청 시간 초과')));
    req.on('error', reject);
    if (body instanceof Readable) body.on('error', (e) => req.destroy(e)).pipe(req);
    else req.end(body);
  });
}

const parse = (t: string) => {
  try {
    return JSON.parse(t);
  } catch {
    return { raw: t };
  }
};
const isQuota = (j: unknown) => /quotaExceeded|uploadLimitExceeded|rateLimitExceeded/.test(JSON.stringify(j));

export interface QueueRow {
  name: string;
  state: 'uploading' | 'waiting' | 'error' | 'queued' | 'done';
  msg: string;
  video_id: string | null;
  privacy: string | null;
}

@Injectable()
export class YtUploadService implements OnApplicationBootstrap, OnApplicationShutdown {
  private state: Record<string, UploadState> = readJson(STATE, {});
  private info = new Map<string, { state: QueueRow['state']; msg: string }>();
  private active = new Map<string, string>(); // 파일명 -> 전체 경로 (업로드 중)
  private retryAt = new Map<string, number>();
  private fails = new Map<string, number>();
  private authError = '';
  private gate = 0; // 이 시각 전에는 새 업로드 세션을 만들지 않는다
  private createChain: Promise<unknown> = Promise.resolve();
  private tok = { at: '', exp: 0 };
  private nextT = 0;
  private stop = new AbortController();

  constructor(
    private readonly store: StoreService,
    private readonly notifier: NotifierService,
    private readonly recorder: RecorderService,
  ) {}

  onApplicationBootstrap() {
    void this.scanLoop();
  }

  onApplicationShutdown() {
    this.stop.abort();
  }

  // ---- 설정/토큰/큐 ----

  settings(): UploadSettings {
    const file = readJson<Partial<UploadSettings>>(SETTINGS, {});
    if (!file.auto_since) {
      // 기능을 처음 켠 날부터 자동 대상 — 밀린 파일은 수동으로 고른다
      file.auto_since = new Date().toLocaleDateString('sv-SE');
      writeJson(SETTINGS, file);
    }
    return { ...DEFAULT_UPLOAD_SETTINGS, ...file } as UploadSettings;
  }

  saveSettings(patch: Record<string, unknown>) {
    const cur = readJson<Record<string, unknown>>(SETTINGS, {});
    for (const [k, v] of Object.entries(patch)) if (SETTING_KEYS.has(k) && v !== undefined) cur[k] = v;
    writeJson(SETTINGS, cur);
  }

  saveToken(text: string) {
    const t = JSON.parse(text);
    const missing = ['refresh_token', 'client_id', 'client_secret', 'token_uri'].filter((k) => !t[k]);
    if (missing.length) throw new Error(`토큰 JSON에 키가 없습니다: ${missing.join(', ')}`);
    writeJson(TOKEN, t);
    try {
      fs.chmodSync(TOKEN, 0o600);
    } catch {
      /* Windows 등 */
    }
    this.tok = { at: '', exp: 0 };
    this.authError = '';
  }

  /** Verify with Google before replacing the stored refresh token. Never return tokens to the browser. */
  async reauthenticate(value: unknown) {
    if (typeof value !== 'string' || !value.trim() || value.length > 16_384 || /\s/.test(value.trim())) {
      throw new Error('새 refresh token을 입력하세요.');
    }
    const refreshToken = value.trim();
    const current = readJson<Record<string, unknown> | null>(TOKEN, null);
    if (!current || typeof current.client_id !== 'string' || !current.client_id || typeof current.client_secret !== 'string' || !current.client_secret) {
      throw new Error('기존 OAuth 클라이언트 정보가 없습니다. 인증 토큰 전체 JSON을 먼저 등록하세요.');
    }
    let response: Response;
    try {
      response = await fetch('https://oauth2.googleapis.com/token', {
        method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ client_id: current.client_id, client_secret: current.client_secret,
          refresh_token: refreshToken, grant_type: 'refresh_token' }),
        signal: AbortSignal.timeout(30_000),
      });
    } catch {
      throw new Error('Google에 연결하지 못했습니다. 잠시 후 재인증을 다시 시도하세요.');
    }
    if (!response.ok) {
      throw new Error(response.status < 500
        ? '재인증에 실패했습니다. 기존과 같은 OAuth 클라이언트에서 발급한 refresh token인지 확인하세요.'
        : 'Google 인증 서버 오류입니다. 잠시 후 다시 시도하세요.');
    }
    let result: { access_token?: unknown; expires_in?: unknown; scope?: unknown } | null;
    try { result = await response.json(); } catch { throw new Error('Google 인증 응답을 읽지 못했습니다.'); }
    if (!result || typeof result.access_token !== 'string' || !result.access_token ||
        typeof result.expires_in !== 'number' || !Number.isFinite(result.expires_in) || result.expires_in <= 0) {
      throw new Error('Google 인증 응답이 올바르지 않습니다. 다시 시도하세요.');
    }
    if (typeof result.scope === 'string' && !result.scope.split(' ').some((s) =>
      ['https://www.googleapis.com/auth/youtube', 'https://www.googleapis.com/auth/youtube.force-ssl'].includes(s))) {
      throw new Error('YouTube 업로드와 재생목록 관리 권한이 필요합니다. 해당 권한으로 발급한 refresh token을 입력하세요.');
    }
    if (JSON.stringify(readJson(TOKEN, null)) !== JSON.stringify(current)) {
      throw new Error('확인 중 인증 정보가 변경되었습니다. 재인증을 다시 시도하세요.');
    }
    this.saveToken(JSON.stringify({ ...current, refresh_token: refreshToken, token_uri: 'https://oauth2.googleapis.com/token' }));
    this.tok = { at: result.access_token, exp: Date.now() + (result.expires_in - 300) * 1000 };
    return { ok: true };
  }

  enqueue(fullPath: string) {
    const p = path.resolve(fullPath);
    const fn = path.basename(p);
    if (!fs.existsSync(p) || !fs.statSync(p).isFile() || !(path.extname(fn).toLowerCase() in EXTS)) throw new Error('.ts / .mp4 파일만 업로드할 수 있습니다');
    const st = (this.state[fn] ??= {});
    if (st.video_id) throw new Error('이미 업로드된 파일입니다');
    st.path = p;
    this.retryAt.delete(fn);
    this.save();
  }

  activePaths(): string[] {
    return [...this.active.values()];
  }

  snapshot() {
    const order = { uploading: 0, waiting: 1, error: 2, queued: 3, done: 4 };
    const items: QueueRow[] = Object.entries(this.state)
      .map(([name, st]) => {
        const i = this.info.get(name);
        return { name, state: st.video_id ? ('done' as const) : (i?.state ?? 'queued'), msg: i?.msg ?? '', video_id: st.video_id ?? null, privacy: st.privacy ?? null };
      })
      .sort((a, b) => order[a.state] - order[b.state] || a.name.localeCompare(b.name));
    return { auth_error: this.authError, has_token: fs.existsSync(TOKEN), settings: this.settings(), items };
  }

  private save() {
    writeJson(STATE, this.state);
  }

  // ---- 스캔 루프 ----

  private async scanLoop() {
    const sig = this.stop.signal;
    let running = 0;
    while (!sig.aborted) {
      const s = this.settings();
      try {
        if (!this.authError) {
          const channels = this.store.getChannels();
          const recBusy = new Set(this.recorder.busyPaths().map(normPath)); // 녹화/후처리 중인 파일은 건드리지 않는다
          const busyOf = (p: string) => this.active.has(path.basename(p)) || recBusy.has(normPath(p));
          for (const p of selectCandidates(channels, this.state, busyOf, s)) {
            const fn = path.basename(p);
            if (this.active.has(fn) || isDone(fn, this.state[fn], channels) || (this.retryAt.get(fn) ?? 0) > Date.now()) continue;
            if (running >= s.pool) break;
            this.active.set(fn, p);
            this.info.set(fn, this.info.get(fn) ?? { state: 'queued', msg: '' });
            running++;
            void this.work(p, channels, s).finally(() => running--);
          }
        }
      } catch (e) {
        console.error('[YT] 스캔 오류:', e);
      }
      await sleep(s.scan_interval_sec * 1000, sig);
    }
  }

  private async work(p: string, channels: Channel[], s: UploadSettings) {
    const fn = path.basename(p);
    try {
      const st = this.state[fn] ?? {};
      if (!st.video_id && !st.session) {
        // 세션이 열린 파일은 자르지 않는다
        const parts = await this.splitLong(p, s);
        if (parts) {
          delete this.state[fn];
          for (const part of parts) this.state[path.basename(part)] = { path: part }; // 조각은 다음 스캔에서 개별 파일로 올라간다
          this.save();
          return;
        }
      }
      this.info.set(fn, { state: 'uploading', msg: '' });
      await this.upload(p, channels, s);
      this.info.set(fn, { state: 'done', msg: '' });
      this.fails.delete(fn);
    } catch (e) {
      if (e instanceof Fatal) {
        if (!this.authError) void this.notifier.notify(`[YouTube 업로드] 중단: ${e.message}`);
        this.authError = e.message;
        this.info.set(fn, { state: 'error', msg: e.message });
      } else if (e instanceof LimitHit) {
        this.info.set(fn, { state: 'waiting', msg: e.message });
        this.retryAt.set(fn, this.gate);
      } else {
        const n = (this.fails.get(fn) ?? 0) + 1;
        this.fails.set(fn, n);
        const msg = (e as Error).message;
        const wait = /quota/.test(msg) ? 3600_000 : Math.min(30_000 * 2 ** (n - 1), 1800_000);
        console.error(`[YT] 오류 → ${wait / 1000}s 후 재시도: ${fn}: ${msg.slice(0, 300)}`);
        this.info.set(fn, { state: 'error', msg: msg.slice(0, 300) });
        this.retryAt.set(fn, Date.now() + wait);
      }
    } finally {
      this.active.delete(fn);
    }
  }

  // ---- YouTube API ----

  private async token(force = false): Promise<string> {
    if (!force && this.tok.at && Date.now() < this.tok.exp) return this.tok.at;
    if (!fs.existsSync(TOKEN)) throw new Fatal('yt_token.json 이 없습니다 — 업로드 화면에서 토큰을 등록하세요');
    const t = readJson<Record<string, string>>(TOKEN, {});
    const res = await fetch(t.token_uri, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ refresh_token: t.refresh_token, client_id: t.client_id, client_secret: t.client_secret, grant_type: 'refresh_token' }),
      signal: AbortSignal.timeout(60_000),
    });
    const j: any = await res.json().catch(() => ({}));
    if (!res.ok) {
      if (JSON.stringify(j).includes('invalid_grant')) throw new Fatal('refresh token 만료 — 재인증 필요 (토큰을 다시 등록하세요)');
      throw new Error(`토큰 갱신 실패 ${res.status}`);
    }
    this.tok = { at: j.access_token, exp: Date.now() + (j.expires_in - 300) * 1000 };
    return this.tok.at;
  }

  /** JSON API 호출. 401이면 토큰을 갱신해 한 번 더 시도한다. */
  private async api(method: string, url: string, body?: unknown, headers: Record<string, string> = {}) {
    for (let attempt = 0; ; attempt++) {
      const res = await request(url, method, { Authorization: `Bearer ${await this.token(attempt === 1)}`, 'Content-Type': 'application/json; charset=UTF-8', ...headers }, body ? JSON.stringify(body) : undefined);
      if (res.status === 401 && attempt === 0) continue;
      return { ...res, json: parse(res.text) };
    }
  }

  /** 전체 스트림 합산 속도를 rate_mbps로 제한하는 변환 스트림. */
  private throttle(rate: number, onBytes: (n: number) => void) {
    return new Transform({
      transform: (chunk: Buffer, _enc, cb) => {
        onBytes(chunk.length);
        const now = Date.now();
        const start = Math.max(this.nextT, now);
        this.nextT = start + (chunk.length * 8) / (rate * 1e3); // ms
        setTimeout(() => cb(null, chunk), start - now);
      },
    });
  }

  private async upload(p: string, channels: Channel[], s: UploadSettings) {
    const fn = path.basename(p);
    const size = fs.statSync(p).size;
    const names = new Set(fs.readdirSync(path.dirname(p)));
    const st = (this.state[fn] ??= {});
    const pl = playlistOf(fn, channels);

    while (!st.video_id) {
      if (!st.session) {
        const meta = {
          snippet: { title: titleOf(fn, names), description: s.description, tags: s.tags, categoryId: '22' },
          status: { privacyStatus: s.privacy, selfDeclaredMadeForKids: false },
        };
        // 실패한 insert도 일일 할당량을 쓴다 → 세션 생성은 한 번에 하나, 한도에 걸리면 전체가 1시간 대기
        const created = this.createChain.then(async () => {
          await sleep(Math.max(0, this.gate - Date.now()));
          const r = await this.api('POST', 'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status', meta, {
            'X-Upload-Content-Length': String(size),
            'X-Upload-Content-Type': EXTS[path.extname(fn).toLowerCase()],
          });
          if (r.status === 429 || (r.status !== 200 && isQuota(r.json))) {
            this.gate = Date.now() + 3600_000;
            throw new LimitHit(`한도 ${r.status} → ${new Date(this.gate).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit' })} 까지 전체 대기`);
          }
          return r;
        });
        this.createChain = created.catch(() => undefined);
        const r = await created;
        if (r.status !== 200) throw new Error(`세션 생성 실패 ${r.status} ${r.text.slice(0, 200)}`);
        st.session = String(r.headers.location);
        this.save();
      }

      // 서버가 받은 위치를 확인한 뒤 이어서 PUT
      const q = await request(st.session, 'PUT', { Authorization: `Bearer ${await this.token()}`, 'Content-Length': '0', 'Content-Range': `bytes */${size}` });
      if (q.status === 200 || q.status === 201) {
        this.finish(st, parse(q.text));
        break;
      }
      if (q.status === 404 || q.status === 410) {
        delete st.session; // 세션 만료 → 처음부터
        this.save();
        continue;
      }
      if (q.status !== 308) throw new Error(`오프셋 조회 실패 ${q.status} ${q.text.slice(0, 300)}`);
      const range = q.headers.range as string | undefined;
      const off = range ? Number(range.split('-')[1]) + 1 : 0;

      const body = fs.createReadStream(p, { start: off }).pipe(this.throttle(s.rate_mbps, () => undefined));
      const r = await request(st.session, 'PUT', { Authorization: `Bearer ${await this.token()}`, 'Content-Length': String(size - off), 'Content-Range': `bytes ${off}-${size - 1}/${size}` }, body);
      if (r.status === 200 || r.status === 201) this.finish(st, parse(r.text));
      else if (isQuota(r.text)) throw new Error('quota ' + r.text.slice(0, 200));
      else if (r.status < 500 && r.status !== 308) throw new Error(`업로드 실패 ${r.status} ${r.text.slice(0, 300)}`);
    }
    this.save();

    if (pl && !st.playlisted) {
      const r = await this.api('POST', 'https://www.googleapis.com/youtube/v3/playlistItems?part=snippet', { snippet: { playlistId: pl, resourceId: { kind: 'youtube#video', videoId: st.video_id } } });
      if (r.status !== 200) throw new Error(`재생목록 추가 실패 ${r.status} ${r.text.slice(0, 200)}`);
      st.playlisted = true;
      this.save();
    }
    console.log(`[YT] 완료 [${st.privacy}] https://youtu.be/${st.video_id}  ${fn}`);
  }

  private finish(st: UploadState, j: any) {
    st.video_id = j.id;
    st.privacy = j.status?.privacyStatus;
    delete st.session;
  }

  // ---- 12시간 초과 분할 ----

  private async duration(p: string): Promise<number> {
    const { stderr } = await execFileP(bin('ffmpeg'), ['-hide_banner', '-i', p]).catch((e) => ({ stderr: String(e.stderr ?? '') }));
    const m = /Duration: (\d+):(\d+):([\d.]+)/.exec(stderr);
    if (!m) throw new Error('길이를 읽을 수 없습니다');
    return Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]);
  }

  /** 12시간을 넘으면 N등분해 'X.ts', 'X (1).ts' … 로 바꾸고 원본은 _over12h/ 로 옮긴다 (재인코딩 없음). 분할했으면 새 경로 목록, 아니면 null. */
  private async splitLong(p: string, s: UploadSettings): Promise<string[] | null> {
    const d = await this.duration(p);
    if (d <= s.max_sec) return null;
    const dir = path.dirname(p);
    const fn = path.basename(p);
    const { pre, name, ext } = splitName(fn);
    const n = Math.ceil(d / s.max_sec);
    const base = fn.slice(0, fn.length - ext.length);
    const outs = [fn, ...Array.from({ length: n - 1 }, (_, i) => `${pre}${name} (${i + 1})${ext}`)];
    if (outs.slice(1).some((o) => fs.existsSync(path.join(dir, o)))) throw new Error(`분할 이름 충돌 — 직접 처리 필요: ${fn}`);
    const hold = path.join(dir, '_over12h');
    fs.mkdirSync(hold, { recursive: true });
    const cuts = Array.from({ length: n - 1 }, (_, i) => Math.trunc((d * (i + 1)) / n)).join(',');
    await execFileP(bin('ffmpeg'), ['-hide_banner', '-loglevel', 'error', '-y', '-i', p, '-map', '0', '-c', 'copy', '-f', 'segment', '-reset_timestamps', '1', '-segment_times', cuts, path.join(hold, `${base}.part%d${ext}`)], { maxBuffer: 1 << 24 });
    fs.renameSync(p, path.join(hold, fn));
    outs.forEach((o, i) => fs.renameSync(path.join(hold, `${base}.part${i}${ext}`), path.join(dir, o)));
    return outs.map((o) => path.join(dir, o));
  }
}
