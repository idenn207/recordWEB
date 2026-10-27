import { useEffect, useState } from 'react';
import { useChannels, useCheckX, type XCheckResult } from '@/entities/channel';
import { useSaveSecrets } from '@/entities/config';
import { Badge, Button, Field, Icon, Notice, TextInput, useToast } from '@/shared/ui';

/** 한 줄 쿠키, Netscape 파일, 값만 붙여 넣은 경우를 모두 받아 두 값으로 나눈다. */
export function parseXCookie(text: string): { authToken?: string; ct0?: string } {
  const pick = (name: string) => new RegExp(String.raw`(?:^|[;\s])${name}(?:=|\t)([^;\s]+)`, 'm').exec(text)?.[1];
  return { authToken: pick('auth_token'), ct0: pick('ct0') };
}

export function XConnectCard({ stored }: { stored: string }) {
  const toast = useToast();
  const save = useSaveSecrets();
  const check = useCheckX();
  const channels = useChannels(60_000);
  const xChannels = (channels.data ?? []).filter((c) => c.platform === 'x');
  const [authToken, setAuthToken] = useState('');
  const [ct0, setCt0] = useState('');
  const [result, setResult] = useState<XCheckResult | null>(null);
  const [busy, setBusy] = useState(false);

  const registered = !!stored.trim();
  useEffect(() => {
    const p = parseXCookie(stored);
    setAuthToken(p.authToken ?? '');
    setCt0(p.ct0 ?? '');
    setResult(null);
  }, [stored]);

  // 어느 칸에 붙여 넣든 둘 다 들어 있으면 나눠 채운다. 값 하나만 붙여 넣으면 그 칸에만 들어간다.
  const onPaste = (e: React.ClipboardEvent) => {
    const p = parseXCookie(e.clipboardData.getData('text'));
    if (!p.authToken && !p.ct0) return;
    e.preventDefault();
    if (p.authToken) setAuthToken(p.authToken);
    if (p.ct0) setCt0(p.ct0);
    setResult(null);
  };

  const connect = async () => {
    setBusy(true);
    setResult(null);
    try {
      await save.mutateAsync({ xCookie: `auth_token=${authToken.trim()}; ct0=${ct0.trim()}` });
      const first = xChannels[0];
      if (!first) {
        toast('쿠키를 저장했습니다. X 채널을 추가하면 연결을 확인합니다.');
        return;
      }
      const r = await check.mutateAsync({ handle: first.id, userId: first.x_user_id });
      setResult(r);
      const failed = r.steps.find((s) => !s.ok);
      if (failed) toast(failed.detail, 'error');
      else toast(r.spaceId ? '연결됐고 스페이스가 진행 중입니다.' : '연결됐습니다. 스페이스가 열리면 자동으로 녹음합니다.');
    } catch (e) {
      toast((e as Error).message, 'error');
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    try {
      await save.mutateAsync({ xCookie: '' });
      setResult(null);
      toast('X 쿠키를 삭제했습니다.');
    } catch (e) {
      toast((e as Error).message, 'error');
    }
  };

  const ready = authToken.trim() !== '' && ct0.trim() !== '';
  const failed = result?.steps.find((s) => !s.ok);

  return (
    <section id="x" className="grid gap-4 rounded-card border border-line bg-surface p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">X 스페이스</h2>
        {failed ? <Badge tone="rec">연결 실패</Badge> : result ? <Badge tone="ok">연결됨</Badge> : registered ? <Badge tone="neutral">쿠키 등록됨 · 미확인</Badge> : <Badge tone="warn">쿠키 없음</Badge>}
      </div>

      <details open={!registered} className="text-muted">
        <summary className="cursor-pointer text-link">쿠키 찾는 방법</summary>
        <ol className="mt-2 grid max-w-[68ch] list-decimal gap-1 pl-5">
          <li>녹음에 쓸 계정으로 x.com에 로그인합니다.</li>
          <li>F12 → Application → Cookies → https://x.com 에서 auth_token과 ct0 값을 복사합니다.</li>
          <li>아래 칸에 붙여 넣습니다. 두 값을 한 번에 붙여 넣어도 나뉘어 들어갑니다.</li>
        </ol>
      </details>

      <div className="grid gap-4 sm:grid-cols-2" onPaste={onPaste}>
        <Field label="auth_token">{(id) => <TextInput id={id} value={authToken} onChange={(e) => (setAuthToken(e.target.value), setResult(null))} autoComplete="off" spellCheck={false} className="font-mono text-[13px]" />}</Field>
        <Field label="ct0">{(id) => <TextInput id={id} value={ct0} onChange={(e) => (setCt0(e.target.value), setResult(null))} autoComplete="off" spellCheck={false} className="font-mono text-[13px]" />}</Field>
      </div>

      {result && (
        <ul className="grid gap-1.5" aria-label="연결 확인 결과">
          {result.steps.map((s) => (
            <li key={s.name} className="flex items-start gap-2">
              <Icon name={s.ok ? 'check' : 'alert'} size={16} className={`mt-0.5 shrink-0 ${s.ok ? 'text-ok' : 'text-rec'}`} />
              <span>
                <span className="font-semibold">{s.name}</span> <span className="text-muted">{s.detail}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
      {failed && <Notice tone="rec">{failed.detail}</Notice>}
      {!xChannels.length && registered && <Notice tone="neutral">녹화할 X 채널이 없습니다. 채널에서 X 프로필을 추가하세요.</Notice>}

      <div className="flex flex-wrap items-center gap-3">
        <Button variant="primary" icon="link" disabled={!ready || busy} onClick={connect}>
          {busy ? '확인하는 중…' : '연결 확인'}
        </Button>
        {registered && (
          <Button variant="danger" disabled={busy || save.isPending} onClick={remove}>
            쿠키 삭제
          </Button>
        )}
      </div>
    </section>
  );
}
