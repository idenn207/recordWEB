import { useEffect, useState } from 'react';
import { formatElapsed } from '@/shared/lib/format';

/** 서버 폴링 주기(수 초)와 무관하게 녹화 경과 시간을 1초 단위로 흘려 보낸다. */
export function useElapsed(startedAt: number | null): string {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!startedAt) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [startedAt]);
  return startedAt ? formatElapsed((now - startedAt) / 1000) : '';
}
