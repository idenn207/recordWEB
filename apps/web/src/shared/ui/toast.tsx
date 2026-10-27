import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from 'react';
import { cn } from '../lib/cn';
import { Icon } from './icon';

type Tone = 'ok' | 'error';
interface ToastItem {
  id: number;
  tone: Tone;
  text: string;
}

const ToastContext = createContext<(text: string, tone?: Tone) => void>(() => undefined);
export const useToast = () => useContext(ToastContext);

/**
 * 작업 결과 알림. 성공은 잠깐 보이고 사라지며, 오류는 닫기 전까지 남는다(PATTERNS.md 5절).
 * 오류가 놓치지 않게 상단 중앙에 크게 띄우고, 스크린리더에는 role=alert 로 바로 읽힌다.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const dismiss = useCallback((id: number) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  const push = useCallback(
    (text: string, tone: Tone = 'ok') => {
      const id = Date.now() + Math.random();
      setItems((xs) => {
        // 넘치면 닫지 않은 오류보다 성공 알림부터 지운다
        const drop = xs.length >= 4 ? (xs.find((x) => x.tone === 'ok') ?? xs[0]) : null;
        return [...xs.filter((x) => x !== drop), { id, tone, text }];
      });
      if (tone === 'ok') setTimeout(() => dismiss(id), 4000);
    },
    [dismiss],
  );
  const value = useMemo(() => push, [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 top-4 z-[60] flex flex-col items-center gap-2 px-4">
        {items.map((t) => (
          <div
            key={t.id}
            role={t.tone === 'error' ? 'alert' : 'status'}
            className={cn('pointer-events-auto flex w-full max-w-md items-start gap-3 rounded-card border px-4 py-3 shadow-float', t.tone === 'error' ? 'border-rec/50 bg-err-bg text-ink' : 'border-ok/40 bg-ok-bg text-ink')}
          >
            <Icon name={t.tone === 'error' ? 'alert' : 'check'} className={cn('mt-0.5 shrink-0', t.tone === 'error' ? 'text-rec' : 'text-ok')} />
            <p className="min-w-0 flex-1">{t.text}</p>
            <button type="button" aria-label="알림 닫기" onClick={() => dismiss(t.id)} className="-m-1 rounded-control p-1 text-muted hover:text-ink">
              <Icon name="x" size={16} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
