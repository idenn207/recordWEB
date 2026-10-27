import { useQueryClient } from '@tanstack/react-query';
import { type FormEvent, type ReactNode, useEffect, useState } from 'react';
import { useAuth, useLogin, useSetup } from '@/entities/auth';
import { Button, Field, Icon, Notice, TextInput } from '@/shared/ui';

function AuthScreen({ setup }: { setup: boolean }) {
  const login = useLogin();
  const create = useSetup();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const m = setup ? create : login;
  const mismatch = setup && confirm !== '' && confirm !== password;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (!mismatch) m.mutate({ username: username.trim(), password });
  };

  return (
    <div className="flex min-h-full items-center justify-center bg-chrome px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2 text-lg font-semibold text-chrome-ink">
          <span className="inline-flex size-8 items-center justify-center rounded-control bg-brand text-brand-ink">
            <Icon name="rec" size={18} />
          </span>
          recordWEB
        </div>
        <form onSubmit={submit} className="grid gap-4 rounded-card border border-white/10 bg-surface p-6 text-ink shadow-float">
          <div>
            <h1 className="text-xl font-semibold">{setup ? '계정 만들기' : '로그인'}</h1>
          </div>
          <Field label="아이디">{(id) => <TextInput id={id} value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoFocus required />}</Field>
          <Field label="비밀번호" hint={setup ? '8자 이상' : undefined}>
            {(id) => <TextInput id={id} type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete={setup ? 'new-password' : 'current-password'} required minLength={setup ? 8 : undefined} />}
          </Field>
          {setup && (
            <Field label="비밀번호 확인" hint={mismatch ? '비밀번호가 서로 다릅니다.' : undefined}>
              {(id) => <TextInput id={id} type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required />}
            </Field>
          )}
          {m.error && <Notice tone="rec">{(m.error as Error).message}</Notice>}
          <Button type="submit" variant="primary" disabled={m.isPending || mismatch || !username || !password} className="h-10 justify-center">
            {m.isPending ? '확인하는 중…' : setup ? '계정 만들고 시작' : '로그인'}
          </Button>
        </form>
      </div>
    </div>
  );
}

/** 로그인하지 않았으면 로그인(또는 첫 계정 생성) 화면을, 했으면 자식을 보인다. 세션이 끝나면(401) 다시 로그인으로 돌아온다. */
export function AuthGate({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { data, isLoading, error, refetch } = useAuth();

  useEffect(() => {
    const on = () => void qc.invalidateQueries({ queryKey: ['auth'] });
    window.addEventListener('rw:unauthorized', on);
    return () => window.removeEventListener('rw:unauthorized', on);
  }, [qc]);

  if (isLoading) return <div role="status" aria-label="불러오는 중" className="min-h-full bg-chrome" />;
  if (error || !data)
    return (
      <div className="flex min-h-full items-center justify-center bg-chrome px-4">
        <div className="grid max-w-sm gap-3 rounded-card border border-white/10 bg-surface p-6 text-ink">
          <p className="font-semibold">서버에 연결하지 못했습니다.</p>
          <p className="text-muted">서버가 켜져 있는지 확인한 뒤 다시 시도하세요.</p>
          <Button onClick={() => void refetch()}>다시 시도</Button>
        </div>
      </div>
    );
  if (data.setup) return <AuthScreen setup />;
  if (!data.user) return <AuthScreen setup={false} />;
  return <>{children}</>;
}
