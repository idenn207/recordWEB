import type { ReactNode } from 'react';
import { cn } from '../lib/cn';

/**
 * 선택이나 변경 때문에 나타나는 작업 줄. 화면 아래에 떠 있어서(fixed) 원래 레이아웃을 밀지 않는다.
 * 문서 흐름 안에 조건부로 끼워 넣으면 아래 요소가 밀려 같은 자리를 다시 눌렀을 때 다른 대상이 눌린다.
 * 모바일에서는 아래 탭바(56px) 위에 뜬다. 가려지는 마지막 내용은 main 의 아래 여백이 비워 둔다.
 */
export function FloatingBar({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-[calc(3.5rem+env(safe-area-inset-bottom)+0.75rem)] z-40 flex justify-center px-4 md:bottom-6">
      <div role="region" aria-label={label} className={cn('pointer-events-auto flex max-w-full flex-wrap items-center gap-2 rounded-card border border-line bg-surface px-3 py-2.5 shadow-float', className)}>
        {children}
      </div>
    </div>
  );
}
