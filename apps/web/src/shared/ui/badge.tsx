import type { ReactNode } from 'react';
import { cn } from '../lib/cn';

type Tone = 'neutral' | 'rec' | 'ok' | 'warn';

const TONES: Record<Tone, string> = {
  neutral: 'bg-muted-bg text-muted',
  rec: 'bg-err-bg text-rec',
  ok: 'bg-ok-bg text-ok',
  warn: 'bg-warn-bg text-warn',
};
const DOT: Record<Tone, string> = { neutral: 'bg-chrome-muted', rec: 'bg-rec', ok: 'bg-ok', warn: 'bg-warn' };

/**
 * 상태 칩. 색만으로 구분하지 않도록 항상 문구를 함께 둔다.
 * solid 는 썸네일 위에 올릴 때 쓴다: 어두운 바탕에 색 점과 흰 글자라 어떤 이미지 위에서도 읽힌다.
 */
export function Badge({ tone = 'neutral', pulse, solid, large, children }: { tone?: Tone; pulse?: boolean; solid?: boolean; large?: boolean; children: ReactNode }) {
  return (
    <span className={cn('inline-flex items-center gap-1.5 whitespace-nowrap rounded-full font-semibold', large ? 'px-3 py-1 text-[13px]' : 'px-2.5 py-0.5 text-xs', solid ? 'bg-chrome/90 text-chrome-ink' : TONES[tone])}>
      {(pulse || solid) && <span className={cn('size-2 rounded-full', pulse && 'rec-dot', solid ? DOT[tone] : 'bg-current')} />}
      {children}
    </span>
  );
}
