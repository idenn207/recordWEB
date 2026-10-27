import type { ReactNode } from 'react';
import { cn } from '../lib/cn';
import { Icon } from './icon';

/** 인라인 안내. 오류는 문제와 해결 방법을 함께 적는다. */
export function Notice({ tone = 'warn', children }: { tone?: 'warn' | 'rec' | 'neutral'; children: ReactNode }) {
  return (
    <div role={tone === 'neutral' ? 'status' : 'alert'} className={cn('flex items-start gap-2 rounded-control border border-line px-3 py-2.5', tone === 'warn' ? 'bg-warn-bg text-warn' : tone === 'rec' ? 'bg-err-bg text-rec' : 'bg-muted-bg text-muted')}>
      <Icon name="alert" size={17} className="mt-0.5 shrink-0" />
      <div>{children}</div>
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-card border border-dashed border-line px-6 py-10 text-center">
      <p className="font-semibold">{title}</p>
      {children && <div className="mx-auto mt-1 max-w-[68ch] text-muted">{children}</div>}
    </div>
  );
}

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mb-5 flex min-h-10 flex-wrap items-center justify-between gap-x-4 gap-y-2">
      <h1 className="text-2xl font-bold">{title}</h1>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}
