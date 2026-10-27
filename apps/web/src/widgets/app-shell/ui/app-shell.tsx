import { Menu } from '@base-ui/react/menu';
import { Popover } from '@base-ui/react/popover';
import { useState } from 'react';
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { type ThemePref, useTheme } from '@/app/theme';
import { useAuth, useLogout } from '@/entities/auth';
import { type ChannelWithStatus, priority, useChannels } from '@/entities/channel';
import { cn } from '@/shared/lib/cn';
import { Icon, type IconName } from '@/shared/ui';

const NAV: { to: string; label: string; icon: IconName }[] = [
  { to: '/', label: '녹화', icon: 'rec' },
  { to: '/channels', label: '채널', icon: 'channels' },
  { to: '/files', label: '파일', icon: 'files' },
  { to: '/uploads', label: '업로드', icon: 'upload' },
  { to: '/settings', label: '설정', icon: 'settings' },
];

const THEMES: { key: ThemePref; label: string; icon: IconName }[] = [
  { key: 'light', label: '라이트', icon: 'sun' },
  { key: 'dark', label: '다크', icon: 'moon' },
  { key: 'system', label: '시스템 설정', icon: 'channels' },
];

const ICON_BTN = 'relative inline-flex size-10 items-center justify-center rounded-full text-muted outline-none transition-colors hover:bg-muted-bg hover:text-ink focus-visible:ring-2 focus-visible:ring-brand aria-expanded:bg-muted-bg aria-expanded:text-ink';
const POPUP = 'rounded-card border border-line bg-surface p-1.5 text-ink shadow-float outline-none';
const ITEM = 'flex w-full cursor-pointer items-center gap-2.5 rounded-control px-3 py-2 text-left outline-none data-[highlighted]:bg-muted-bg';

type Problem = { key: string; platform: string; names: string[]; text: string };

/** 같은 원인은 한 줄로 묶는다. */
function problemsOf(list: ChannelWithStatus[]): Problem[] {
  const map = new Map<string, Problem>();
  for (const c of list) {
    if (!c.status.error) continue;
    const key = `${c.platform}|${c.status.error}`;
    const p = map.get(key) ?? { key, platform: c.platform, names: [], text: c.status.error };
    p.names.push(c.name);
    map.set(key, p);
  }
  return [...map.values()];
}

/**
 * 감시를 막는 문제를 알리는 줄. 화면 위에 떠 있어서(fixed) 폴링으로 오류가 생겨도 아래 내용이 밀리지 않는다.
 * 닫으면 같은 문제가 계속되는 동안 다시 뜨지 않고, 문제가 바뀌면 다시 뜬다.
 */
function ProblemAlert({ problems }: { problems: Problem[] }) {
  const sig = problems.map((p) => p.key).join('|');
  const [closed, setClosed] = useState(() => sessionStorage.getItem('rw-alert-closed'));
  if (!problems.length || closed === sig) return null;
  return (
    <div className="pointer-events-none fixed bottom-[calc(3.5rem+env(safe-area-inset-bottom)+0.75rem)] right-0 z-40 w-full px-4 md:bottom-6 md:right-6 md:w-[26rem] md:px-0">
      <div role="alert" className="pointer-events-auto flex flex-wrap items-center gap-x-3 gap-y-2 rounded-card border border-rec/50 bg-surface py-2.5 pl-4 pr-2 shadow-float">
        <Icon name="alert" className="shrink-0 text-rec" />
        <p className="min-w-0 flex-1">
          <span className="font-semibold">{problems.map((p) => p.names.join(', ')).join(' · ')}</span>
          <span className="mt-0.5 line-clamp-1 text-muted md:line-clamp-2">{problems[0].text}</span>
        </p>
        {problems.some((p) => p.platform === 'x') && (
          <Link to="/settings#x" reloadDocument className="inline-flex h-9 shrink-0 items-center rounded-control bg-brand px-4 font-semibold text-brand-ink hover:bg-brand-hover">
            쿠키 다시 등록
          </Link>
        )}
        <button
          type="button"
          aria-label="알림 닫기"
          onClick={() => {
            sessionStorage.setItem('rw-alert-closed', sig);
            setClosed(sig);
          }}
          className="inline-flex size-9 shrink-0 items-center justify-center rounded-control text-muted hover:bg-muted-bg hover:text-ink"
        >
          <Icon name="x" size={16} />
        </button>
      </div>
    </div>
  );
}

