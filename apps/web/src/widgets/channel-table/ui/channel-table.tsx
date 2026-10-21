import { useState } from 'react';
import { type Channel, type ChannelWithStatus, PlatformMark, useChannels, useDeleteChannel, useToggleChannel } from '@/entities/channel';
import { ChannelFormDialog } from '@/features/edit-channel';
import { Badge, Button, ConfirmDialog, EmptyState, Notice, PageHeader, RowMenu, Toggle, useToast } from '@/shared/ui';

const TH = 'sticky top-0 whitespace-nowrap bg-muted-bg px-3 py-2 text-left text-[0.8rem] font-semibold tracking-[0.02em] text-muted';
const TD = 'px-3 py-2.5 align-middle';

export function ChannelTable() {
  const { data, isLoading, error } = useChannels(8000);
  const toggle = useToggleChannel();
  const remove = useDeleteChannel();
  const toast = useToast();
  const [editing, setEditing] = useState<Channel | 'new' | null>(null);
  const [deleting, setDeleting] = useState<ChannelWithStatus | null>(null);

  return (
    <>
      <PageHeader title="채널 관리">
        <Button variant="primary" icon="plus" onClick={() => setEditing('new')}>
          채널 추가
        </Button>
      </PageHeader>

      {error && <Notice tone="rec">채널 목록을 불러오지 못했습니다. ({(error as Error).message})</Notice>}
      {isLoading && <p className="text-muted">불러오는 중…</p>}
      {data && data.length === 0 && <EmptyState title="등록된 채널이 없습니다">오른쪽 위의 “채널 추가”로 녹화할 채널을 등록하세요.</EmptyState>}

      {data && data.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-line bg-card shadow-card">
          <table className="w-full border-collapse md:min-w-[46rem]">
            <thead>
              <tr>
                <th className={TH}>채널</th>
                <th className={`${TH} max-md:hidden`}>저장 경로</th>
                <th className={`${TH} max-md:hidden`}>품질</th>
                <th className={TH}>자동 녹화</th>
                <th className={`${TH} max-md:hidden`}>YouTube 업로드</th>
                <th className={`${TH} w-12`}>
                  <span className="sr-only">작업</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {data.map((c) => (
                <tr key={c.id} className="border-t border-line hover:bg-tint">
                  <td className={TD}>
                    <div className="flex items-center gap-2">
                      <PlatformMark platform={c.platform} />
                      <span className="font-bold">{c.name}</span>
                    </div>
                    <div className="mt-0.5 max-w-[9.5rem] truncate font-mono text-[0.8rem] text-muted md:max-w-64" title={c.id}>
                      {c.id}
                    </div>
                    <div className="mt-0.5 text-[0.8rem] text-muted md:hidden">
                      {c.quality} {c.extension} · {c.output_dir}
                      {c.platform === 'chzzk' && c.yt_auto_upload && ' · 자동 업로드'}
                    </div>
                  </td>
                  <td className={`${TD} font-mono text-[0.85rem] text-muted max-md:hidden`}>{c.output_dir}</td>
                  <td className={`${TD} text-muted max-md:hidden`}>
                    {c.quality} <span className="font-mono text-[0.8rem]">{c.extension}</span>
                  </td>
                  <td className={TD}>
                    <Toggle checked={c.record_enabled} onChange={() => toggle.mutate(c.id)} label={`${c.name} 자동 녹화`} />
                  </td>
                  <td className={`${TD} max-md:hidden`}>
                    {c.platform === 'youtube' ? (
                      <span className="text-muted">해당 없음</span>
                    ) : c.yt_auto_upload ? (
                      <Badge tone="ok">자동{c.yt_playlist_id ? ' · 재생목록' : ''}</Badge>
                    ) : (
                      <span className="text-muted">수동</span>
                    )}
                  </td>
                  <td className={`${TD} text-right`}>
                    <RowMenu
                      label={`${c.name} 작업 메뉴`}
                      items={[
                        { label: '수정', icon: 'edit', onClick: () => setEditing(c) },
                        { label: '삭제', icon: 'trash', danger: true, onClick: () => setDeleting(c) },
                      ]}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ChannelFormDialog open={editing !== null} onClose={() => setEditing(null)} channel={editing === 'new' || editing === null ? undefined : editing} />
      <ConfirmDialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        onConfirm={() => deleting && remove.mutate(deleting.id, { onSuccess: () => toast(`${deleting.name} 채널을 삭제했습니다`), onError: (e) => toast(e.message, 'error'), onSettled: () => setDeleting(null) })}
        title={`${deleting?.name ?? ''} 채널을 삭제할까요?`}
        confirmLabel="삭제"
        danger
        busy={remove.isPending}
      >
        {deleting?.status.state === 'recording' ? '지금 녹화 중이라 녹화가 중지됩니다. ' : ''}이미 녹화된 파일은 지워지지 않습니다.
      </ConfirmDialog>
    </>
  );
}
