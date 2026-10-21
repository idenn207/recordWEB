import type { ReactNode } from 'react';
import { cn } from '../lib/cn';

type Tone = 'neutral' | 'rec' | 'ok' | 'warn';

const TONES: Record<Tone, string> = {
  neutral: 'bg-muted-bg text-muted',
  rec: 'bg-muted-bg text-rec',
  ok: 'bg-ok-bg text-ok',
  warn: 'bg-warn-bg text-warn',
};

/** 상태 칩. 색만으로 구분하지 않도록 항상 문구를 함께 둔다. */
export function Badge({ tone = 'neutral', pulse, children }: { tone?: Tone; pulse?: boolean; children: ReactNode }) {
  return (
    <span className={cn('inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border border-line px-2.5 py-0.5 text-[0.8rem] font-semibold', TONES[tone])}>
      {pulse && <span className="rec-dot h-2 w-2 rounded-full bg-current" />}
      {children}
    </span>
  );
}
