import { cn } from '../lib/cn';

/** 로딩은 글자 대신 실제 높이의 자리표시로 보인다. 레이아웃이 밀리지 않는다. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn('animate-pulse rounded-control bg-muted-bg', className)} />;
}

export function ListSkeleton({ rows = 3, label = '불러오는 중' }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} className="grid gap-px overflow-hidden rounded-card border border-line bg-line">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-4 bg-surface px-4 py-4">
          <Skeleton className="h-4 w-4" />
          <Skeleton className="h-4 w-40" />
          <Skeleton className="ml-auto h-6 w-20" />
        </div>
      ))}
    </div>
  );
}
