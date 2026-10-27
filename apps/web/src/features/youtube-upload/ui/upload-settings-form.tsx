import { useEffect, useState } from 'react';
import { type UploadSettings, useReauthenticateUpload, useSaveUploadSettings } from '@/entities/upload';
import { Button, Card, CardHeader, Field, Select, TextArea, TextInput, useToast } from '@/shared/ui';

/** 업로드 설정과 인증 토큰. 토큰은 바꿀 때만 붙여 넣는다 (저장하면 입력란을 비운다). */
export function UploadSettingsForm({ settings, hasToken }: { settings: UploadSettings; hasToken: boolean }) {
  const [s, setS] = useState(settings);
  const [tags, setTags] = useState(settings.tags.join(', '));
  const [token, setToken] = useState('');
  const [refreshToken, setRefreshToken] = useState('');
  const reauth = useReauthenticateUpload();
  const save = useSaveUploadSettings();
  const toast = useToast();

  // 폴링 갱신이 입력 중인 값을 덮어쓰지 않도록, 서버 값이 실제로 달라졌을 때만 다시 채운다.
  const serverKey = JSON.stringify(settings);
  useEffect(() => {
    setS(settings);
    setTags(settings.tags.join(', '));
  }, [serverKey]); // eslint-disable-line react-hooks/exhaustive-deps

  const dirty =
    s.privacy !== settings.privacy || s.auto_since !== settings.auto_since || s.rate_mbps !== settings.rate_mbps ||
    s.pool !== settings.pool || s.description !== settings.description || tags !== settings.tags.join(', ');
  const authDirty = !!refreshToken.trim() || !!token.trim();
  const busy = save.isPending || reauth.isPending;

  const num = (k: 'rate_mbps' | 'pool') => (e: React.ChangeEvent<HTMLInputElement>) => setS({ ...s, [k]: Number(e.target.value) });

  return (
    <div className="grid items-start gap-6 lg:grid-cols-2">
      <Card>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!dirty || busy) return;
            save.mutate(
              { settings: { ...s, tags: tags.split(',').map((t) => t.trim()).filter(Boolean) } },
              { onSuccess: () => toast('저장했습니다.'), onError: (err) => toast(err.message, 'error') },
            );
          }}
        >
          <CardHeader title="업로드 옵션" />
          <div className="grid gap-4 p-5">
            <div className="grid gap-4 sm:max-lg:grid-cols-2">
              <Field label="공개 범위">
                {(id) => (
                  <Select id={id} value={s.privacy} onChange={(e) => setS({ ...s, privacy: e.target.value as UploadSettings['privacy'] })}>
                    <option value="unlisted">일부 공개</option>
                    <option value="private">비공개</option>
                    <option value="public">공개</option>
                  </Select>
                )}
              </Field>
              <Field label="자동 업로드 시작일">
                {(id) => <TextInput id={id} type="date" value={s.auto_since} onChange={(e) => setS({ ...s, auto_since: e.target.value })} />}
              </Field>
              <Field label="속도 상한 (Mbps)">
                {(id) => <TextInput id={id} type="number" min={1} value={s.rate_mbps} onChange={num('rate_mbps')} />}
              </Field>
              <Field label="동시 업로드 수" hint="재시작 후 적용">
                {(id) => <TextInput id={id} type="number" min={1} max={10} value={s.pool} onChange={num('pool')} />}
              </Field>
            </div>
            <Field label="영상 설명">{(id) => <TextArea id={id} rows={5} value={s.description} onChange={(e) => setS({ ...s, description: e.target.value })} className="font-sans text-sm" />}</Field>
            <Field label="태그">
              {(id) => <TextInput id={id} value={tags} onChange={(e) => setTags(e.target.value)} />}
            </Field>
          </div>
          <Footer dirty={dirty} pending={save.isPending} disabled={!dirty || busy} />
        </form>
      </Card>

      <Card>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!authDirty || busy) return;
            const done = () => { setToken(''); setRefreshToken(''); };
            if (token.trim()) {
              save.mutate({ settings, token: token.trim() }, { onSuccess: () => { done(); toast('저장했습니다.'); }, onError: (err) => toast(err.message, 'error') });
            } else if (hasToken) {
              reauth.mutate(refreshToken.trim(), {
                onSuccess: () => { done(); toast('재인증했습니다. 업로드를 이어서 진행합니다.'); },
                onError: (err) => toast(err.message, 'error'),
                onSettled: () => reauth.reset(),
              });
            }
          }}
        >
          <CardHeader title="인증" />
          <div className="grid gap-4 p-5">
            <Field label="새 refresh token" hint={hasToken ? undefined : '먼저 아래에 인증 토큰 JSON을 등록하세요.'}>
              {(id) => <TextInput id={id} type="password" value={refreshToken} onChange={(e) => setRefreshToken(e.target.value)} autoComplete="off" spellCheck={false} disabled={!hasToken || busy} />}
            </Field>
            <Field label="인증 토큰 전체 JSON" hint={hasToken ? '클라이언트 정보까지 바꿀 때만 붙여 넣으세요.' : 'refresh_token, client_id, client_secret, token_uri가 필요합니다.'}>
              {(id) => <TextArea id={id} rows={4} value={token} onChange={(e) => setToken(e.target.value)} placeholder='{"refresh_token": "...", "client_id": "...", ...}' autoComplete="off" spellCheck={false} />}
            </Field>
          </div>
          <Footer dirty={authDirty} pending={busy} disabled={!authDirty || busy} />
        </form>
      </Card>
    </div>
  );
}

/** 높이가 고정된 카드 푸터. 문구만 바뀌고 자리는 그대로다. */
function Footer({ dirty, pending, disabled }: { dirty: boolean; pending: boolean; disabled: boolean }) {
  return (
    <div className="flex h-16 items-center justify-between gap-3 border-t border-line px-5">
      <span className="text-sm text-muted" role="status" aria-live="polite">{pending ? '저장하는 중…' : dirty ? '저장하지 않은 변경' : ''}</span>
      <Button type="submit" variant={dirty ? 'primary' : 'secondary'} disabled={disabled}>저장</Button>
    </div>
  );
}
