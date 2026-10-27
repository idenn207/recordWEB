import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ChannelThumb, type ChannelWithStatus, PlatformMark, priority, StatusBadge, useChannels, useStartAll, useStopAll } from '@/entities/channel';
import { useDisks } from '@/entities/system';
import { AutoRecordToggle, RecordButton } from '@/features/record-channel';
import { cn } from '@/shared/lib/cn';
import { formatBytes } from '@/shared/lib/format';
import { Button, Card, ConfirmDialog, EmptyState, Icon, PageHeader, Skeleton } from '@/shared/ui';

/**
 * 채널을 어느 상태로 볼지. 오류는 대기 중이어도 오류로 센다.
 * 상태가 늘면 FILTERS 에 한 줄을 더하면 탭, 개수, 목록이 함께 따라온다.
 */
type Kind = 'recording' | 'live' | 'waiting' | 'problem' | 'idle';
const kindOf = (c: ChannelWithStatus): Kind => (c.status.error ? 'problem' : c.status.state === 'recording' ? 'recording' : c.status.meta?.isLive ? 'live' : c.status.state === 'watching' ? 'waiting' : 'idle');

const FILTERS: { key: 'all' | Kind; label: string }[] = [
  { key: 'all', label: '전체' },
  { key: 'recording', label: '녹화 중' },
  { key: 'live', label: '방송 중' },
  { key: 'waiting', label: '녹화 대기' },
  { key: 'problem', label: '오류' },
  { key: 'idle', label: '꺼짐' },
];

/**
 * 갤러리: 테두리 없는 16:9 화면 아래에 이름과 방송 제목, 그 아래에 조작.
 * 모든 채널이 같은 크기다(상태와 이미지 유무와 무관).
 */
function GalleryCard({ channel }: { channel: ChannelWithStatus }) {
  const { meta } = channel.status;
  return (
    <article className="flex h-full flex-col gap-3">
      <div className="relative">
        <ChannelThumb channel={channel} className={cn('rounded-xl', channel.status.error && 'ring-2 ring-rec/60')} />
        <div className="absolute left-3 top-3">
          <StatusBadge channel={channel} overlay />
        </div>
      </div>
      <div className="min-w-0 px-0.5">
        <p className="flex items-center gap-2 text-base font-bold">
          <PlatformMark platform={channel.platform} />
          <span className="truncate">{channel.name}</span>
        </p>
        <p className="mt-0.5 min-h-5 truncate text-sm text-muted" title={meta?.isLive ? meta.liveTitle : undefined}>
          {meta?.isLive ? meta.liveTitle : ''}
        </p>
      </div>
      <div className="mt-auto flex items-center justify-between gap-3 px-0.5">
        <label className="flex items-center gap-2 text-sm text-muted">
          자동 녹화
          <AutoRecordToggle channel={channel} />
        </label>
        <RecordButton channel={channel} small />
      </div>
    </article>
  );
}

/**
 * 리스트: 큰 화면 칸이 있는 행. 정보(이름, 상태, 방송 제목)와 조작(자동 녹화, 버튼)은
 * 넓으면 한 줄에, 좁으면 두 줄에 놓인다. 어느 폭에서든 모든 행의 높이가 같다.
 */
function ChannelRow({ channel, showReason }: { channel: ChannelWithStatus; showReason: boolean }) {
  const { meta, error } = channel.status;
  const sub = showReason && error ? error : meta?.isLive ? meta.liveTitle : '';
  return (
    <li className="flex items-center gap-4 border-b border-line last:border-b-0 max-sm:h-36 sm:h-[7.5rem]">
      <ChannelThumb channel={channel} size="sm" className="w-28 rounded-lg sm:w-44" />
      <div className="flex min-w-0 flex-1 flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          <span className="flex min-w-0 items-center gap-2 text-base font-bold">
            <PlatformMark platform={channel.platform} />
            <span className="truncate">{channel.name}</span>
          </span>
          <span className="flex min-w-0 items-center gap-2">
            <span className="shrink-0">
              <StatusBadge channel={channel} large />
            </span>
            {sub && (
              <span className="truncate text-sm text-muted max-sm:hidden" title={sub}>
                {sub}
              </span>
            )}
          </span>
        </div>
        <div className="flex shrink-0 items-center justify-between gap-3">
          <label className="flex items-center gap-2 whitespace-nowrap text-sm text-muted">
            자동 녹화
            <AutoRecordToggle channel={channel} />
          </label>
          <RecordButton channel={channel} />
        </div>
      </div>
    </li>
  );
}

