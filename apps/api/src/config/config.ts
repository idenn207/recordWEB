import { normalizeHandle } from '../x/x.js';

// json/config.json 과 json/channels.json 의 스키마. 기존 파일과 키 이름이 같아서 NAS의 설정을 그대로 읽는다.
export interface Config {
  telegram_enabled: boolean;
  autoRecordingMode: boolean;
  autoPostProcessing: boolean;
  deleteAfterPostProcessing: boolean;
  removeFixedPrefix: boolean;
  moveAfterProcessingEnabled: boolean;
  moveAfterProcessing: string;
  recheckInterval: number;
  filenamePattern: string;
  stream_copy: boolean;
  video_codec: string;
  preset: string;
  postprocess_resolution: 'source' | '1080p' | '720p' | '480p';
  use_bitrate_mode: boolean;
  video_quality: number;
  video_bitrate: string;
  vbv_maxrate: string;
  vbv_bufsize: string;
  audio_codec: string;
  audio_bitrate: string;
  extra_ffmpeg_options: string;
  port: number;
  fileManagerEnabled: boolean;
  fileManagerRoots: string[];
  fileManagerMode: 'blacklist' | 'whitelist';
  fileManagerReadOnly: boolean;
  trashEnabled: boolean;
  ytPoToken: string;
}

export const DEFAULT_CONFIG: Config = {
  telegram_enabled: false,
  autoRecordingMode: false,
  autoPostProcessing: true,
  deleteAfterPostProcessing: true,
  removeFixedPrefix: true,
  moveAfterProcessingEnabled: false,
  moveAfterProcessing: '',
  recheckInterval: 60,
  filenamePattern: '[{start_time}] {channel_name} {safe_live_title} {record_quality}{frame_rate}{file_extension}',
  stream_copy: true,
  video_codec: 'libx264',
  preset: 'fast',
  postprocess_resolution: 'source',
  use_bitrate_mode: true,
  video_quality: 33,
  video_bitrate: '1000k',
  vbv_maxrate: '',
  vbv_bufsize: '',
  audio_codec: 'aac',
  audio_bitrate: '192k',
  extra_ffmpeg_options: '',
  port: 5000,
  fileManagerEnabled: false,
  fileManagerRoots: [],
  fileManagerMode: 'blacklist',
  fileManagerReadOnly: false,
  trashEnabled: false,
  ytPoToken: '',
};

const bool = (v: unknown, d: boolean) =>
  typeof v === 'boolean' ? v : v == null ? d : !['0', 'false', 'no', 'off', ''].includes(String(v).toLowerCase());
const int = (v: unknown, d: number) => (v !== '' && v != null && Number.isFinite(Number(v)) ? Math.trunc(Number(v)) : d);
const str = (v: unknown, d: string) => (v == null ? d : String(v));

