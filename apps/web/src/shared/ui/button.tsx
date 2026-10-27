import type { ButtonHTMLAttributes } from 'react';
import { cn } from '../lib/cn';
import { Icon, type IconName } from './icon';

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';

const VARIANTS: Record<Variant, string> = {
  primary: 'border-transparent bg-brand font-semibold text-brand-ink hover:bg-brand-hover disabled:bg-muted-bg disabled:text-muted disabled:opacity-100',
  secondary: 'border-ink/15 bg-transparent font-semibold text-ink hover:bg-muted-bg',
  danger: 'border-rec/40 bg-transparent font-semibold text-rec hover:bg-err-bg',
  ghost: 'border-transparent bg-transparent font-semibold text-muted hover:bg-muted-bg hover:text-ink',
};

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  icon?: IconName;
  small?: boolean;
}

export function Button({ variant = 'secondary', icon, small, className, children, type = 'button', ...rest }: Props) {
  return (
    <button
      type={type}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-full border transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50',
        small ? 'h-8 px-3 text-[13px]' : 'h-9 px-4 text-sm pointer-coarse:min-h-11',
        VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {icon && <Icon name={icon} size={small ? 15 : 17} />}
      {children}
    </button>
  );
}

/** 라벨 없이 아이콘만 쓰는 버튼. 접근성 이름(label)은 필수. */
export function IconButton({ icon, label, className, ...rest }: { icon: IconName; label: string } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={cn('inline-flex size-9 items-center justify-center rounded-full border border-transparent text-muted transition-colors hover:border-line hover:bg-muted-bg hover:text-ink aria-expanded:border-line aria-expanded:bg-muted-bg', className)}
      {...rest}
    >
      <Icon name={icon} />
    </button>
  );
}
