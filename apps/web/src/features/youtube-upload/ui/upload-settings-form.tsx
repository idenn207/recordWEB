import { useEffect, useState } from 'react';
import { type UploadSettings, useReauthenticateUpload, useSaveUploadSettings } from '@/entities/upload';
import { Button, Field, Select, TextArea, TextInput, useToast } from '@/shared/ui';

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

  const num = (k: 'rate_mbps' | 'pool') => (e: React.ChangeEvent<HTMLInputElement>) => setS({ ...s, [k]: Number(e.target.value) });

  return (
    <form
      className="grid max-w-2xl gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(
          { settings: { ...s, tags: tags.split(',').map((t) => t.trim()).filter(Boolean) }, token: token.trim() || undefined },
          {
            onSuccess: () => {
              setToken('');
              toast('저장했습니다');
            },
            onError: (err) => toast(err.message, 'error'),
          },
        );
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="공개 범위">
          {(id) => (
            <Select id={id} value={s.privacy} onChange={(e) => setS({ ...s, privacy: e.target.value as UploadSettings['privacy'] })}>
              <option value="unlisted">일부 공개</option>
              <option value="private">비공개</option>
              <option value="public">공개</option>
            </Select>
          )}
        </Field>
        <Field label="자동 업로드 시작일" hint="이 날짜 이후에 녹화된 파일만 자동으로 올립니다">
          {(id) => <TextInput id={id} type="date" value={s.auto_since} onChange={(e) => setS({ ...s, auto_since: e.target.value })} />}
        </Field>
        <Field label="속도 상한 (Mbps)" hint="회선이 포화돼 다른 기기가 끊기면 낮추세요">
          {(id) => <TextInput id={id} type="number" min={1} value={s.rate_mbps} onChange={num('rate_mbps')} />}
        </Field>
        <Field label="동시 업로드 수" hint="재시작 후 적용됩니다">
          {(id) => <TextInput id={id} type="number" min={1} max={10} value={s.pool} onChange={num('pool')} />}
        </Field>
      </div>
      <Field label="영상 설명">{(id) => <TextArea id={id} rows={5} value={s.description} onChange={(e) => setS({ ...s, description: e.target.value })} className="font-sans text-[0.9rem]" />}</Field>
      <Field label="태그" hint="쉼표로 구분">
        {(id) => <TextInput id={id} value={tags} onChange={(e) => setTags(e.target.value)} />}
      </Field>
      <div className="grid gap-3 rounded-lg border border-line p-4">
        <Field label="새 refresh token" hint={hasToken ? '기존과 같은 OAuth 클라이언트에서 발급한 값을 입력하세요. Google 확인에 성공하면 저장하고 업로드를 재개합니다.' : '먼저 아래에서 인증 토큰 전체 JSON을 등록하세요.'}>
          {(id) => <TextInput id={id} type="password" value={refreshToken} onChange={(e) => setRefreshToken(e.target.value)} autoComplete="off" spellCheck={false} disabled={!hasToken || reauth.isPending} />}
        </Field>
        <div>
          <Button type="button" disabled={!hasToken || !refreshToken.trim() || reauth.isPending || save.isPending} onClick={() => {
            reauth.mutate(refreshToken.trim(), {
              onSuccess: () => { setRefreshToken(''); toast('재인증했습니다. 업로드를 재개합니다.'); },
              onError: (err) => toast(err.message, 'error'),
              onSettled: () => reauth.reset(),
            });
          }}>
            {reauth.isPending ? '인증 확인 중…' : '재인증'}
          </Button>
        </div>
        <p className="text-sm text-muted" role="status" aria-live="polite">{reauth.isPending ? 'Google에서 새 토큰을 확인하고 있습니다.' : '인증에 실패하면 기존 토큰은 유지됩니다.'}</p>
      </div>
      <Field label="인증 토큰 전체 JSON" hint={hasToken ? '클라이언트 정보까지 바꿀 때만 붙여 넣으세요.' : '등록해야 업로드됩니다. refresh_token, client_id, client_secret, token_uri가 들어 있어야 합니다.'}>
        {(id) => <TextArea id={id} rows={4} value={token} onChange={(e) => setToken(e.target.value)} placeholder='{"refresh_token": "...", "client_id": "...", ...}' autoComplete="off" spellCheck={false} />}
      </Field>
      <div>
        <Button type="submit" variant="primary" disabled={save.isPending || reauth.isPending}>
          저장
        </Button>
      </div>
    </form>
  );
}
