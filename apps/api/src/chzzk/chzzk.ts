import { ChzzkCookies } from '../config/store.service.js';
import { sleep } from '../lib/text.js';

export interface LiveMeta {
  status: string; // 'OPEN' | 'CLOSE' ...
  liveId?: number;
  liveTitle: string;
  category: string;
  thumbnailUrl: string | null;
  avatarUrl?: string | null; // 채널 프로필 이미지. 방송 중이 아니어도 있다
  startTime: string; // YYYY-MM-DD
  recordQuality: string; // 파일명용 라벨 (예: 1080p)
  frameRate: string; // 파일명용 (예: 60)
  resolvedQuality: string; // streamlink에 넘길 품질
  availableQualities: string[];
  watchPartyNo: number | null;
  watchPartyTag: string;
}

const UA = process.platform === 'win32' ? 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' : 'Mozilla/5.0 (X11; Linux x86_64)';

export function authHeaders(c: ChzzkCookies): Record<string, string> {
  const cookie = [c.NID_AUT && `NID_AUT=${c.NID_AUT}`, c.NID_SES && `NID_SES=${c.NID_SES}`].filter(Boolean).join('; ');
  return cookie ? { 'User-Agent': UA, Cookie: cookie } : { 'User-Agent': UA };
}

const UNKNOWN_QUALITY = '알 수 없는 품질';
const UNKNOWN_FPS = '알 수 없는 프레임 레이트';

interface Variant {
  height: number;
  label: string;
  fps: string;
}

/** livePlaybackJson의 트랙 중 사용자가 고른 품질에 맞는 것을 고른다. 못 찾으면 best로 폴백. */
export function resolveQuality(userSelected: string, livePlaybackJson: string) {
  const want = (userSelected || 'best').trim().toLowerCase();
  const variants: Variant[] = [];
  try {
    for (const track of JSON.parse(livePlaybackJson).media ?? []) {
      for (const enc of track.encodingTrack ?? []) {
        const height = parseInt(enc.videoHeight, 10);
        if (!Number.isFinite(height)) continue;
        variants.push({
          height,
          label: String(enc.encodingTrackId),
          fps: enc.videoFrameRate ? String(Math.trunc(Number(enc.videoFrameRate))) : UNKNOWN_FPS,
        });
      }
    }
  } catch {
    /* 파싱 실패는 variants 비어 있음으로 처리 */
  }
  if (!variants.length) return { recordQuality: UNKNOWN_QUALITY, frameRate: UNKNOWN_FPS, resolvedQuality: want, availableQualities: [] as string[] };

  const best = variants.reduce((a, b) => (b.height > a.height ? b : a));
  const available = [...variants].sort((a, b) => a.height - b.height).map((v) => v.label);
  if (want === 'best') return { recordQuality: best.label, frameRate: best.fps, resolvedQuality: 'best', availableQualities: available };

  const exact = variants.find((v) => v.label === want);
  const target = /^(\d+)/.exec(want)?.[1];
  const under = target ? variants.filter((v) => v.height <= Number(target)) : [];
  const chosen = exact ?? (under.length ? under.reduce((a, b) => (b.height > a.height ? b : a)) : null);
  return chosen
    ? { recordQuality: chosen.label, frameRate: chosen.fps, resolvedQuality: chosen.label, availableQualities: available }
    : { recordQuality: best.label, frameRate: best.fps, resolvedQuality: 'best', availableQualities: available };
}

async function getJson(url: string, headers: Record<string, string>, retries = 3): Promise<{ status: number | null; body: any }> {
  let backoff = 700;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(url, { headers, signal: AbortSignal.timeout(8000) });
      if (res.status === 200) return { status: 200, body: await res.json().catch(() => null) };
      if ([404, 410].includes(res.status)) return { status: res.status, body: null };
      if ([429, 500, 502, 503, 504].includes(res.status) && attempt < retries) {
        await sleep(backoff);
        backoff *= 1.8;
        continue;
      }
      return { status: res.status, body: null };
    } catch {
      if (attempt < retries) {
        await sleep(backoff);
        backoff *= 1.8;
        continue;
      }
      return { status: null, body: null };
    }
  }
  return { status: null, body: null };
}

const today = () => new Date().toLocaleDateString('sv-SE'); // YYYY-MM-DD (로컬 시간)

/** 방송 상태/메타데이터. 방송 중이 아니면 status가 CLOSE, 조회 실패(네트워크/서버 오류)는 null. */
export async function getLiveMeta(channel: { id: string; name: string; quality: string }, cookies: ChzzkCookies): Promise<LiveMeta | null> {
  const { status, body } = await getJson(`https://api.chzzk.naver.com/service/v3/channels/${channel.id}/live-detail`, authHeaders(cookies));
  const closed: LiveMeta = {
    status: 'CLOSE',
    liveTitle: '방송 제목 없음',
    category: '카테고리 없음',
    thumbnailUrl: null,
    startTime: today(),
    recordQuality: UNKNOWN_QUALITY,
    frameRate: UNKNOWN_FPS,
    resolvedQuality: channel.quality || 'best',
    availableQualities: [],
    watchPartyNo: null,
    watchPartyTag: '',
  };
  if (status === 404 || status === 410) return closed;
  const c = body?.content;
  if (status !== 200 || !c) return null;

  const open = c.status === 'OPEN';
  const q = c.livePlaybackJson
    ? resolveQuality(channel.quality, c.livePlaybackJson)
    : { recordQuality: String(channel.quality || 'best'), frameRate: UNKNOWN_FPS, resolvedQuality: channel.quality || 'best', availableQualities: [] as string[] };
  return {
    status: c.status ?? 'CLOSE',
    liveId: c.liveId,
    liveTitle: c.liveTitle || '방송 제목 없음',
    category: c.liveCategoryValue || '카테고리 없음',
    thumbnailUrl: open && c.liveImageUrl ? String(c.liveImageUrl).replace('{type}', '360') : null,
    avatarUrl: c.channel?.channelImageUrl ? String(c.channel.channelImageUrl) : null,
    startTime: /^\d{4}-\d\d-\d\d/.test(c.openDate ?? '') ? c.openDate.slice(0, 10) : today(),
    watchPartyNo: c.watchPartyNo ?? null,
    watchPartyTag: c.watchPartyTag || '',
    ...q,
  };
}
