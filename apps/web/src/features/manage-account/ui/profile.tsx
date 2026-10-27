import { type FormEvent, useState } from 'react';
import { useTheme, type ThemePref } from '@/app/theme';
import { ACTIVITY_LABEL, useActivity, useAuth, useChangePassword, useLogout, useLogoutAll } from '@/entities/auth';
import { cn } from '@/shared/lib/cn';
import { Button, Card, CardHeader, ConfirmDialog, Field, Icon, ListSkeleton, Notice, PageHeader, TextInput, useToast } from '@/shared/ui';

const THEMES: { key: ThemePref; label: string }[] = [
  { key: 'light', label: '라이트' },
  { key: 'dark', label: '다크' },
  { key: 'system', label: '시스템 설정' },
];

const time = (iso: string) => new Date(iso).toLocaleString('ko-KR', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });

function PasswordCard() {
  const change = useChangePassword();
  const toast = useToast();
  const [cur, setCur] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const mismatch = again !== '' && again !== next;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    change.mutate(
      { current: cur, next },
      {
        onSuccess: () => {
          setCur('');
          setNext('');
          setAgain('');
          toast('비밀번호를 바꿨습니다. 다른 기기는 모두 로그아웃됩니다.');
        },
      },
    );
  };

  return (
    <Card>
      <CardHeader title="비밀번호 변경" />
      <form onSubmit={submit} className="grid max-w-md gap-4 p-5">
        <Field label="현재 비밀번호">{(id) => <TextInput id={id} type="password" value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" required />}</Field>
        <Field label="새 비밀번호" hint="8자 이상">
          {(id) => <TextInput id={id} type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" required minLength={8} />}
        </Field>
        <Field label="새 비밀번호 확인" hint={mismatch ? '새 비밀번호와 다릅니다.' : undefined}>
          {(id) => <TextInput id={id} type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />}
        </Field>
        {change.error && <Notice tone="rec">{(change.error as Error).message}</Notice>}
        <div>
          <Button type="submit" variant="primary" disabled={change.isPending || mismatch || !cur || next.length < 8}>
            저장
          </Button>
        </div>
      </form>
    </Card>
  );
}

function ActivityCard() {
  const { data, isLoading, error } = useActivity();
  return (
    <Card>
      <CardHeader title="최근 활동" />
      {isLoading && <div className="p-5"><ListSkeleton rows={3} /></div>}
      {error && <div className="p-5"><Notice tone="rec">활동 기록을 불러오지 못했습니다.</Notice></div>}
      {data && data.length === 0 && <p className="p-5 text-muted">아직 기록이 없습니다.</p>}
      {data && data.length > 0 && (
        <ul className="divide-y divide-line">
          {data.slice(0, 12).map((a, i) => (
            <li key={i} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3">
              <span className={cn('flex min-w-0 flex-1 items-center gap-2', a.type === 'login-fail' && 'font-semibold text-rec')}>
                {a.type === 'login-fail' && <Icon name="alert" size={16} className="shrink-0" />}
                {ACTIVITY_LABEL[a.type]}
                {a.detail && a.type !== 'login-fail' && <span className="truncate text-xs text-muted">{a.detail}</span>}
              </span>
              <span className="tnum font-mono text-xs text-muted">{a.ip}</span>
              <span className="tnum text-xs text-muted">{time(a.at)}</span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function ProfilePage() {
  const { data } = useAuth();
  const { pref, setPref } = useTheme();
  const logout = useLogout();
  const logoutAll = useLogoutAll();
  const [confirmAll, setConfirmAll] = useState(false);
  const user = data?.user ?? '';

  return (
    <>
      <PageHeader title="프로필" />
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="grid gap-6">
          <Card className="p-5">
            <div className="flex items-center gap-4">
              <span className="inline-flex size-14 items-center justify-center rounded-full bg-brand text-2xl font-semibold uppercase text-brand-ink">{user.slice(0, 1)}</span>
              <div className="min-w-0">
                <p className="truncate text-lg font-semibold">{user}</p>
              </div>
            </div>
            <div className="mt-5 flex flex-wrap gap-2">
              <Button icon="logout" onClick={() => logout.mutate()}>
                로그아웃
              </Button>
              <Button variant="danger" onClick={() => setConfirmAll(true)}>
                모든 기기에서 로그아웃
              </Button>
            </div>
          </Card>

          <Card>
            <CardHeader title="화면 테마" />
            <div role="radiogroup" aria-label="화면 테마" className="grid grid-cols-3 gap-2 p-5">
              {THEMES.map((t) => (
                <button key={t.key} type="button" role="radio" aria-checked={pref === t.key} onClick={() => setPref(t.key)} className={cn('h-10 rounded-control border text-sm font-medium transition-colors', pref === t.key ? 'border-brand bg-tint text-link' : 'border-line text-muted hover:text-ink')}>
                  {t.label}
                </button>
              ))}
            </div>
          </Card>
        </div>

        <div className="grid gap-6">
          <PasswordCard />
          <ActivityCard />
        </div>
      </div>

      <ConfirmDialog open={confirmAll} onClose={() => setConfirmAll(false)} onConfirm={() => logoutAll.mutate()} title="모든 기기에서 로그아웃할까요?" confirmLabel="모두 로그아웃" danger busy={logoutAll.isPending}>
        이 기기를 포함해 로그인된 모든 기기가 로그아웃됩니다. 녹화는 계속됩니다.
      </ConfirmDialog>
    </>
  );
}
