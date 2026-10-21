import { useState } from 'react';
import { Link } from 'react-router-dom';
import { type ChannelWithStatus, PlatformMark, priority, StatusBadge, useChannels, useStartAll, useStopAll } from '@/entities/channel';
import { AutoRecordToggle, RecordButton } from '@/features/record-channel';
import { Badge, Button, ConfirmDialog, EmptyState, Icon, Notice, PageHeader } from '@/shared/ui';

function Thumb({ channel }: { channel: ChannelWithStatus }) {
  const [failed, setFailed] = useState(false);
  const url = failed ? null : channel.status.meta?.thumbnailUrl;
  return (
    <div className="aspect-video w-20 shrink-0 overflow-hidden rounded-md border border-line bg-muted-bg sm:w-32">
      {url ? (
        // 라이브 썸네일은 장식이다. 제목이 바로 옆에 텍스트로 있다.
        <img src={url} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} className="h-full w-full object-cover" />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-muted">
          <Icon name={channel.platform === 'youtube' ? 'play' : 'channels'} size={22} />
        </div>
      )}
    </div>
  );
}

function ChannelRow({ channel }: { channel: ChannelWithStatus }) {
  const meta = channel.status.meta;
  const recording = channel.status.state === 'recording';
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-3 border-b border-line px-4 py-3 last:border-b-0 hover:bg-tint">
      <Thumb channel={channel} />
      <div className="min-w-0 flex-1 basis-40">
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
          <PlatformMark platform={channel.platform} />
          <span className="font-bold">{channel.name}</span>
          <StatusBadge channel={channel} />
          {meta?.isLive && !recording && <Badge tone="ok">방송 중</Badge>}
        </div>
        <p className="mt-0.5 truncate text-muted" title={meta?.liveTitle}>
          {meta ? (meta.isLive ? meta.liveTitle : '방송 중이 아닙니다') : '불러오는 중…'}
          {meta?.isLive && meta.category && <span> · {meta.category}</span>}
        </p>
        {recording && channel.status.filename && (
          <p className="mt-0.5 truncate font-mono text-[0.8rem] text-muted" title={channel.status.filename}>
            {channel.status.filename}
          </p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-3 max-sm:w-full max-sm:justify-between">
        <label className="flex items-center gap-2 text-[0.8rem] font-semibold text-muted">
          자동 녹화
          <AutoRecordToggle channel={channel} />
        </label>
        <RecordButton channel={channel} />
      </div>
    </li>
  );
}

export function ChannelOverview({ status }: { status?: React.ReactNode }) {
  const { data, isLoading, error } = useChannels();
  const startAll = useStartAll();
  const stopAll = useStopAll();
  const [confirmStop, setConfirmStop] = useState(false);

  const channels = [...(data ?? [])].sort((a, b) => priority(a) - priority(b) || a.name.localeCompare(b.name, 'ko'));
  const count = (s: ChannelWithStatus['status']['state']) => channels.filter((c) => c.status.state === s).length;
  const anyActive = channels.some((c) => c.status.state !== 'idle');

  return (
    <>
      <PageHeader title="녹화 현황">
        <span className="tnum mr-2 w-full text-muted sm:w-auto" aria-live="polite">
          녹화 중 {count('recording')} · 예약 {count('watching')} · 대기 {count('idle')}
        </span>
        <Button icon="play" onClick={() => startAll.mutate()} disabled={startAll.isPending || !channels.some((c) => c.record_enabled)} title="자동 녹화가 켜진 채널의 감시를 시작합니다">
          전체 시작
        </Button>
        <Button icon="stop" variant="danger" onClick={() => setConfirmStop(true)} disabled={!anyActive}>
          전체 중지
        </Button>
      </PageHeader>

      {status}
      {error && <Notice tone="rec">채널 목록을 불러오지 못했습니다. 서버가 켜져 있는지 확인하세요. ({(error as Error).message})</Notice>}
      {isLoading && <p className="text-muted">불러오는 중…</p>}
      {!isLoading && !error && channels.length === 0 && (
        <EmptyState title="등록된 채널이 없습니다">
          <Link to="/channels" className="text-link underline underline-offset-2">
            채널 관리
          </Link>
          에서 녹화할 채널을 추가하세요.
        </EmptyState>
      )}
      {channels.length > 0 && <ul className="overflow-hidden rounded-[14px] border border-line bg-card shadow-card">{channels.map((c) => <ChannelRow key={c.id} channel={c} />)}</ul>}

      <ConfirmDialog
        open={confirmStop}
        onClose={() => setConfirmStop(false)}
        onConfirm={() => stopAll.mutate(undefined, { onSettled: () => setConfirmStop(false) })}
        title="모든 녹화를 중지할까요?"
        confirmLabel="전체 중지"
        danger
        busy={stopAll.isPending}
      >
        녹화 중인 {count('recording')}개 채널의 녹화가 끝나고 후처리가 시작됩니다. 예약 중인 채널의 감시도 멈춥니다.
      </ConfirmDialog>
    </>
  );
}
