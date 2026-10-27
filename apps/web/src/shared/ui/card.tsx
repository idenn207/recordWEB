import type { ComponentProps, ReactNode } from 'react';
import { cn } from '../lib/cn';

/** 한 덩어리의 내용을 담는 면. 카드 안에 카드를 넣지 않는다. */
export function Card({ className, ...p }: ComponentProps<'section'>) {
  return <section className={cn('rounded-card bg-surface shadow-card', className)} {...p} />;
}

export function CardHeader({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-line px-5 py-4">
      <h2 className="text-base font-semibold">{title}</h2>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}
