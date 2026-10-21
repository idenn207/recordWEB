import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from 'react';
import { cn } from '../lib/cn';

type Tone = 'ok' | 'error';
interface ToastItem {
  id: number;
  tone: Tone;
  text: string;
}

const ToastContext = createContext<(text: string, tone?: Tone) => void>(() => undefined);
export const useToast = () => useContext(ToastContext);

/** 작업 결과를 잠깐 알린다. 스크린리더에는 aria-live로 읽힌다. 오류는 더 오래 남긴다. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const push = useCallback((text: string, tone: Tone = 'ok') => {
    const id = Date.now() + Math.random();
    setItems((xs) => [...xs, { id, tone, text }]);
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), tone === 'error' ? 8000 : 3500);
  }, []);
  const value = useMemo(() => push, [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-[min(22rem,calc(100vw-2rem))] flex-col gap-2">
        {items.map((t) => (
          <div key={t.id} role={t.tone === 'error' ? 'alert' : 'status'} className={cn('pointer-events-auto rounded-lg border border-line bg-card px-3.5 py-2.5 shadow-float', t.tone === 'error' ? 'text-rec' : 'text-ink')}>
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
