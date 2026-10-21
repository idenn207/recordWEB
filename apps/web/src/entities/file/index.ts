import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';

export interface FileItem {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  mtime: string;
  ext: string;
  locked?: boolean;
}

export interface DiskUsage {
  path: string;
  label?: string;
  total: number;
  used: number;
  free: number;
  percent: number;
}

export const useFileRoots = () => useQuery({ queryKey: ['file-roots'], queryFn: () => api<{ roots: string[]; default: string | null }>('/files/roots'), retry: false });

export const useFileList = (path: string | null, showHidden: boolean) =>
  useQuery({
    queryKey: ['files', path, showHidden],
    queryFn: () => api<{ path: string; items: FileItem[] }>(`/files/ls?path=${encodeURIComponent(path ?? '')}&show_hidden=${showHidden}`),
    enabled: !!path,
    retry: false,
    refetchInterval: 15000, // 녹화/후처리 중인 파일의 잠금 표시와 크기를 따라간다
  });

export const useFileDisks = () => useQuery({ queryKey: ['file-disks'], queryFn: () => api<{ usages: DiskUsage[] }>('/files/disk-usage'), retry: false, refetchInterval: 60000 });

/** 파일 변경 작업 후 목록과 디스크 사용량을 갱신한다. */
export function useFileAction<V, R = unknown>(fn: (v: V) => Promise<R>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ['files'] });
      void qc.invalidateQueries({ queryKey: ['file-disks'] });
    },
  });
}

export const fileApi = {
  mkdir: (path: string, new_name: string) => api<{ created: string }>('/files/mkdir', { body: { path, new_name } }),
  rename: (path: string, new_name: string) => api<{ path: string }>('/files/rename', { body: { path, new_name } }),
  move: (srcs: string[], dst_dir: string) => api<{ moved: string[] }>('/files/move', { body: { srcs, dst_dir } }),
  remove: (paths: string[], hard: boolean) => api<{ deleted: string[] }>('/files/delete', { body: { paths, hard } }),
  streamCopy: (paths: string[]) => api<{ results: { src: string; ok: boolean; error?: string }[] }>('/files/streamcopy', { body: { paths } }),
  downloadUrl: (path: string) => `/api/files/download?path=${encodeURIComponent(path)}`,
};
