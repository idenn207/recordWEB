import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { type ReactNode, useState } from 'react';
import { ToastProvider } from '@/shared/ui';

export function Providers({ children }: { children: ReactNode }) {
  // 폴링 화면이 대부분이라 창 포커스 때마다 다시 불러오지 않는다.
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 2000, refetchOnWindowFocus: false, retry: 1 } } }));
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>{children}</ToastProvider>
    </QueryClientProvider>
  );
}
