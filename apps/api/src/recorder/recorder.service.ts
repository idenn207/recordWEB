import { Injectable, OnApplicationBootstrap, OnApplicationShutdown } from '@nestjs/common';
import { ChildProcess } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { getLiveMeta, LiveMeta } from '../chzzk/chzzk.js';
import { Channel } from '../config/config.js';
import { StoreService } from '../config/store.service.js';
import { bin } from '../lib/bin.js';
import { absFromRoot } from '../lib/paths.js';
import { exited, onLines, signalGroup, spawnGroup, terminate } from '../lib/proc.js';
import { fmtDuration, jitteredWaitMs, sleep, uniqueFilename } from '../lib/text.js';
import { getYoutubeMeta, YtMeta } from '../youtube/youtube.js';
import { chzzkProbeArgs, chzzkRecordArgs, recordFilename, ytDlpArgs, ytNameQuality } from './commands.js';
import { esc, NotifierService } from './notifier.service.js';
import { moveInto, postProcess } from './postprocess.js';

export type RunState = 'idle' | 'watching' | 'recording';

/** UI에 보여 주는 방송 정보 (플랫폼 무관). */
export interface UiMeta {
  isLive: boolean;
  liveTitle: string;
  category: string;
  thumbnailUrl: string | null;
}

interface Runtime {
  state: RunState;
  abort: AbortController | null;
  proc: ChildProcess | null;
  file: string | null;
  startedAt: number | null;
  stopping: boolean;
  done: Promise<void>;
}

export interface ChannelStatus {
  state: RunState;
  filename: string;
  duration: string;
  startedAt: number | null;
  meta: UiMeta | null;
}

const TAIL_COOLDOWN_MS = 60_000; // 방종 직후 같은 라이브로 되감기 재접속 방지
const META_TTL_MS = 30_000;
const MAX_PROBES = 4;
const MIN_OK_SIZE = 1024 * 1024; // yt-dlp 결과가 이보다 작으면 깨진 파일로 본다

const TRANSIENT = [/Failed to fetch segment.*(404|403|416)/s, /No new segments in playlist/, /Read timeout/];

@Injectable()
export class RecorderService implements OnApplicationBootstrap, OnApplicationShutdown {
  private rt = new Map<string, Runtime>();
  private metaCache = new Map<string, { meta: UiMeta; at: number }>();
  private metaInflight = new Map<string, Promise<void>>();
  private postInflight = new Set<string>();
  private postTasks = new Set<Promise<unknown>>();
  private probes = 0;

  constructor(
    private readonly store: StoreService,
    private readonly notifier: NotifierService,
  ) {}

  onApplicationBootstrap() {
    // 부팅 시 자동 시작 (autoRecordingMode ON이면 record_enabled 채널 전부 감시 시작)
    if (this.store.getConfig().autoRecordingMode) this.startAll();
  }

  async onApplicationShutdown() {
    await this.stopAll();
    // 방금 중지된 녹화의 후처리가 끝날 때까지 기다린다 (컨테이너 stop_grace_period 안에서). 못 끝나면 원본이 남는다.
    await Promise.race([Promise.allSettled([...this.postTasks]), new Promise((r) => setTimeout(r, 25_000))]);
  }

  private runtime(id: string): Runtime {
    let r = this.rt.get(id);
    if (!r) this.rt.set(id, (r = { state: 'idle', abort: null, proc: null, file: null, startedAt: null, stopping: false, done: Promise.resolve() }));
    return r;
  }

  // ---- 외부 API ----

  status(ch: Channel): ChannelStatus {
    const r = this.runtime(ch.id);
    return {
      state: r.state,
      filename: r.file ? path.basename(r.file) : '',
      duration: r.state === 'recording' && r.startedAt ? fmtDuration((Date.now() - r.startedAt) / 1000) : '',
      startedAt: r.startedAt,
      meta: this.cachedMeta(ch),
    };
  }

  /** 사용자 시작: 토글이 꺼져 있어도 이번 방송 1회는 녹화한다. */
  start(id: string, user = true): boolean {
    const ch = this.store.getChannel(id);
    if (!ch) return false;
    const r = this.runtime(id);
    if (r.abort) {
      if (!r.abort.signal.aborted) return true; // 이미 감시/녹화 중
      void r.done.then(() => this.start(id, user)); // 중지 중이면 끝난 뒤에 다시 시작
      return true;
    }
    const abort = (r.abort = new AbortController());
    r.stopping = false;
    r.done = this.loop(ch, r, user).finally(() => {
      if (r.abort === abort) r.abort = null;
      r.state = 'idle';
    });
    return true;
  }

