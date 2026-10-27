import { useState } from 'react';
import { cn } from '@/shared/lib/cn';
import type { ChannelWithStatus } from '../model/types';

/**
 * 채널 화면. 방송 중이면 라이브 썸네일, 아니면 채널 프로필 이미지, 그것도 없으면 이름 첫 글자.
 * 어느 경우든 같은 16:9 칸을 채워서 카드 크기가 상태나 이미지 유무로 달라지지 않는다.
 * size="sm" 은 리스트 행의 작은 칸이다.
 */
export function ChannelThumb({ channel, size = 'lg', className }: { channel: ChannelWithStatus; size?: 'lg' | 'sm'; className?: string }) {
  const [liveFailed, setLiveFailed] = useState(false);
  const [avatarFailed, setAvatarFailed] = useState(false);
  const { meta } = channel.status;
  const live = !liveFailed && meta?.isLive ? meta.thumbnailUrl : null;
  const avatar = !avatarFailed ? meta?.avatarUrl : null;
  const round = size === 'lg' ? 'size-20' : 'size-12';
  return (
    <div className={cn('relative aspect-video overflow-hidden bg-muted-bg', size === 'sm' && 'shrink-0', className)}>
      {live ? (
        <img src={live} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setLiveFailed(true)} className="size-full object-cover" />
      ) : (
        <div className="flex size-full items-center justify-center">
          {avatar ? (
            <img src={avatar} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setAvatarFailed(true)} className={cn('rounded-full object-cover', round)} />
          ) : (
            <span aria-hidden="true" className={cn('inline-flex items-center justify-center rounded-full bg-tint font-semibold text-link', round, size === 'lg' ? 'text-3xl' : 'text-xl')}>
              {channel.name.trim().slice(0, 1)}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
