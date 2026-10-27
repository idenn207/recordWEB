import { Switch } from '@base-ui/react/switch';
import { cn } from '../lib/cn';

/** 라벨은 접근성 이름으로만 쓰고, 보이는 문구는 호출하는 쪽에서 둔다. 켜는 즉시 반영되는 설정에만 쓴다. */
export function Toggle({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <Switch.Root
      checked={checked}
      onCheckedChange={onChange}
      disabled={disabled}
      aria-label={label}
      className={cn('relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border border-line bg-muted-bg transition-colors duration-150 data-[checked]:border-transparent data-[checked]:bg-brand disabled:opacity-50')}
    >
      <Switch.Thumb className="size-[18px] translate-x-[3px] rounded-full bg-muted transition-transform duration-150 data-[checked]:translate-x-[22px] data-[checked]:bg-brand-ink" />
    </Switch.Root>
  );
}