function Bell({ problems }: { problems: Problem[] }) {
  return (
    <Popover.Root>
      <Popover.Trigger className={ICON_BTN} aria-label={problems.length ? `알림 ${problems.length}건` : '알림 없음'}>
        <Icon name="bell" />
        {problems.length > 0 && <span className="absolute right-1.5 top-1.5 size-2 rounded-full bg-rec ring-2 ring-bg" aria-hidden="true" />}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner side="bottom" align="end" sideOffset={8} className="z-50">
          <Popover.Popup className={cn(POPUP, 'w-[min(22rem,calc(100vw-2rem))] p-0')}>
            <Popover.Title className="border-b border-line px-4 py-3 text-sm font-semibold">알림</Popover.Title>
            {problems.length === 0 ? (
              <p className="px-4 py-6 text-center text-muted">새 알림이 없습니다.</p>
            ) : (
              <ul className="max-h-80 divide-y divide-line overflow-auto">
                {problems.map((p) => (
                  <li key={p.key} className="px-4 py-3">
                    <p className="flex items-center gap-2 font-semibold">
                      <Icon name="alert" size={16} className="shrink-0 text-rec" />
                      {p.names.join(', ')}
                    </p>
                    <p className="mt-1 text-muted">{p.text}</p>
                    {p.platform === 'x' && (
                      <Link to="/settings#x" reloadDocument className="mt-2 inline-block font-semibold text-link hover:underline">
                        쿠키 다시 등록
                      </Link>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}

function ThemeMenu() {
  const { pref, setPref } = useTheme();
  const cur = THEMES.find((t) => t.key === pref)!;
  return (
    <Menu.Root>
      <Menu.Trigger className={ICON_BTN} aria-label={`화면 테마: ${cur.label}`}>
        <Icon name={pref === 'system' ? 'channels' : cur.icon} />
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner side="bottom" align="end" sideOffset={8} className="z-50">
          <Menu.Popup className={cn(POPUP, 'min-w-44')}>
            {THEMES.map((t) => (
              <Menu.Item key={t.key} onClick={() => setPref(t.key)} className={ITEM}>
                <Icon name={t.icon} size={16} />
                <span className="flex-1">{t.label}</span>
                {pref === t.key && <Icon name="check" size={16} className="text-brand" />}
              </Menu.Item>
            ))}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}

function ProfileMenu({ user }: { user: string }) {
  const logout = useLogout();
  const navigate = useNavigate();
  return (
    <Menu.Root>
      <Menu.Trigger className="inline-flex h-10 items-center gap-2 rounded-full pl-1 pr-3 text-ink outline-none transition-colors hover:bg-muted-bg focus-visible:ring-2 focus-visible:ring-brand aria-expanded:bg-muted-bg" aria-label="내 계정">
        <span className="inline-flex size-7 items-center justify-center rounded-full bg-brand text-xs font-semibold uppercase text-brand-ink">{user.slice(0, 1)}</span>
        <span className="max-w-24 truncate text-sm font-medium max-sm:hidden">{user}</span>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner side="bottom" align="end" sideOffset={8} className="z-50">
          <Menu.Popup className={cn(POPUP, 'min-w-48')}>
            <p className="px-3 pb-2 pt-1.5 text-xs text-muted">
              로그인 계정<span className="mt-0.5 block text-sm font-semibold text-ink">{user}</span>
            </p>
            <Menu.Item onClick={() => navigate('/profile')} className={ITEM}>
              <Icon name="user" size={16} />
              프로필
            </Menu.Item>
            <Menu.Item onClick={() => logout.mutate()} className={cn(ITEM, 'text-rec')}>
              <Icon name="logout" size={16} />
              로그아웃
            </Menu.Item>
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}

/** 채널 프로필 이미지(없으면 이름 첫 글자). 사이드바의 작은 원. */
function Avatar({ channel }: { channel: ChannelWithStatus }) {
  const [failed, setFailed] = useState(false);
  const url = !failed ? channel.status.meta?.avatarUrl : null;
  return url ? (
    <img src={url} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} className="size-8 shrink-0 rounded-full object-cover" />
  ) : (
    <span aria-hidden="true" className="inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-tint text-sm font-semibold text-link">
      {channel.name.trim().slice(0, 1)}
    </span>
  );
}

const NAV_ITEM = 'flex items-center rounded-lg font-semibold transition-colors md:flex-col md:gap-1 md:py-2 md:text-xs lg:flex-row lg:gap-3 lg:px-3 lg:py-2 lg:text-[15px]';

/**
 * 왼쪽 메뉴. 넓은 화면은 메뉴 이름과 "내 채널" 목록, 중간 폭은 아이콘 위주의 좁은 줄(치지직과 같은 구조).
 * 채널을 누르면 녹화 화면이 그 채널 이름으로 걸러진다.
 */
function Sidebar({ channels, recording }: { channels: ChannelWithStatus[]; recording: number }) {
  const navigate = useNavigate();
  const [all, setAll] = useState(false);
  const sorted = [...channels].sort((a, b) => priority(a) - priority(b) || a.name.localeCompare(b.name, 'ko'));
  const shown = all ? sorted : sorted.slice(0, 8);
  return (
    <aside className="fixed bottom-0 left-0 top-14 z-20 hidden w-[4.5rem] flex-col overflow-y-auto px-2 pb-6 pt-3 md:flex lg:w-60 lg:px-4">
      <nav aria-label="주 메뉴" className="grid gap-1">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === '/'} className={({ isActive }) => cn(NAV_ITEM, isActive ? 'text-link' : 'text-ink hover:bg-muted-bg')}>
            <span className="relative">
              <Icon name={n.icon} size={22} />
              {n.to === '/' && recording > 0 && <span className="absolute -right-1 -top-1 size-2 rounded-full bg-rec ring-2 ring-bg lg:hidden" aria-hidden="true" />}
            </span>
            {n.label}
            {n.to === '/' && recording > 0 && <span className="tnum ml-auto hidden rounded-full bg-rec px-2 text-xs font-semibold leading-5 text-bg lg:inline">{recording}</span>}
          </NavLink>
        ))}
      </nav>
      {sorted.length > 0 && (
        <section aria-label="내 채널" className="mt-5 hidden border-t border-line pt-4 lg:block">
          <h2 className="px-3 pb-2 text-[13px] font-semibold text-muted">내 채널</h2>
          <ul className="grid gap-0.5">
            {shown.map((c) => (
              <li key={c.id}>
                <button type="button" onClick={() => navigate(`/?q=${encodeURIComponent(c.name)}`)} className="flex h-12 w-full items-center gap-3 rounded-lg px-3 text-left transition-colors hover:bg-muted-bg">
                  <Avatar channel={c} />
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">{c.name}</span>
                  {c.status.state === 'recording' ? (
                    <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-rec">
                      <span className="rec-dot size-1.5 rounded-full bg-current" aria-hidden="true" />녹화 중
                    </span>
                  ) : c.status.error ? (
                    <span className="text-xs font-semibold text-rec">오류</span>
                  ) : null}
                </button>
              </li>
            ))}
          </ul>
          {sorted.length > 8 && (
            <button type="button" onClick={() => setAll((v) => !v)} className="mx-auto mt-3 flex h-8 items-center rounded-full border border-ink/15 px-4 text-[13px] font-semibold text-ink hover:bg-muted-bg">
              {all ? '접기' : `더보기 (${sorted.length - 8})`}
            </button>
          )}
        </section>
      )}
    </aside>
  );
}

/**
 * 치지직과 같은 구조: 페이지와 같은 바탕의 상단바(로고, 알림, 테마, 계정), 왼쪽 메뉴, 오른쪽 본문.
 * 모바일은 아래 탭바. 본문은 사이드바를 뺀 영역에서 최대 폭 안에 놓인다.
 */
export function AppShell() {
  const auth = useAuth();
  const channels = useChannels();
  const list = channels.data ?? [];
  const problems = problemsOf(list);
  const recording = list.filter((c) => c.status.state === 'recording').length;
  const user = auth.data?.user ?? '';

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-30 h-14 border-b border-line bg-bg">
        <div className="flex h-full items-center gap-2 px-4 sm:px-6">
          <Link to="/" className="mr-2 flex items-center gap-2 text-lg font-bold tracking-tight" aria-label="recordWEB 녹화">
            <span className="inline-flex size-8 items-center justify-center rounded-full bg-brand text-brand-ink">
              <Icon name="rec" size={18} />
            </span>
            recordWEB
          </Link>
          <div className="ml-auto flex items-center gap-1">
            <Bell problems={problems} />
            <ThemeMenu />
            {user && <ProfileMenu user={user} />}
          </div>
        </div>
      </header>

      <Sidebar channels={list} recording={recording} />

      <main className="px-4 pb-24 pt-6 sm:px-6 md:pb-12 md:pl-[calc(4.5rem+1.5rem)] lg:pl-[calc(15rem+2rem)] lg:pr-8">
        <div className="mx-auto w-full max-w-[1600px]">
          <Outlet />
        </div>
      </main>
      <ProblemAlert problems={problems} />

      <nav aria-label="주 메뉴" className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-5 border-t border-line bg-bg pb-[env(safe-area-inset-bottom)] md:hidden">
        {NAV.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.to === '/'} className={({ isActive }) => cn('relative flex min-h-14 flex-col items-center justify-center gap-1 text-xs font-semibold', isActive ? 'text-link' : 'text-muted')}>
            <Icon name={n.icon} />
            {n.label}
            {n.to === '/' && recording > 0 && <span className="rec-dot absolute right-[28%] top-2 size-2 rounded-full bg-rec" role="img" aria-label={`${recording}개 녹화 중`} />}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
