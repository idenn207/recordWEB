import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react';
import { useId } from 'react';
import { cn } from '../lib/cn';
import { Toggle } from './toggle';

const CONTROL = 'w-full rounded-lg border border-line bg-card px-2.5 py-2 text-[0.9rem] text-ink placeholder:text-muted/70 disabled:opacity-50';

/** 라벨 + 컨트롤 + 보조 설명. 컨트롤에는 id가 자동 연결된다. */
export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-[0.8rem] font-semibold tracking-[0.02em] text-muted">
        {label}
      </label>
      {children(id)}
      {hint && <p className="text-[0.8rem] text-muted">{hint}</p>}
    </div>
  );
}

export function TextInput({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(CONTROL, className)} {...p} />;
}

export function Select({ className, children, ...p }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cn(CONTROL, className)} {...p}>
      {children}
    </select>
  );
}

export function TextArea({ className, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(CONTROL, 'min-h-20 font-mono text-[0.85rem]', className)} {...p} />;
}

/** 설정 한 줄: 왼쪽에 이름과 설명, 오른쪽에 토글. */
export function ToggleRow({ label, hint, checked, onChange, disabled }: { label: string; hint?: ReactNode; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div>
        <div className="font-semibold">{label}</div>
        {hint && <p className="text-[0.8rem] text-muted">{hint}</p>}
      </div>
      <Toggle checked={checked} onChange={onChange} label={label} disabled={disabled} />
    </div>
  );
}