  async stop(id: string) {
    const r = this.rt.get(id);
    if (!r?.abort) return;
    r.stopping = true;
    r.abort.abort();
    if (r.proc) await this.stopProc(r.proc, this.store.getChannel(id)?.platform);
  }

  startAll() {
    for (const ch of this.store.getChannels()) if (ch.record_enabled) this.start(ch.id, false);
  }

  async stopAll() {
    await Promise.all(this.store.getChannels().map((c) => this.stop(c.id)));
  }

  /** 토글이 꺼지면 감시만 멈춘다. 녹화 중이면 이번 회차는 끝까지 간다. */
  async onToggled(ch: Channel) {
    if (!ch.record_enabled && this.runtime(ch.id).state === 'watching') await this.stop(ch.id);
  }

  // ---- 메타데이터 캐시 (stale-while-revalidate) ----

  private cachedMeta(ch: Channel): UiMeta | null {
    const c = this.metaCache.get(ch.id);
    if (!c || Date.now() - c.at > META_TTL_MS) void this.refreshMeta(ch);
    return c?.meta ?? null;
  }

  refreshMeta(ch: Channel): Promise<void> {
    let p = this.metaInflight.get(ch.id);
    if (!p) {
      p = this.fetchUiMeta(ch)
        .then((meta) => meta && this.metaCache.set(ch.id, { meta, at: Date.now() }))
        .catch(() => undefined)
        .then(() => void this.metaInflight.delete(ch.id));
      this.metaInflight.set(ch.id, p);
    }
    return p;
  }

  private async fetchUiMeta(ch: Channel): Promise<UiMeta | null> {
    if (ch.platform === 'chzzk') {
      const m = await getLiveMeta(ch, this.store.getChzzkCookies());
      return m && { isLive: m.status === 'OPEN', liveTitle: m.liveTitle, category: m.category, thumbnailUrl: m.thumbnailUrl };
    }
    const y = await getYoutubeMeta(ch.id, this.store.getYoutubeCookiePath());
    return { isLive: y.isLive, liveTitle: y.liveTitle, category: y.category, thumbnailUrl: y.thumbnailUrl };
  }

  // ---- 감시/녹화 루프 ----

  private async loop(ch: Channel, r: Runtime, user: boolean) {
    const sig = r.abort!.signal;
    const name = esc(ch.name);
    try {
      while (!sig.aborted) {
        if (!user && !ch.record_enabled) break; // 자동 경로는 토글이 꺼지면 감시 종료
        const cfg = this.store.getConfig();

        const live = await this.detect(ch);
        if (!live.open) {
          if (!ch.record_enabled) break; // 토글 OFF의 1회성 시작은 방송이 없으면 그대로 끝
          r.state = 'watching';
          void this.notifier.notify(`<b>${name}</b> 채널은 <i>예약녹화 중</i>으로 전환되었습니다.`, { channelId: ch.id, state: 'watching' });
          await sleep(jitteredWaitMs(ch.id, cfg.recheckInterval), sig);
          continue;
        }

        if (ch.platform === 'chzzk' && live.chzzk && ch.recordWatchParty && !this.watchPartyAllowed(ch, live.chzzk)) {
          if (!ch.record_enabled) break;
          r.state = 'watching';
          await sleep(cfg.recheckInterval * 1000, sig);
          continue;
        }

        r.state = 'recording';
        const ended = await (ch.platform === 'chzzk' ? this.recordChzzk(ch, r, live.chzzk!) : this.recordYoutube(ch, r, live.youtube!));
        r.state = 'watching';
        if (sig.aborted) break;

        void this.notifier.notify(`<b>${name}</b> 녹화가 <b>종료</b>되었습니다.`, { channelId: ch.id, state: 'ended' });
        if (ended === 'transient') {
          await sleep(1000, sig); // 일시적 HLS 오류: 쿨다운 없이 바로 재접속
          continue;
        }
        if (ended === 'ended') await sleep(TAIL_COOLDOWN_MS, sig);
        if (!ch.record_enabled) break;
        await sleep(jitteredWaitMs(ch.id, cfg.recheckInterval), sig);
      }
    } catch (e) {
      console.error(`[REC] ${ch.name} 루프 오류:`, e);
    }
  }

