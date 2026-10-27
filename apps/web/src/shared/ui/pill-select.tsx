import { Select } from '@base-ui/react/select';
import { cn } from '../lib/cn';
import { Icon } from './icon';

export interface PillOption<T extends string> {
  value: T;
  label: string;
  /** 오른쪽에 붙는 보조 수치(예: 남은 용량) */
  hint?: string;
  hintClass?: string;
}

/**
 * 알약 모양 선택 상자. 글자 영역(말줄임)과 화살표 자리(40px)를 나눠 서로 침범하지 않는다.
 * 키보드: Enter/Space/방향키로 열기, 방향키 이동, Esc 닫기.
 */
export function PillSelect<T extends string>({ label, value, options, onChange, className, mono, ...rest }: { 'data-ctl'?: boolean; label: string; value: T; options: PillOption<T>[]; onChange: (v: T) => void; className?: string; mono?: boolean }) {
  const cur = options.find((o) => o.value === value);
  return (
    <Select.Root value={value} onValueChange={(v) => v && onChange(v as T)}>
      <Select.Trigger
        aria-label={label}
        {...rest}
        className={cn('inline-flex h-10 min-w-0 items-center rounded-full border border-ink/15 bg-transparent pl-4 text-sm font-semibold text-ink transition-colors hover:bg-muted-bg data-[popup-open]:bg-muted-bg pointer-coarse:min-h-11', className)}
      >
        <span data-pill-text className={cn('min-w-0 flex-1 truncate text-left', mono && 'font-mono')}>
          {cur?.label ?? '선택'}
        </span>
        <Select.Icon className="ml-2 flex w-10 shrink-0 items-center justify-center text-muted">
          <Icon name="chevron" size={16} />
        </Select.Icon>
      </Select.Trigger>
      <Select.Portal>
        <Select.Positioner alignItemWithTrigger={false} side="bottom" align="start" sideOffset={4} className="z-40">
          <Select.Popup className="max-h-80 min-w-(--anchor-width) max-w-[min(32rem,92vw)] overflow-y-auto rounded-card border border-ink/15 bg-surface p-1 shadow-float outline-none">
            {options.map((o) => (
              <Select.Item
                key={o.value}
                value={o.value}
                label={o.label}
                className="flex min-h-10 cursor-pointer items-center justify-between gap-4 rounded-lg px-3 text-sm outline-none data-[highlighted]:bg-muted-bg data-[selected]:text-brand"
              >
                <Select.ItemText className={cn('min-w-0 truncate font-semibold', mono && 'font-mono')}>{o.label}</Select.ItemText>
                {o.hint && <span className={cn('tnum shrink-0 text-[13px] text-muted', o.hintClass)}>{o.hint}</span>}
              </Select.Item>
            ))}
          </Select.Popup>
        </Select.Positioner>
      </Select.Portal>
    </Select.Root>
  );
}
