import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';
import type { Channel, ChannelWithStatus } from '../model/types';

const KEY = ['channels'] as const;

/** 채널 설정과 실시간 상태를 함께 폴링한다. */
export function useChannels(intervalMs = 4000) {
  return useQuery({ queryKey: KEY, queryFn: () => api<ChannelWithStatus[]>('/channels'), refetchInterval: intervalMs });
}

/** 변이 후 목록을 다시 불러온다. */
function useChannelMutation<V, R = unknown>(fn: (v: V) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSettled: () => qc.invalidateQueries({ queryKey: KEY }) });
}

export const useStartChannel = () => useChannelMutation((id: string) => api(`/channels/${encodeURIComponent(id)}/start`, { method: 'POST' }));
export const useStopChannel = () => useChannelMutation((id: string) => api(`/channels/${encodeURIComponent(id)}/stop`, { method: 'POST' }));
export const useToggleChannel = () => useChannelMutation((id: string) => api<{ record_enabled: boolean }>(`/channels/${encodeURIComponent(id)}/toggle`, { method: 'POST' }));
export const useStartAll = () => useChannelMutation(() => api('/recording/start-all', { method: 'POST' }));
export const useStopAll = () => useChannelMutation(() => api('/recording/stop-all', { method: 'POST' }));
export const useAddChannel = () => useChannelMutation((c: Partial<Channel>) => api<Channel>('/channels', { body: c }));
export const useUpdateChannel = () => useChannelMutation(({ id, patch }: { id: string; patch: Partial<Channel> }) => api<Channel>(`/channels/${encodeURIComponent(id)}`, { method: 'PUT', body: patch }));
export interface XCheckResult {
  steps: { name: string; ok: boolean; detail: string }[];
  userId?: string;
  spaceId?: string | null;
}

/** X 연결 확인: 쿠키 → 사용자 ID → 스페이스 조회를 단계별로 돌려준다. */
export const useCheckX = () => useMutation({ mutationFn: (v: { handle: string; userId?: string }) => api<XCheckResult>('/x/check', { body: v }) });

export const useDeleteChannel = () => useChannelMutation((id: string) => api(`/channels/${encodeURIComponent(id)}`, { method: 'DELETE' }));