  private async detect(ch: Channel): Promise<{ open: boolean; chzzk?: LiveMeta; youtube?: YtMeta }> {
    if (ch.platform === 'youtube') {
      const y = await getYoutubeMeta(ch.id, this.store.getYoutubeCookiePath());
      return { open: y.isLive, youtube: y };
    }
    let m = await getLiveMeta(ch, this.store.getChzzkCookies());
    let open = m?.status === 'OPEN';
    if (!open && (await this.probe(ch))) {
      // 메타가 애매할 때 HLS가 열려 있으면 열린 것으로 본다
      open = true;
      m = { ...(m ?? ({} as LiveMeta)), status: 'OPEN', liveTitle: m?.liveTitle ?? ch.name, resolvedQuality: m?.resolvedQuality ?? ch.quality ?? 'best', recordQuality: m?.recordQuality ?? ch.quality, frameRate: m?.frameRate ?? '', startTime: m?.startTime ?? new Date().toLocaleDateString('sv-SE'), availableQualities: [], category: m?.category ?? '', thumbnailUrl: null, watchPartyNo: m?.watchPartyNo ?? null, watchPartyTag: m?.watchPartyTag ?? '' };
    }
    return { open, chzzk: m ?? undefined };
  }

  private watchPartyAllowed(ch: Channel, m: LiveMeta): boolean {
    if (m.watchPartyNo == null) return false;
    const tag = m.watchPartyTag.toLowerCase();
    return !ch.watchPartyExcludeTags.some((k) => k.trim() && tag.includes(k.toLowerCase()));
  }

  /** streamlink가 첫 바이트를 내보내면 방송이 열린 것이다. 동시 프로브는 MAX_PROBES개까지, 바쁘면 이번 라운드는 건너뛴다. */
  private async probe(ch: Channel, timeoutSec = 6): Promise<boolean> {
    if (this.probes >= MAX_PROBES) return false;
    this.probes++;
    const p = spawnGroup(bin('streamlink'), chzzkProbeArgs(ch, this.store.getChzzkCookies(), timeoutSec), { stdio: ['ignore', 'pipe', 'ignore'] });
    try {
      return await new Promise<boolean>((resolve) => {
        const t = setTimeout(() => resolve(false), (timeoutSec + 2) * 1000);
        p.stdout!.once('data', () => (clearTimeout(t), resolve(true)));
        p.once('error', () => (clearTimeout(t), resolve(false)));
        p.once('close', () => (clearTimeout(t), resolve(false)));
      });
    } finally {
      this.probes--;
      signalGroup(p, 'SIGKILL');
    }
  }

  /** streamlink로 한 회차 녹화. 'ended' = 방송 종료, 'transient' = 일시 오류, 'exit' = 그 외. */
  private async recordChzzk(ch: Channel, r: Runtime, meta: LiveMeta): Promise<'ended' | 'transient' | 'exit'> {
    const cfg = this.store.getConfig();
    const dir = absFromRoot(ch.output_dir);
    fs.mkdirSync(dir, { recursive: true });
    const filename = uniqueFilename(
      dir,
      recordFilename(cfg.filenamePattern, { channelName: ch.name, title: meta.liveTitle, startTime: meta.startTime, quality: meta.recordQuality, fps: meta.frameRate, ext: ch.extension }, 'chzzk'),
    );
    const output = path.join(dir, filename);
    const proc = spawnGroup(bin('streamlink'), chzzkRecordArgs(ch, meta, this.store.getChzzkCookies(), output), { stdio: ['ignore', 'pipe', 'pipe'] });
    this.attach(r, proc, output);
    void this.notifier.notify(`<b>${esc(ch.name)}</b> 채널의 녹화가 <i>시작</i>되었습니다.`, { channelId: ch.id, state: 'recording' });

    let streamEnded = false;
    let transient = false;
    onLines(proc.stdout, (l) => {
      if (l.includes('Stream ended')) streamEnded = true;
    });
    proc.stderr!.on('data', (d: Buffer) => {
      const s = d.toString('utf8');
      if (TRANSIENT.some((re) => re.test(s))) transient = true;
    });
    await exited(proc);
    this.detach(r);

    if (cfg.autoPostProcessing && fs.existsSync(output)) this.schedulePost(output);

    if (r.stopping) return 'exit';
    if (streamEnded && transient) {
      // 일시 오류인지 확인: 메타와 HLS가 둘 다 열려 있으면 바로 재접속
      const m = await getLiveMeta(ch, this.store.getChzzkCookies());
      if (m?.status === 'OPEN' && (await this.probe(ch))) return 'transient';
    }
    return streamEnded ? 'ended' : 'exit';
  }

