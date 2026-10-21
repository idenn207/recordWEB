import type { ButtonHTMLAttributes } from 'react';
import { cn } from '../lib/cn';
import { Icon, type IconName } from './icon';

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost';

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-brand text-brand-ink border-line hover:bg-brand-hover font-bold',
  secondary: 'bg-card text-ink border-line hover:bg-muted-bg font-semibold',
  danger: 'bg-card text-rec border-line hover:bg-muted-bg font-semibold',
  ghost: 'bg-transparent text-muted border-transparent hover:bg-muted-bg hover:text-ink font-semibold',
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
        'inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-lg border transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-50',
        small ? 'px-2.5 py-1 text-[0.8rem]' : 'px-3.5 py-2',
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
      className={cn('inline-flex h-[30px] w-[30px] items-center justify-center rounded-lg border border-transparent text-muted transition-colors hover:border-line hover:bg-muted-bg hover:text-ink aria-expanded:border-line aria-expanded:bg-muted-bg', className)}
      {...rest}
    >
      <Icon name={icon} />
    </button>
  );
}
