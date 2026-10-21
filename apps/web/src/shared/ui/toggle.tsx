import { Switch } from '@headlessui/react';
import { cn } from '../lib/cn';

/** 라벨은 접근성 이름으로만 쓰고, 보이는 문구는 호출하는 쪽에서 둔다. */
export function Toggle({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <Switch
      checked={checked}
      onChange={onChange}
      disabled={disabled}
      aria-label={label}
      className={cn('relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border border-line transition-colors duration-150 disabled:opacity-50', checked ? 'border-transparent bg-toggle-on' : 'bg-muted-bg')}
    >
      <span className={cn('inline-block h-[18px] w-[18px] rounded-full transition-transform duration-150', checked ? 'translate-x-[22px] bg-toggle-thumb' : 'translate-x-[3px] bg-muted')} />
    </Switch>
  );
}
