import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';

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

export interface Secrets {
  chzzk: { NID_AUT?: string; NID_SES?: string };
  youtubeCookie: string;
  telegram: { token: string; chatId: string };
}

export const useConfig = () => useQuery({ queryKey: ['config'], queryFn: () => api<Config>('/config') });
export const useSecrets = () => useQuery({ queryKey: ['secrets'], queryFn: () => api<Secrets>('/secrets') });

export function useSaveConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<Config>) => api<Config>('/config', { method: 'PUT', body: patch }),
    onSuccess: (cfg) => qc.setQueryData(['config'], cfg),
  });
}

export function useSaveSecrets() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (s: Partial<Secrets>) => api('/secrets', { method: 'PUT', body: s }),
    onSettled: () => qc.invalidateQueries({ queryKey: ['secrets'] }),
  });
}

export const testTelegram = () => api('/telegram/test', { method: 'POST' });
