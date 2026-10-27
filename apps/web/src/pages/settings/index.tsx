import { useEffect } from 'react';
import { useConfig, useSecrets } from '@/entities/config';
import { SettingsForm } from '@/features/edit-settings';
import { Notice, PageHeader } from '@/shared/ui';

export function SettingsPage() {
  const config = useConfig();
  const secrets = useSecrets();
  // 탭마다 높이가 달라도 스크롤바 유무로 가로 폭이 바뀌지 않게 한다.
  useEffect(() => {
    document.documentElement.style.scrollbarGutter = 'stable';
    return () => void (document.documentElement.style.scrollbarGutter = '');
  }, []);
  const error = config.error ?? secrets.error;
  return (
    <>
      <PageHeader title="설정" />
      {error && <Notice tone="rec">설정을 불러오지 못했습니다. ({(error as Error).message})</Notice>}
      {config.data && secrets.data && <SettingsForm config={config.data} secrets={secrets.data} />}
    </>
  );
}
