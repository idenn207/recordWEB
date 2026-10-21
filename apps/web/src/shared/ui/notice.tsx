import type { ReactNode } from 'react';
import { cn } from '../lib/cn';
import { Icon } from './icon';

/** 인라인 안내. 오류는 문제와 해결 방법을 함께 적는다. */
export function Notice({ tone = 'warn', children }: { tone?: 'warn' | 'rec' | 'neutral'; children: ReactNode }) {
  return (
    <div role={tone === 'neutral' ? 'status' : 'alert'} className={cn('flex items-start gap-2 rounded-lg border border-line px-3 py-2.5', tone === 'warn' ? 'bg-warn-bg text-warn' : tone === 'rec' ? 'bg-muted-bg text-rec' : 'bg-muted-bg text-muted')}>
      <Icon name="alert" size={17} className="mt-0.5 shrink-0" />
      <div>{children}</div>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-[14px] border border-dashed border-line px-6 py-10 text-center">
      <p className="font-bold">{title}</p>
      {children && <div className="mt-1 text-muted">{children}</div>}
    </div>
  );
}

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mb-4 flex min-h-10 flex-wrap items-center justify-between gap-3">
      <h1 className="text-[1.05rem] font-bold">{title}</h1>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}
