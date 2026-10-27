import { createBrowserRouter, Navigate } from 'react-router-dom';
import { DashboardPage } from '@/pages/dashboard';
import { AuthGate } from '@/features/sign-in';
import { AppShell } from '@/widgets/app-shell';

// 첫 화면(대시보드)만 즉시 싣고, 나머지 페이지는 들어갈 때 불러온다.
export const router = createBrowserRouter([
  {
    element: (
      <AuthGate>
        <AppShell />
      </AuthGate>
    ),
    HydrateFallback: () => null,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'channels', lazy: async () => ({ Component: (await import('@/pages/channels')).ChannelsPage }) },
      { path: 'files', lazy: async () => ({ Component: (await import('@/pages/files')).FilesPage }) },
      { path: 'uploads', lazy: async () => ({ Component: (await import('@/pages/uploads')).UploadsPage }) },
      { path: 'profile', lazy: async () => ({ Component: (await import('@/features/manage-account')).ProfilePage }) },
      { path: 'settings', lazy: async () => ({ Component: (await import('@/pages/settings')).SettingsPage }) },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);
