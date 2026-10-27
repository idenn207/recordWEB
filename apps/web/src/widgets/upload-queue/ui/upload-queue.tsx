import { type QueueRow, useUploads } from '@/entities/upload';
import { UploadSettingsForm } from '@/features/youtube-upload';
import { Badge, Card, CardHeader, EmptyState, Icon, ListSkeleton, Notice, PageHeader } from '@/shared/ui';

const STATE: Record<QueueRow['state'], { label: string; tone: 'neutral' | 'rec' | 'ok' | 'warn' }> = {
  uploading: { label: '업로드 중', tone: 'rec' },
  waiting: { label: '한도 대기', tone: 'warn' },
  error: { label: '오류', tone: 'warn' },
  queued: { label: '대기', tone: 'neutral' },
  done: { label: '완료', tone: 'ok' },
};

const PRIVACY: Record<string, string> = { unlisted: '일부 공개', private: '비공개', public: '공개' };
const REASON: Record<string, string> = { quotaExceeded: '일일 업로드 한도를 넘었습니다. 한도가 풀리면 다시 시도합니다.' };

const TH = 'whitespace-nowrap sticky top-0 bg-muted-bg px-3 py-2 text-left text-xs font-semibold tracking-[0.02em] text-muted';

export function UploadQueue() {
  const { data, error, isLoading } = useUploads();
  const pending = data?.items.filter((i) => i.state !== 'done') ?? [];
  const done = (data?.items.length ?? 0) - pending.length;

  return (
    <>
      <PageHeader title="YouTube 업로드" />

      <div className="mb-4 grid gap-2 empty:hidden">
        {error && <Notice tone="rec">업로드 상태를 불러오지 못했습니다. 서버가 켜져 있는지 확인하세요.</Notice>}
        {data?.auth_error && <Notice tone="rec">인증이 만료되어 업로드가 멈췄습니다. 아래에서 토큰을 다시 등록하면 이어서 올립니다.</Notice>}
        {data && !data.has_token && !data.auth_error && <Notice>인증 토큰이 없습니다. 아래에서 등록하면 업로드할 수 있습니다.</Notice>}
      </div>

      {isLoading && <ListSkeleton />}
      {data && data.items.length === 0 && (
        <EmptyState title="업로드할 파일이 없습니다">채널에서 자동 업로드를 켜거나, 파일 메뉴에서 직접 올릴 수 있습니다.</EmptyState>
      )}
      {data && data.items.length > 0 && (
        <Card className="mb-6 overflow-hidden">
          <CardHeader title="업로드 큐">
            <span className="tnum text-sm text-muted">진행 {pending.length} · 완료 {done}</span>
          </CardHeader>
          <div className="max-h-[28rem] overflow-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                <th className={`${TH} w-32`}>상태</th>
                <th className={TH}>파일</th>
                <th className={`${TH} hidden w-1/4 md:table-cell`}>비고</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.name} className="border-t border-line hover:bg-tint">
                  <td className="px-3 py-2">
                    <Badge tone={STATE[r.state].tone} pulse={r.state === 'uploading'}>
                      {STATE[r.state].label}
                    </Badge>
                  </td>
                  <td className="max-w-0 px-3 py-2">
                    {r.video_id ? (
                      <a href={`https://youtu.be/${r.video_id}`} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-6 max-w-full items-center gap-1.5 text-link hover:underline" title={r.name}>
                        <span className="truncate">{r.name}</span>
                        <Icon name="link" size={14} className="shrink-0" />
                      </a>
                    ) : (
                      <span className="block truncate" title={r.name}>
                        {r.name}
                      </span>
                    )}
                  </td>
                  <td className="hidden px-3 py-2 text-[13px] md:table-cell text-muted">{REASON[r.msg] ?? (r.msg || (r.privacy ? PRIVACY[r.privacy] ?? r.privacy : ''))}</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </Card>
      )}

      {data && <UploadSettingsForm settings={data.settings} hasToken={data.has_token} />}
    </>
  );
}
