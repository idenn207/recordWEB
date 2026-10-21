import { useEffect, useState } from 'react';
import { type Channel, PLATFORM_NAME, type Platform, QUALITIES, useAddChannel, useCheckX, useUpdateChannel, type XCheckResult } from '@/entities/channel';
import { Button, Field, Icon, Modal, Notice, Select, TextInput, ToggleRow } from '@/shared/ui';

const EMPTY: Channel = {
  platform: 'chzzk',
  id: '',
  name: '',
  output_dir: 'chzzk',
  quality: 'best',
  extension: '.ts',
  record_enabled: false,
  recordWatchParty: false,
  watchPartyExcludeTags: [],
};

/** channel이 있으면 수정, 없으면 추가. */
export function ChannelFormDialog({ open, onClose, channel }: { open: boolean; onClose: () => void; channel?: Channel }) {
  const editing = !!channel;
  const [form, setForm] = useState<Channel>(EMPTY);
  const [tags, setTags] = useState('');
  const [error, setError] = useState('');
  const [check, setCheck] = useState<XCheckResult | null>(null);
  const checkX = useCheckX();
  const add = useAddChannel();
  const update = useUpdateChannel();

  useEffect(() => {
    if (!open) return;
    setForm(channel ?? EMPTY);
    setTags((channel?.watchPartyExcludeTags ?? []).join(', '));
    setError('');
    setCheck(null);
  }, [open, channel]);

  const set = <K extends keyof Channel>(k: K, v: Channel[K]) => setForm((f) => ({ ...f, [k]: v }));
  const changePlatform = (p: Platform) =>
    setForm((f) => ({ ...f, platform: p, quality: 'best', extension: p === 'youtube' ? '.mkv' : p === 'x' ? '.m4a' : '.ts', recordWatchParty: false, output_dir: p === 'x' ? 'xspaces' : f.output_dir === 'xspaces' ? 'chzzk' : f.output_dir }));

  const submit = () => {
    const body = { ...form, id: form.id.trim(), name: form.name.trim(), watchPartyExcludeTags: tags.split(',').map((s) => s.trim()).filter(Boolean), x_user_id: form.platform === 'x' ? form.x_user_id?.trim() || undefined : undefined };
    const done = { onSuccess: onClose, onError: (e: Error) => setError(e.message) };
    if (editing) update.mutate({ id: channel.id, patch: body }, done);
    else add.mutate(body, done);
  };
  const busy = add.isPending || update.isPending;
  const yt = form.platform === 'youtube';
  const x = form.platform === 'x';
  const runCheck = () => checkX.mutate({ handle: form.id, userId: form.x_user_id }, { onSuccess: setCheck, onError: (e) => setCheck({ steps: [{ name: '요청', ok: false, detail: e.message }] }) });

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editing ? `${channel.name} 수정` : '채널 추가'}
      wide
      footer={
        <>
          <Button onClick={onClose}>취소</Button>
          <Button variant="primary" onClick={submit} disabled={busy || !form.id.trim() || !form.name.trim()}>
            {editing ? '저장' : '추가'}
          </Button>
        </>
      }
    >
      <form
        className="grid gap-4 sm:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <Field label="플랫폼">
          {(id) => (
            <Select id={id} value={form.platform} onChange={(e) => changePlatform(e.target.value as Platform)} disabled={editing}>
              {(['chzzk', 'youtube', 'x'] as const).map((p) => (
                <option key={p} value={p}>
                  {PLATFORM_NAME[p]}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="채널 이름" hint="파일명에 들어갑니다">
          {(id) => <TextInput id={id} value={form.name} onChange={(e) => set('name', e.target.value)} />}
        </Field>
        <Field label={x ? 'X 프로필 (@핸들)' : yt ? '채널 핸들 또는 ID' : '채널 ID'} hint={x ? '@HanayoHiyori 또는 프로필 주소. 스페이스 주소는 방송마다 바뀌므로 프로필만 등록합니다' : yt ? '@핸들 또는 UC로 시작하는 채널 ID' : 'chzzk.naver.com/ 뒤의 32자리 값'}>
          {(id) => <TextInput id={id} value={form.id} onChange={(e) => set('id', e.target.value)} disabled={editing} className="font-mono text-[0.85rem]" />}
        </Field>
        <Field label="저장 경로" hint="앱 폴더 기준 상대 경로 또는 절대 경로">
          {(id) => <TextInput id={id} value={form.output_dir} onChange={(e) => set('output_dir', e.target.value)} />}
        </Field>
        {!x && (
        <Field label="품질">
          {(id) => (
            <Select id={id} value={form.quality} onChange={(e) => set('quality', e.target.value)}>
              {QUALITIES[form.platform].map((q) => (
                <option key={q}>{q}</option>
              ))}
            </Select>
          )}
        </Field>
        )}
        {!x && (
        <Field label="확장자" hint={yt ? '유튜브는 .mkv로 고정됩니다' : undefined}>
          {(id) => (
            <Select id={id} value={form.extension} onChange={(e) => set('extension', e.target.value)} disabled={yt}>
              {(yt ? ['.mkv'] : ['.ts', '.mp4']).map((ext) => (
                <option key={ext}>{ext}</option>
              ))}
            </Select>
          )}
        </Field>
        )}

        {x && (
          <div className="grid gap-4 sm:col-span-2">
            <Notice tone="neutral">스페이스 감시에는 X 로그인 쿠키가 필요합니다. 설정 → 계정·알림에서 먼저 등록하세요. 음성은 .m4a로 저장되고, 감시는 2분 간격으로 합니다.</Notice>
            <Field label="X 사용자 ID (선택)" hint="비워 두면 핸들로 자동 조회합니다. 자동 조회가 막히면 숫자 ID를 직접 입력하세요">
              {(id) => <TextInput id={id} value={form.x_user_id ?? ''} onChange={(e) => set('x_user_id', e.target.value)} inputMode="numeric" className="font-mono text-[0.85rem]" />}
            </Field>
            <div className="grid gap-2">
              <div>
                <Button icon="refresh" onClick={runCheck} disabled={!form.id.trim() || checkX.isPending}>
                  {checkX.isPending ? '확인 중…' : '연결 확인'}
                </Button>
              </div>
              {check && (
                <ul className="grid gap-1" aria-label="연결 확인 결과">
                  {check.steps.map((s) => (
                    <li key={s.name} className="flex items-start gap-2">
                      <Icon name={s.ok ? 'check' : 'alert'} size={16} className={`mt-0.5 shrink-0 ${s.ok ? 'text-ok' : 'text-warn'}`} />
                      <span>
                        <strong>{s.name}</strong> {s.ok ? '확인됨' : '실패'} — <span className="text-muted">{s.detail}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        )}

        {!yt && !x && (
          <div className="sm:col-span-2">
            <ToggleRow label="같이보기만 녹화" hint="같이보기(공동 시청) 방송일 때만 녹화합니다" checked={form.recordWatchParty} onChange={(v) => set('recordWatchParty', v)} />
            {form.recordWatchParty && (
              <Field label="녹화 제외할 태그" hint="쉼표로 구분. 같이보기 태그에 포함되면 녹화하지 않습니다">
                {(id) => <TextInput id={id} value={tags} onChange={(e) => setTags(e.target.value)} placeholder="예: LCK, VCT" />}
              </Field>
            )}
          </div>
        )}

        {!yt && !x && (
          <div className="grid gap-4 border-t border-line pt-4 sm:col-span-2 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <ToggleRow label="녹화 후 YouTube 자동 업로드" hint="켠 뒤에 녹화된 파일부터 자동으로 올립니다. 이전 파일은 파일 관리에서 직접 고릅니다" checked={!!form.yt_auto_upload} onChange={(v) => set('yt_auto_upload', v)} />
            </div>
            <Field label="YouTube 재생목록 ID" hint="비워 두면 재생목록에 추가하지 않습니다">
              {(id) => <TextInput id={id} value={form.yt_playlist_id ?? ''} onChange={(e) => set('yt_playlist_id', e.target.value)} className="font-mono text-[0.85rem]" />}
            </Field>
          </div>
        )}
        {error && (
          <div className="sm:col-span-2">
            <Notice tone="rec">{error}</Notice>
          </div>
        )}
        <button type="submit" hidden />
      </form>
    </Modal>
  );
}
