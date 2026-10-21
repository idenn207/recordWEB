import { useQuery } from '@tanstack/react-query';
import { api } from '@/shared/api/client';

export interface Metrics {
  cpu: { percent: number; model: string; cores: number };
  memory: { total: number; used: number; percent: number };
  uptimeSec: number;
  hostname: string;
}

export interface Disk {
  path: string;
  total: number;
  used: number;
  free: number;
  percent: number;
}

export const useMetrics = () => useQuery({ queryKey: ['metrics'], queryFn: () => api<Metrics>('/system/metrics'), refetchInterval: 5000 });
export const useDisks = () => useQuery({ queryKey: ['disks'], queryFn: () => api<Disk[]>('/system/disks'), refetchInterval: 60000 });
