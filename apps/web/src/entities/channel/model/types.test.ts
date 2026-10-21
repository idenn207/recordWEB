import { describe, expect, it } from 'vitest';
import { type ChannelWithStatus, priority } from './types';

const ch = (state: 'idle' | 'watching' | 'recording', isLive: boolean): ChannelWithStatus =>
  ({ status: { state, meta: { isLive, liveTitle: '', category: '', thumbnailUrl: null } } }) as ChannelWithStatus;

describe('priority (대시보드 정렬)', () => {
  it('녹화 중 → 방송 중(미녹화) → 예약 → 대기 순', () => {
    const order = [ch('idle', false), ch('watching', false), ch('idle', true), ch('recording', true)].sort((a, b) => priority(a) - priority(b));
    expect(order.map((c) => `${c.status.state}:${c.status.meta?.isLive}`)).toEqual(['recording:true', 'idle:true', 'watching:false', 'idle:false']);
  });

  it('메타가 아직 없어도 상태로 정렬한다', () => {
    const c = { status: { state: 'watching', meta: null } } as ChannelWithStatus;
    expect(priority(c)).toBe(2);
  });
});