function DiskText() {
  const d = useDisks().data?.[0];
  return (
    <span className={cn('tnum min-h-5 whitespace-nowrap text-sm', !d && 'invisible', d && d.percent >= 90 ? 'font-semibold text-rec' : d && d.percent >= 75 ? 'font-semibold text-warn' : 'text-muted')}>
      {d ? `디스크 ${formatBytes(d.free)} 남음${d.percent >= 90 ? ' · 거의 가득 참' : d.percent >= 75 ? ' · 여유 부족' : ''}` : '디스크'}
    </span>
  );
}

type View = 'gallery' | 'list';
/** 보기 방식은 이 브라우저에 기억한다. 처음에는 좁은 화면이면 리스트, 넓으면 갤러리. */
function useView(): [View, (v: View) => void] {
  const [view, set] = useState<View>(() => (localStorage.getItem('rw-view') as View) || (matchMedia('(max-width: 767px)').matches ? 'list' : 'gallery'));
  return [view, (v) => (localStorage.setItem('rw-view', v), set(v))];
}

function ViewToggle({ view, onChange }: { view: View; onChange: (v: View) => void }) {
  const items: { key: View; label: string; icon: 'grid' | 'list' }[] = [
    { key: 'gallery', label: '갤러리로 보기', icon: 'grid' },
    { key: 'list', label: '리스트로 보기', icon: 'list' },
  ];
  return (
    <div role="radiogroup" aria-label="보기 방식" className="inline-flex shrink-0 rounded-full border border-ink/15 p-0.5">
      {items.map((i) => (
        <button key={i.key} type="button" role="radio" aria-checked={view === i.key} aria-label={i.label} title={i.label} onClick={() => onChange(i.key)} className={cn('inline-flex size-9 items-center justify-center rounded-full transition-colors', view === i.key ? 'bg-ink text-bg' : 'text-muted hover:text-ink')}>
          <Icon name={i.icon} size={18} />
        </button>
      ))}
    </div>
  );
}

