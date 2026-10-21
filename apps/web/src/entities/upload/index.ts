import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';

export interface UploadSettings {
  pool: number;
  rate_mbps: number;
  scan_interval_sec: number;
  stable_sec: number;
  max_sec: number;
  privacy: 'unlisted' | 'private' | 'public';
  tags: string[];
  description: string;
  auto_since: string;
}

export interface QueueRow {
  name: string;
  state: 'uploading' | 'waiting' | 'error' | 'queued' | 'done';
  msg: string;
  video_id: string | null;
  privacy: string | null;
}

export interface UploadSnapshot {
  auth_error: string;
  has_token: boolean;
  settings: UploadSettings;
  items: QueueRow[];
}

export const useUploads = () => useQuery({ queryKey: ['uploads'], queryFn: () => api<UploadSnapshot>('/uploads'), refetchInterval: 5000 });

export function useSaveUploadSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { settings?: Partial<UploadSettings>; token?: string }) => api('/uploads/settings', { body: v }),
    onSettled: () => qc.invalidateQueries({ queryKey: ['uploads'] }),
  });
}

export function useEnqueueUploads() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (paths: string[]) => api<{ results: { src: string; ok: boolean; error?: string }[] }>('/uploads/enqueue', { body: { paths } }),
    onSettled: () => qc.invalidateQueries({ queryKey: ['uploads'] }),
  });
}

export function useReauthenticateUpload() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (refreshToken: string) => api<{ ok: boolean }>('/uploads/reauth', { body: { refresh_token: refreshToken } }),
    onSettled: () => qc.invalidateQueries({ queryKey: ['uploads'] }),
    gcTime: 0,
  });
}
