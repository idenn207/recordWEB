import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/shared/api/client';

export interface AuthState {
  setup: boolean;
  user: string | null;
}

export interface Activity {
  at: string;
  type: 'login' | 'login-fail' | 'logout' | 'setup' | 'password' | 'logout-all' | 'secrets' | 'config';
  ip: string;
  detail?: string;
}

export const ACTIVITY_LABEL: Record<Activity['type'], string> = {
  login: '로그인',
  'login-fail': '로그인 실패',
  logout: '로그아웃',
  setup: '계정 생성',
  password: '비밀번호 변경',
  'logout-all': '모든 기기에서 로그아웃',
  secrets: '쿠키·토큰 변경',
  config: '설정 변경',
};

export const useAuth = () => useQuery({ queryKey: ['auth'], queryFn: () => api<AuthState>('/auth/state'), staleTime: 60_000, retry: false });

/** 로그인 상태가 바뀌면 보관 중인 모든 데이터를 버린다 (다른 계정의 화면이 남지 않게). */
function useAuthMutation<V>(fn: (v: V) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async () => {
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== 'auth' });
      await qc.invalidateQueries({ queryKey: ['auth'] });
    },
  });
}

export const useLogin = () => useAuthMutation((v: { username: string; password: string }) => api('/auth/login', { body: v }));
export const useSetup = () => useAuthMutation((v: { username: string; password: string }) => api('/auth/setup', { body: v }));
export const useLogout = () => useAuthMutation(() => api('/auth/logout', { method: 'POST', body: {} }));
export const useLogoutAll = () => useAuthMutation(() => api('/auth/logout-all', { method: 'POST', body: {} }));
export const useChangePassword = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { current: string; next: string }) => api('/auth/password', { body: v }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['activity'] }),
  });
};
export const useActivity = () => useQuery({ queryKey: ['activity'], queryFn: () => api<Activity[]>('/auth/activity') });
