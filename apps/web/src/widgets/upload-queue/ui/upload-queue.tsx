import { type QueueRow, useUploads } from '@/entities/upload';
import { UploadSettingsForm } from '@/features/youtube-upload';
import { Badge, EmptyState, Icon, Notice, PageHeader } from '@/shared/ui';

const STATE: Record<QueueRow['state'], { label: string; tone: 'neutral' | 'rec' | 'ok' | 'warn' }> = {
  uploading: { label: '업로드 중', tone: 'rec' },
  waiting: { label: '한도 대기', tone: 'warn' },
  error: { label: '오류', tone: 'warn' },
  queued: { label: '대기', tone: 'neutral' },
  done: { label: '완료', tone: 'ok' },
};

const TH = 'sticky top-0 bg-muted-bg px-3 py-2 text-left text-[0.8rem] font-semibold tracking-[0.02em] text-muted';

export function UploadQueue() {
  const { data, error, isLoading } = useUploads();
  const pending = data?.items.filter((i) => i.state !== 'done') ?? [];
  const done = (data?.items.length ?? 0) - pending.length;

  return (
    <>
      <PageHeader title="YouTube 업로드">
        {data && (
          <span className="tnum text-muted">
            진행 {pending.length} · 완료 {done}
          </span>
        )}
      </PageHeader>

      <div className="mb-4 grid gap-2">
        {error && <Notice tone="rec">업로드 상태를 불러오지 못했습니다. ({(error as Error).message})</Notice>}
        {data?.auth_error && <Notice tone="rec">업로드가 중단되었습니다: {data.auth_error}. 아래에서 토큰을 다시 등록하면 이어서 올립니다.</Notice>}
        {data && !data.has_token && !data.auth_error && <Notice>인증 토큰이 없습니다. 아래 설정에서 토큰을 등록해야 업로드할 수 있습니다.</Notice>}
      </div>

      {isLoading && <p className="text-muted">불러오는 중…</p>}
      {data && data.items.length === 0 && (
        <EmptyState title="업로드 대기 중인 파일이 없습니다">채널 관리에서 자동 업로드를 켜거나, 파일 관리에서 파일의 메뉴로 직접 올릴 수 있습니다.</EmptyState>
      )}
      {data && data.items.length > 0 && (
        <div className="max-h-[28rem] overflow-auto rounded-xl border border-line bg-card shadow-card">
          <table className="w-full min-w-[34rem] border-collapse">
            <thead>
              <tr>
                <th className={`${TH} w-28`}>상태</th>
                <th className={TH}>파일</th>
                <th className={`${TH} w-1/4`}>비고</th>
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
                      <a href={`https://youtu.be/${r.video_id}`} target="_blank" rel="noopener noreferrer" className="inline-flex max-w-full items-center gap-1.5 text-link hover:underline" title={r.name}>
                        <span className="truncate">{r.name}</span>
                        <Icon name="link" size={14} className="shrink-0" />
                      </a>
                    ) : (
                      <span className="block truncate" title={r.name}>
                        {r.name}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-[0.85rem] text-muted">{r.msg || r.privacy || ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && (
        <section className="mt-8" aria-labelledby="upload-settings">
          <h2 id="upload-settings" className="mb-3 text-[1.05rem] font-bold">
            업로드 설정
          </h2>
          <UploadSettingsForm settings={data.settings} hasToken={data.has_token} />
        </section>
      )}
    </>
  );
}