/** 기존 _normalizeConfig 대응. 모르는 키(예: 예전 GPU 설정)는 그대로 보존해 파일을 망가뜨리지 않는다. */
export function normalizeConfig(raw: unknown): Config {
  const r = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const d = DEFAULT_CONFIG;
  const resolutions = ['source', '1080p', '720p', '480p'];
  const resIn = String(r.postprocess_resolution ?? 'source').toLowerCase();
  const roots = Array.isArray(r.fileManagerRoots) ? r.fileManagerRoots : typeof r.fileManagerRoots === 'string' ? [r.fileManagerRoots] : [];
  return {
    ...(r as object),
    telegram_enabled: bool(r.telegram_enabled, d.telegram_enabled),
    autoRecordingMode: bool(r.autoRecordingMode, d.autoRecordingMode),
    autoPostProcessing: bool(r.autoPostProcessing, d.autoPostProcessing),
    deleteAfterPostProcessing: bool(r.deleteAfterPostProcessing, d.deleteAfterPostProcessing),
    removeFixedPrefix: bool(r.removeFixedPrefix, d.removeFixedPrefix),
    moveAfterProcessingEnabled: bool(r.moveAfterProcessingEnabled, d.moveAfterProcessingEnabled),
    moveAfterProcessing: str(r.moveAfterProcessing, d.moveAfterProcessing),
    recheckInterval: Math.max(10, int(r.recheckInterval, d.recheckInterval)),
    filenamePattern: str(r.filenamePattern, d.filenamePattern) || d.filenamePattern,
    stream_copy: bool(r.stream_copy, d.stream_copy),
    video_codec: str(r.video_codec, d.video_codec),
    preset: str(r.preset, d.preset),
    postprocess_resolution: (resolutions.includes(resIn) ? resIn : 'source') as Config['postprocess_resolution'],
    use_bitrate_mode: bool(r.use_bitrate_mode, d.use_bitrate_mode),
    video_quality: int(r.video_quality, d.video_quality),
    video_bitrate: str(r.video_bitrate, d.video_bitrate),
    vbv_maxrate: str(r.vbv_maxrate, d.vbv_maxrate),
    vbv_bufsize: str(r.vbv_bufsize, d.vbv_bufsize),
    audio_codec: str(r.audio_codec, d.audio_codec),
    audio_bitrate: str(r.audio_bitrate, d.audio_bitrate),
    extra_ffmpeg_options: str(r.extra_ffmpeg_options, d.extra_ffmpeg_options),
    port: int(r.port, d.port),
    // 기존 앱은 loginMode가 꺼져 있으면 파일 관리자를 강제로 껐다. 로그인은 네트워크 경계로 대체했으므로 이 결합은 없앤다.
    fileManagerEnabled: bool(r.fileManagerEnabled, d.fileManagerEnabled),
    fileManagerRoots: roots.map((p) => String(p).trim()).filter(Boolean),
    fileManagerMode: String(r.fileManagerMode ?? 'blacklist').toLowerCase() === 'whitelist' ? 'whitelist' : 'blacklist',
    fileManagerReadOnly: bool(r.fileManagerReadOnly, d.fileManagerReadOnly),
    trashEnabled: bool(r.trashEnabled, d.trashEnabled),
    ytPoToken: str(r.ytPoToken, d.ytPoToken),
  };
}

export type Platform = 'chzzk' | 'youtube' | 'x';
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
  x_user_id?: string; // X 숫자 사용자 ID. 비어 있으면 핸들로 자동 조회한 뒤 저장한다
}

const dedupeTags = (v: unknown): string[] => {
  const parts = Array.isArray(v) ? v.map(String) : typeof v === 'string' ? v.split(',') : [];
  const seen = new Set<string>();
  return parts.map((s) => s.trim()).filter((s) => s && !seen.has(s.toLowerCase()) && seen.add(s.toLowerCase()));
};

export function normalizeChannel(raw: unknown): Channel | null {
  const r = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>;
  const platform = String(r.platform ?? '').trim().toLowerCase();
  const id = String(r.id ?? r.channelId ?? '').trim();
  if ((platform !== 'chzzk' && platform !== 'youtube' && platform !== 'x') || !id) return null;
  const c: Channel = {
    platform,
    id: platform === 'x' ? normalizeHandle(id) : id,
    name: String(r.name ?? '').trim(),
    output_dir: String(r.output_dir ?? (platform === 'x' ? 'xspaces' : 'output')),
    quality: String(r.quality ?? 'best'),
    extension: platform === 'youtube' ? '.mkv' : platform === 'x' ? '.m4a' : String(r.extension ?? '.ts'),
    record_enabled: bool(r.record_enabled, false),
    recordWatchParty: platform === 'chzzk' && bool(r.recordWatchParty, false),
    watchPartyExcludeTags: dedupeTags(r.watchPartyExcludeTags),
  };
  if (r.yt_auto_upload != null) c.yt_auto_upload = bool(r.yt_auto_upload, false);
  if (r.yt_playlist_id != null) c.yt_playlist_id = String(r.yt_playlist_id).trim();
  if (platform === 'x' && r.x_user_id) c.x_user_id = String(r.x_user_id).trim();
  return c;
}

/** 기존 normalizeChannelsList 대응: 잘못된 항목은 버리고 (platform,id) 중복은 먼저 나온 것을 남긴다. */
export function normalizeChannels(list: unknown): Channel[] {
  const seen = new Set<string>();
  const out: Channel[] = [];
  for (const raw of Array.isArray(list) ? list : []) {
    const c = normalizeChannel(raw);
    if (!c || seen.has(`${c.platform}:${c.id}`)) continue;
    seen.add(`${c.platform}:${c.id}`);
    out.push(c);
  }
  return out;
}
