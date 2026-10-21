import { Badge } from '@/shared/ui';
import { useElapsed } from '../lib/use-elapsed';
import type { ChannelWithStatus, Platform } from '../model/types';

/** 상태는 색 + 문구(+ 녹화 중 깜빡이는 점)로 전달한다. */
export function StatusBadge({ channel }: { channel: ChannelWithStatus }) {
  const elapsed = useElapsed(channel.status.state === 'recording' ? channel.status.startedAt : null);
  if (channel.status.state === 'recording') {
    return (
      <Badge tone="rec" pulse>
        녹화 중 <span className="tnum">{elapsed}</span>
      </Badge>
    );
  }
  if (channel.status.state === 'watching') return <Badge tone="warn">예약 녹화 중</Badge>;
  return <Badge>대기 중</Badge>;
}

export function PlatformMark({ platform, showName = false }: { platform: Platform; showName?: boolean }) {
  const name = platform === 'chzzk' ? '치지직' : '유튜브';
  return (
    <span className="inline-flex items-center gap-1.5">
      <img src={`/img/${platform}_icon.png`} alt={showName ? '' : name} title={name} width={16} height={16} className="h-4 w-4 rounded-[4px]" />
      {showName && <span>{name}</span>}
    </span>
  );
}