  /** yt-dlp로 한 회차 녹화. 중지는 SIGINT로 보내 mux까지 마치게 한다. */
  private async recordYoutube(ch: Channel, r: Runtime, y: YtMeta): Promise<'ended' | 'exit'> {
    const cfg = this.store.getConfig();
    const dir = absFromRoot(ch.output_dir);
    fs.mkdirSync(dir, { recursive: true });
    const q = ytNameQuality(ch.quality, y);
    const start = y.startTime ? new Date(y.startTime) : new Date();
    const filename = recordFilename(cfg.filenamePattern, { channelName: ch.name, title: y.liveTitle, startTime: start.toLocaleDateString('sv-SE'), quality: q.quality, fps: q.fps, ext: q.ext }, 'youtube');
    const final = path.join(dir, uniqueFilename(dir, filename));
    const prefix = final.slice(0, -path.extname(final).length);
    const tmpDir = path.join(dir, '_ytdlp_tmp', ch.id.replace(/[^0-9A-Za-z._-]+/g, '_'));
    fs.mkdirSync(tmpDir, { recursive: true });

    const url = y.watchUrl ?? `https://www.youtube.com/watch?v=${y.videoId}`;
    const args = ytDlpArgs({ url, outDir: dir, tmpDir, outTemplate: path.basename(prefix) + '.%(ext)s', quality: /^(\d+p(60)?|best)$/i.test(ch.quality) ? ch.quality : 'best', cookieFile: this.store.getYoutubeCookiePath(), poToken: cfg.ytPoToken, sabr: fs.existsSync(path.join(path.dirname(bin('yt-dlp')), '_internal')) });
    const proc = spawnGroup(bin('yt-dlp'), args, { cwd: tmpDir, stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, PATH: [path.dirname(bin('ffmpeg')), process.env.PATH ?? ''].join(path.delimiter) } });
    this.attach(r, proc, final);
    void this.notifier.notify(`<b>${esc(ch.name)}</b> 채널의 녹화가 <i>시작</i>되었습니다.`, { channelId: ch.id, state: 'recording' });

    let reported: string | null = null;
    const scan = (l: string) => {
      const m = /^__FINAL__:(.*)$/.exec(l);
      if (m) {
        try {
          reported = JSON.parse(m[1]);
        } catch {
          /* 무시 */
        }
      }
    };
    onLines(proc.stdout, scan);
    onLines(proc.stderr, () => undefined);
    await exited(proc);
    this.detach(r);

    const file = [reported, final].find((p): p is string => !!p && fs.existsSync(p) && fs.statSync(p).size >= MIN_OK_SIZE);
    if (file) {
      if (cfg.moveAfterProcessingEnabled && cfg.moveAfterProcessing) {
        try {
          moveInto(file, absFromRoot(cfg.moveAfterProcessing));
        } catch (e) {
          console.error('[YT] 이동 실패', e);
        }
      }
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
    return file ? 'ended' : 'exit';
  }

  private attach(r: Runtime, proc: ChildProcess, file: string) {
    r.proc = proc;
    r.file = file;
    r.startedAt = Date.now();
  }

  private detach(r: Runtime) {
    r.proc = null;
    r.file = null;
    r.startedAt = null;
  }

  private stopProc(p: ChildProcess, platform?: string) {
    return terminate(p, platform === 'youtube' ? 'SIGINT' : 'SIGTERM', platform === 'youtube' ? 60_000 : 5000);
  }

  /** 같은 파일을 두 번 후처리하지 않는다. 후처리는 녹화 루프를 막지 않고 뒤에서 돈다. */
  private schedulePost(file: string) {
    if (this.postInflight.has(file)) return;
    this.postInflight.add(file);
    const task = postProcess(file, this.store.getConfig(), (m) => console.log(m))
      .catch((e) => console.error('[POST]', e))
      .finally(() => {
        this.postInflight.delete(file);
        this.postTasks.delete(task);
      });
    this.postTasks.add(task);
  }

  /** 후처리 중인 원본/결과 경로 (파일 관리자가 잠금 표시에 쓴다). */
  busyPaths(): string[] {
    return [...this.rt.values()].flatMap((r) => (r.file ? [r.file] : [])).concat([...this.postInflight]);
  }
}
