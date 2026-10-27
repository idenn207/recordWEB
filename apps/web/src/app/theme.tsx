import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';

export type ThemePref = 'light' | 'dark' | 'system';
const KEY = 'rw-theme';

const resolve = (p: ThemePref) => (p === 'system' ? (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark') : p);

const Ctx = createContext<{ pref: ThemePref; setPref: (p: ThemePref) => void }>({ pref: 'system', setPref: () => undefined });
export const useTheme = () => useContext(Ctx);

/** 라이트, 다크, 시스템 설정 따르기. 선택은 이 브라우저에 저장하고 <html data-theme> 로 적용한다. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPrefState] = useState<ThemePref>(() => (localStorage.getItem(KEY) as ThemePref) || 'system');
  const apply = useCallback((p: ThemePref) => (document.documentElement.dataset.theme = resolve(p)), []);

  useEffect(() => {
    apply(pref);
    if (pref !== 'system') return;
    const mq = matchMedia('(prefers-color-scheme: light)');
    const on = () => apply('system');
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, [pref, apply]);

  const value = useMemo(
    () => ({
      pref,
      setPref: (p: ThemePref) => {
        localStorage.setItem(KEY, p);
        setPrefState(p);
      },
    }),
    [pref],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
