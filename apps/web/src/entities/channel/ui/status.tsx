import { Badge, Icon } from '@/shared/ui';
import { useElapsed } from '../lib/use-elapsed';
import { type ChannelWithStatus, PLATFORM_NAME, type Platform } from '../model/types';

/** 상태는 색 + 문구(+ 녹화 중 깜빡이는 점)로 전달한다. */
export function StatusBadge({ channel, overlay, large }: { channel: ChannelWithStatus; overlay?: boolean; large?: boolean }) {
  const elapsed = useElapsed(channel.status.state === 'recording' ? channel.status.startedAt : null);
  if (channel.status.state === 'recording') {
    return (
      <Badge tone="rec" pulse solid={overlay} large={large}>
        녹화 중 <span className="tnum">{elapsed}</span>
      </Badge>
    );
  }
  if (channel.status.meta?.isLive && !channel.status.error) return <Badge tone="ok" solid={overlay} large={large}>방송 중</Badge>; // 방송은 하지만 녹화는 하지 않는 채널
  // 감시를 막는 문제가 있으면 "예약 녹화 중"처럼 정상으로 보이지 않게 한다
  if (channel.status.state === 'watching') return <Badge tone={channel.status.error ? 'rec' : 'warn'} solid={overlay} large={large}>{channel.status.error ? '오류' : '녹화 대기'}</Badge>;
  return <Badge solid={overlay} large={large}>꺼짐</Badge>;
}

export function PlatformMark({ platform, showName = false }: { platform: Platform; showName?: boolean }) {
  const name = PLATFORM_NAME[platform];
  if (platform === 'x') {
    // X는 별도 이미지 없이 검은 타일 위에 X를 그린다 (다른 플랫폼 아이콘과 같은 크기)
    return (
      <span className="inline-flex items-center gap-1.5" title={name}>
        <span className="inline-flex h-4 w-4 items-center justify-center rounded-[4px] bg-ink text-bg">
          <Icon name="x" size={11} />
        </span>
        {showName ? <span>{name}</span> : <span className="sr-only">{name}</span>}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5">
      <img src={`/img/${platform}_icon.png`} alt={showName ? '' : name} title={name} width={16} height={16} className="h-4 w-4 rounded-[4px]" />
      {showName && <span>{name}</span>}
    </span>
  );
}
