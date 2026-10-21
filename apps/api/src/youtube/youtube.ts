import fs from 'node:fs';

export interface YtMeta {
  isLive: boolean;
  liveTitle: string;
  category: string;
  thumbnailUrl: string | null;
  watchUrl: string | null;
  videoId: string | null;
  fps: number | null;
  height: number | null;
  startTime: string | null; // ISO
}

export const liveUrlOf = (id: string) =>
  id.startsWith('UC') ? `https://www.youtube.com/channel/${id}/live` : `https://www.youtube.com/${id.startsWith('@') ? id : '@' + id}/live`;

/** Netscape 쿠키 파일에서 youtube.com 쿠키를 Cookie 헤더로 만든다. */
export function cookieHeaderFrom(file: string | null): string | null {
  if (!file || !fs.existsSync(file)) return null;
  const pairs: string[] = [];
  for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
    const f = line.replace(/^#HttpOnly_/, '').split('\t');
    if (f.length >= 7 && /(^|\.)youtube\.com$|(^|\.)google\.com$/.test(f[0].replace(/^\./, ''))) pairs.push(`${f[5]}=${f[6]}`);
  }
  return pairs.length ? pairs.join('; ') : null;
}

/** ytInitialPlayerResponse를 페이지에서 꺼낸다. */
export function extractPlayer(html: string): any | null {
  for (const re of [/ytInitialPlayerResponse\s*=\s*({.*?});/s, /"ytInitialPlayerResponse"\s*:\s*({.*?})\s*,\s*"(?:ytInitialData|INNERTUBE)/s]) {
    const m = re.exec(html);
    if (m) {
      try {
        return JSON.parse(m[1]);
      } catch {
        /* 다음 패턴 시도 */
      }
    }
  }
  return null;
}

/** 진짜 라이브 중일 때만 isLive=true (종료/처리중인데 playabilityStatus=OK인 경우를 걸러낸다). */
export function parseLivePage(html: string, finalUrl = ''): YtMeta {
  const player = extractPlayer(html);
  const videoId =
    player?.videoDetails?.videoId ?? /"videoId"\s*:\s*"([A-Za-z0-9_-]{11})"/.exec(html)?.[1] ?? (finalUrl.includes('/watch') ? new URL(finalUrl).searchParams.get('v') : null);
  const meta: YtMeta = {
    isLive: false,
    liveTitle: '정보 없음',
    category: '정보 없음',
    thumbnailUrl: videoId ? `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg` : null,
    watchUrl: videoId ? `https://www.youtube.com/watch?v=${videoId}` : null,
    videoId: videoId ?? null,
    fps: null,
    height: null,
    startTime: null,
  };
  if (!player) return meta;

  const vd = player.videoDetails ?? {};
  const micro = player.microformat?.playerMicroformatRenderer ?? {};
  const lb = micro.liveBroadcastDetails ?? {};
  meta.liveTitle = vd.title ?? micro.title?.simpleText ?? '정보 없음';
  meta.category = micro.category ?? vd.category ?? '정보 없음';
  meta.isLive = Boolean(lb.isLiveNow) && !lb.endTimestamp && String(player.playabilityStatus?.status ?? '').toUpperCase() !== 'LIVE_STREAM_OFFLINE';
  meta.startTime = lb.startTimestamp ?? lb.scheduledStartTime ?? null;

  const fmts: any[] = player.streamingData?.adaptiveFormats ?? [];
  const fps = fmts.map((f) => f.fps).filter(Boolean);
  const heights = fmts
    .filter((f) => String(f.mimeType ?? '').includes('video/'))
    .map((f) => (Number.isInteger(f.height) ? f.height : parseInt(/^(\d+)p/.exec(f.qualityLabel ?? '')?.[1] ?? '', 10)))
    .filter(Number.isFinite);
  meta.fps = fps.length ? Math.max(...fps) : null;
  meta.height = heights.length ? Math.max(...heights) : null;
  return meta;
}

export async function getYoutubeMeta(channelId: string, cookieFile: string | null): Promise<YtMeta> {
  const empty = parseLivePage('');
  const cookie = cookieHeaderFrom(cookieFile);
  const fetchPage = async (withCookie: boolean) => {
    const res = await fetch(liveUrlOf(channelId), {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        ...(withCookie && cookie ? { Cookie: cookie } : {}),
      },
      signal: AbortSignal.timeout(10000),
    });
    return { html: await res.text(), url: res.url };
  };
  try {
    const page = await fetchPage(Boolean(cookie)).catch(() => (cookie ? fetchPage(false) : Promise.reject()));
    return parseLivePage(page.html, page.url);
  } catch {
    return empty;
  }
}

/** yt-dlp 품질 선택자. 1080p60 / 1080p / best. */
export function formatSelector(quality: string, sabr = false): string {
  const q = (quality || 'best').trim().toLowerCase();
  const fallback = 'bv*+ba/b';
  const best = sabr ? `ba[protocol=sabr]+bv[protocol=sabr]/${fallback}` : fallback;
  let m = /^(\d{3,4})p(\d{2})$/.exec(q);
  if (m) {
    const sel = `bv*[height<=${m[1]}][fps<=${m[2]}]+ba/b[height<=${m[1]}][fps<=${m[2]}]`;
    return sabr ? `bv*[protocol=sabr][height<=${m[1]}][fps<=${m[2]}]+ba[protocol=sabr]/${sel}/${fallback}` : `${sel}/${fallback}`;
  }
  m = /^(\d{3,4})p$/.exec(q);
  if (m) {
    const sel = `bv*[height<=${m[1]}]+ba/b[height<=${m[1]}]`;
    return sabr ? `bv*[protocol=sabr][height<=${m[1]}]+ba[protocol=sabr]/${sel}/${fallback}` : `${sel}/${fallback}`;
  }
  return best;
}

/** PO 토큰 입력을 "<client>.<scope>+<token>" 쉼표 목록으로 맞춘다. 순수 토큰은 mweb.gvs로 취급. */
export function normalizePoToken(raw: string): { token: string; clients: string[] } {
  const parts = raw.replace(/;/g, ',').split(',').map((s) => s.trim()).filter(Boolean);
  const toks = [...new Set(parts.map((p) => (p.includes('+') && p.split('+')[0].includes('.') ? p : `mweb.gvs+${p}`)))];
  const order = ['mweb', 'web', 'ios', 'android', 'tv'];
  const found = new Set(toks.map((t) => t.split('+')[0].split('.')[0]));
  const clients = [...order.filter((c) => found.has(c)), ...[...found].filter((c) => !order.includes(c)).sort()];
  return { token: toks.join(','), clients };
}

export function extractorArgs(poToken: string, sabr: boolean): string {
  const { token, clients } = normalizePoToken(poToken);
  const args = [`player-client=${!clients.length ? 'default,mweb' : clients.join() === 'web' ? 'web' : 'default,' + clients.join(',')}`];
  if (sabr) args.push('formats=duplicate');
  if (token) args.push(`po_token=${token}`);
  return 'youtube:' + args.join(';');
}