export function ChannelOverview() {
  const { data, isLoading, error } = useChannels();
  const startAll = useStartAll();
  const stopAll = useStopAll();
  const [confirmStop, setConfirmStop] = useState(false);
  const [params, setParams] = useSearchParams();
  const raw = params.get('state');
  const filter = FILTERS.find((f) => f.key === raw)?.key ?? 'all'; // 잘못된 값은 전체로
  const q = (params.get('q') ?? '').trim();
  const [view, setView] = useView();
  const update = (next: { state?: string; q?: string }) => {
    const p = new URLSearchParams(params);
    for (const [k, v] of Object.entries(next)) (v ? p.set(k, v) : p.delete(k));
    setParams(p, { replace: true });
  };

  const all = [...(data ?? [])].sort((a, b) => priority(a) - priority(b) || a.name.localeCompare(b.name, 'ko'));
  const named = q ? all.filter((c) => c.name.toLowerCase().includes(q.toLowerCase())) : all;
  const count = (k: string) => (k === 'all' ? named.length : named.filter((c) => kindOf(c) === k).length);
  const shown = filter === 'all' ? named : named.filter((c) => kindOf(c) === filter);
  const anyActive = all.some((c) => c.status.state !== 'idle');

  return (
    <>
      <PageHeader title="녹화">
        <Button variant="primary" icon="play" onClick={() => startAll.mutate()} disabled={startAll.isPending || !all.some((c) => c.record_enabled)}>
          전체 시작
        </Button>
        <Button icon="stop" variant="danger" onClick={() => setConfirmStop(true)} disabled={!anyActive}>
          전체 중지
        </Button>
      </PageHeader>

      {error && (
        <Card className="mb-6 bg-err-bg p-4" role="alert">
          채널 목록을 불러오지 못했습니다. 서버가 켜져 있는지 확인하세요.
        </Card>
      )}
      {isLoading && (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,17rem),1fr))] gap-6" role="status" aria-label="불러오는 중">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="aspect-video rounded-xl" />
          ))}
        </div>
      )}

      {data && all.length === 0 && (
        <EmptyState title="등록된 채널이 없습니다">
          <Link to="/channels" className="text-link underline underline-offset-2">
            채널
          </Link>
          에서 녹화할 채널을 추가하세요.
        </EmptyState>
      )}

      {data && all.length > 0 && (
        <>
          <div role="tablist" aria-label="상태별 보기" className="-mx-1 mb-5 flex gap-1 overflow-x-auto overflow-y-hidden border-b border-line px-1 [scrollbar-width:none]">
            {FILTERS.map((f) => (
              <button
                key={f.key}
                type="button"
                role="tab"
                aria-selected={filter === f.key}
                onClick={() => update({ state: f.key === 'all' ? '' : f.key })}
                className={cn('tnum -mb-px inline-flex h-11 shrink-0 items-center gap-1.5 border-b-2 px-3 text-base transition-colors', filter === f.key ? 'border-ink font-bold text-ink' : 'border-transparent text-muted hover:text-ink')}
              >
                {f.label}
                <span className={cn('text-sm font-semibold', f.key === 'problem' && count(f.key) > 0 ? 'text-rec' : 'text-muted')}>{count(f.key)}</span>
              </button>
            ))}
          </div>

          <div className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-3">
            <label className="relative block w-full sm:max-w-sm sm:flex-1">
              <span className="sr-only">채널 검색</span>
              <Icon name="search" size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted" />
              <input value={q} onChange={(e) => update({ q: e.target.value })} placeholder="채널 검색" className="h-10 w-full rounded-full border border-ink/15 bg-transparent pl-11 pr-10 text-[15px] text-ink placeholder:text-muted" />
              {q && (
                <button type="button" aria-label="검색어 지우기" onClick={() => update({ q: '' })} className="absolute right-1.5 top-1/2 inline-flex size-8 -translate-y-1/2 items-center justify-center rounded-full text-muted hover:bg-muted-bg hover:text-ink">
                  <Icon name="x" size={16} />
                </button>
              )}
            </label>
            <div className="ml-auto flex items-center gap-4">
              <DiskText />
              <ViewToggle view={view} onChange={setView} />
            </div>
          </div>

          {shown.length === 0 ? (
            <EmptyState title={q ? '검색 결과가 없습니다' : '해당하는 채널이 없습니다'}>
              <button type="button" className="text-link underline underline-offset-2" onClick={() => update({ state: '', q: '' })}>
                전체 보기
              </button>
            </EmptyState>
          ) : view === 'gallery' ? (
            <ul className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,17rem),1fr))] gap-x-6 gap-y-8">
              {shown.map((c) => (
                <li key={c.id} className="min-w-0">
                  <GalleryCard channel={c} />
                </li>
              ))}
            </ul>
          ) : (
            <ul>
              {shown.map((c) => (
                <ChannelRow key={c.id} channel={c} showReason={filter === 'problem'} />
              ))}
            </ul>
          )}
        </>
      )}

      <ConfirmDialog open={confirmStop} onClose={() => setConfirmStop(false)} onConfirm={() => stopAll.mutate(undefined, { onSettled: () => setConfirmStop(false) })} title="모든 녹화를 중지할까요?" confirmLabel="전체 중지" danger busy={stopAll.isPending}>
        녹화 중인 {all.filter((c) => c.status.state === 'recording').length}개는 여기서 끝나고 후처리로 넘어갑니다. 녹화 대기 중인 채널도 취소됩니다.
      </ConfirmDialog>
    </>
  );
}
