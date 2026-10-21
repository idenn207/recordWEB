export type Platform = 'chzzk' | 'youtube' | 'x';
export type RunState = 'idle' | 'watching' | 'recording';

export interface LiveInfo {
  isLive: boolean;
  liveTitle: string;
  category: string;
  thumbnailUrl: string | null;
}

export interface ChannelStatus {
  state: RunState;
  filename: string;
  duration: string;
  startedAt: number | null;
  meta: LiveInfo | null;
  /** 감시를 막는 문제(쿠키 만료 등). 비어 있으면 정상 */
  error: string;
}

export interface Channel {
  platform: Platform;
  id: string;
  name: string;
  output_dir: string;
  quality: string;
  extension: string;
  record_enabled: boolean;
  recordWatchParty: boolean;
  watchPartyExcludeTags: string[];
  yt_auto_upload?: boolean;
  yt_playlist_id?: string;
  x_user_id?: string;
}

export interface ChannelWithStatus extends Channel {
  status: ChannelStatus;
}

export const QUALITIES: Record<Platform, string[]> = {
  chzzk: ['best', '1080p', '720p', '480p', '360p', '144p'],
  youtube: ['best', '1080p60', '1080p', '720p60', '720p', '480p'],
  x: ['best'],
};

export const PLATFORM_NAME: Record<Platform, string> = { chzzk: '치지직', youtube: '유튜브', x: 'X 스페이스' };

/** 대시보드 정렬 순서: 녹화 중 → 방송 중(미녹화) → 예약 → 대기 */
export function priority(c: ChannelWithStatus): number {
  if (c.status.state === 'recording') return 0;
  if (c.status.meta?.isLive) return 1;
  if (c.status.state === 'watching') return 2;
  return 3;
}
