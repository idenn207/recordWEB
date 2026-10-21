import { useDisks, useMetrics } from '@/entities/system';
import { cn } from '@/shared/lib/cn';
import { formatBytes } from '@/shared/lib/format';

function Meter({ label, percent, detail }: { label: string; percent: number; detail?: string }) {
  const level = percent >= 90 ? 'bg-rec' : percent >= 80 ? 'bg-warn' : 'bg-muted';
  return (
    <div className="min-w-36 flex-1">
      <div className="flex items-baseline justify-between gap-2 text-[0.8rem]">
        <span className="truncate font-semibold text-muted" title={label}>
          {label}
        </span>
        <span className="tnum whitespace-nowrap">
          {percent}%{detail && <span className="text-muted"> · {detail}</span>}
        </span>
      </div>
      <div role="meter" aria-label={label} aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} className="mt-1 h-1 overflow-hidden rounded-full bg-muted-bg">
        <div className={cn('h-full rounded-full transition-[width] duration-500', level)} style={{ width: `${Math.min(100, percent)}%` }} />
      </div>
    </div>
  );
}

/** 한 줄로 훑는 서버 상태. CPU, 메모리, 녹화 폴더가 있는 볼륨별 사용량. */
export function SystemStatus() {
  const m = useMetrics();
  const disks = useDisks();
  return (
    <section aria-label="서버 상태" className="mb-4 flex flex-wrap gap-x-6 gap-y-3 rounded-[14px] border border-line bg-card px-4 py-3 shadow-card">
      <Meter label="CPU" percent={m.data?.cpu.percent ?? 0} />
      <Meter label="메모리" percent={m.data?.memory.percent ?? 0} detail={m.data ? formatBytes(m.data.memory.used) : undefined} />
      {disks.data?.map((d) => (
        <Meter key={d.path} label={`디스크 ${d.path.split(/[\\/]/).filter(Boolean).pop() ?? d.path}`} percent={d.percent} detail={`${formatBytes(d.free)} 남음`} />
      ))}
    </section>
  );
}
