import { useState } from 'react';
import { type ChannelWithStatus, useStartChannel, useStopChannel, useToggleChannel } from '@/entities/channel';
import { Button, Toggle } from '@/shared/ui';

/** 시작/중지. 토글이 꺼져 있어도 "시작"은 이번 방송 1회만 녹화한다. */
export function RecordButton({ channel, small }: { channel: ChannelWithStatus; small?: boolean }) {
  const start = useStartChannel();
  const stop = useStopChannel();
  const [error, setError] = useState('');
  const active = channel.status.state !== 'idle';
  const recording = channel.status.state === 'recording';
  const busy = start.isPending || stop.isPending;
  const run = (fn: typeof start | typeof stop) => fn.mutate(channel.id, { onError: (e) => setError(e.message), onSuccess: () => setError('') });

  return (
    <>
      {active ? (
        <Button small={small} variant="danger" icon="stop" disabled={busy} onClick={() => run(stop)} aria-label={`${channel.name} ${recording ? '녹화 중지' : '대기 취소'}`}>
          {recording ? '녹화 중지' : '대기 취소'}
        </Button>
      ) : (
        <Button small={small} variant="primary" icon="play" disabled={busy} onClick={() => run(start)} aria-label={`${channel.name} 녹화 시작`}>
          녹화 시작
        </Button>
      )}
      {error && (
        <span role="alert" className="text-xs text-rec">
          {error}
        </span>
      )}
    </>
  );
}

/** 자동 녹화: 켜 두면 방송이 시작될 때마다 알아서 녹화한다. */
export function AutoRecordToggle({ channel }: { channel: ChannelWithStatus }) {
  const toggle = useToggleChannel();
  return <Toggle checked={channel.record_enabled} onChange={() => toggle.mutate(channel.id)} disabled={toggle.isPending} label={`${channel.name} 자동 녹화`} />;
}
