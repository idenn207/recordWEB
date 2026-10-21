import { NavLink, Outlet } from 'react-router-dom';
import { useChannels } from '@/entities/channel';
import { cn } from '@/shared/lib/cn';
import { Icon, type IconName } from '@/shared/ui';

const NAV: { to: string; label: string; short: string; icon: IconName }[] = [
  { to: '/', label: '녹화 현황', short: '현황', icon: 'rec' },
  { to: '/channels', label: '채널 관리', short: '채널', icon: 'channels' },
  { to: '/files', label: '파일 관리', short: '파일', icon: 'files' },
  { to: '/uploads', label: 'YouTube 업로드', short: '업로드', icon: 'upload' },
  { to: '/settings', label: '설정', short: '설정', icon: 'settings' },
];

/** 데스크톱은 왼쪽 고정 내비게이션, 좁은 화면은 위쪽 가로 내비게이션. */
export function AppShell() {
  const channels = useChannels();
  const recording = channels.data?.filter((c) => c.status.state === 'recording').length ?? 0;

  return (
    <div className="flex min-h-full flex-col md:flex-row">
      <aside className="border-b border-line bg-surface md:w-56 md:shrink-0 md:border-b-0 md:border-r">
        <div className="flex items-baseline gap-2 px-4 py-3 md:py-5">
          <span className="text-[1.05rem] font-bold">recordWEB</span>
          <span className="text-[0.8rem] text-muted">녹화 서버</span>
        </div>
        <nav aria-label="주 메뉴" className="grid grid-cols-5 gap-1 px-2 pb-2 md:flex md:flex-col md:pb-4">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === '/'}
              className={({ isActive }) => cn('relative flex flex-col items-center gap-0.5 rounded-lg px-1 py-1.5 text-[0.8rem] font-semibold transition-colors md:flex-row md:gap-2.5 md:px-3 md:py-2 md:text-[0.9rem]', isActive ? 'bg-tint text-link' : 'text-muted hover:bg-muted-bg hover:text-ink')}
            >
              <Icon name={n.icon} />
              <span className="md:hidden">{n.short}</span>
              <span className="hidden md:inline">{n.label}</span>
              {n.to === '/' && recording > 0 && (
                <span className="absolute right-0.5 top-0 inline-flex items-center gap-1 rounded-full border border-line bg-muted-bg px-1.5 text-[0.8rem] text-rec md:static md:ml-auto md:px-2" aria-label={`${recording}개 채널 녹화 중`}>
                  <span className="rec-dot h-1.5 w-1.5 rounded-full bg-current max-md:hidden" />
                  <span className="tnum">{recording}</span>
                </span>
              )}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-5 md:px-8">
        <Outlet />
      </main>
    </div>
  );
}
