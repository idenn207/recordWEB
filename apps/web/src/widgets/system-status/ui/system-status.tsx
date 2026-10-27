import { useDisks, useMetrics } from '@/entities/system';
import { cn } from '@/shared/lib/cn';
import { formatBytes } from '@/shared/lib/format';

/** 서버 상태 한 줄. 디스크는 75%부터 노랑, 90%부터 빨강으로 글자와 함께 알린다 (PATTERNS 6절). */
export function SystemStatus() {
  const m = useMetrics();
  const disks = useDisks();
  if (!m.data && !disks.data?.length) return null; // 계산하지 못한 값을 0%로 보이지 않는다
  return (
    <p aria-label="서버 상태" className="tnum mb-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
      {m.data && <span>CPU {m.data.cpu.percent}%</span>}
      {m.data && <span>메모리 {m.data.memory.percent}%</span>}
      {disks.data?.map((d) => (
        <span key={d.path} className={cn(d.percent >= 90 ? 'font-semibold text-rec' : d.percent >= 75 && 'font-semibold text-warn')}>
          디스크 {d.path.split(/[\/]/).filter(Boolean).pop() ?? d.path} {formatBytes(d.free)} 남음{d.percent >= 75 && ` (${d.percent >= 90 ? '거의 가득 참' : '여유 부족'})`}
        </span>
      ))}
    </p>
  );
}
