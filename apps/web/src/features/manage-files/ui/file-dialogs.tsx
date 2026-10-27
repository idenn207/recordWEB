import { useEffect, useState } from 'react';
import { fileApi, type FileItem, useFileAction } from '@/entities/file';
import { Button, Field, Modal, Notice, TextInput, useToast } from '@/shared/ui';

/** 대화상자 공통: 실패하면 닫지 않고 사유를 보여 준다. */
function useRun(onDone: () => void) {
  const toast = useToast();
  const [error, setError] = useState('');
  const wrap = <T,>(fn: () => Promise<T>, okText: string) => async () => {
    try {
      await fn();
      setError('');
      toast(okText);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    }
  };
  return { error, setError, wrap };
}

export function NameDialog({ kind, parent, target, onClose }: { kind: 'mkdir' | 'rename'; parent: string; target?: FileItem; onClose: () => void }) {
  const [name, setName] = useState(target?.name ?? '');
  const act = useFileAction<string>((n) => (kind === 'mkdir' ? fileApi.mkdir(parent, n) : fileApi.rename(target!.path, n)));
  const { error, wrap } = useRun(onClose);
  useEffect(() => setName(target?.name ?? ''), [target]);
  const submit = wrap(() => act.mutateAsync(name.trim()), kind === 'mkdir' ? '폴더를 만들었습니다' : '이름을 바꿨습니다');
  return (
    <Modal
      open
      onClose={onClose}
      title={kind === 'mkdir' ? '새 폴더' : '이름 변경'}
      footer={
        <>
          <Button onClick={onClose}>취소</Button>
          <Button variant="primary" onClick={submit} disabled={!name.trim() || name === target?.name || act.isPending}>
            {kind === 'mkdir' ? '만들기' : '변경'}
          </Button>
        </>
      }
    >
      <form
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <Field label={kind === 'mkdir' ? '폴더 이름' : '새 이름'}>{(id) => <TextInput id={id} autoFocus value={name} onChange={(e) => setName(e.target.value)} />}</Field>
        {error && <Notice tone="rec">{error}</Notice>}
      </form>
    </Modal>
  );
}

export function MoveDialog({ items, currentDir, roots, onClose }: { items: FileItem[]; currentDir: string; roots: string[]; onClose: () => void }) {
  const [dst, setDst] = useState(currentDir);
  const act = useFileAction((d: string) => fileApi.move(items.map((i) => i.path), d));
  const { error, wrap } = useRun(onClose);
  const submit = wrap(() => act.mutateAsync(dst.trim()), `${items.length}개 항목을 옮겼습니다`);
  return (
    <Modal
      open
      onClose={onClose}
      title="이동"
      footer={
        <>
          <Button onClick={onClose}>취소</Button>
          <Button variant="primary" onClick={submit} disabled={!dst.trim() || act.isPending}>
            이동
          </Button>
        </>
      }
    >
      <form
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <p className="text-muted">{items.length === 1 ? items[0].name : `${items[0].name} 외 ${items.length - 1}개`}</p>
        <Field label="이동할 폴더" hint="없는 폴더는 새로 만듭니다">
          {(id) => (
            <>
              <TextInput id={id} autoFocus list="move-roots" value={dst} onChange={(e) => setDst(e.target.value)} className="font-mono text-[13px]" />
              <datalist id="move-roots">
                {roots.map((r) => (
                  <option key={r} value={r} />
                ))}
              </datalist>
            </>
          )}
        </Field>
        {error && <Notice tone="rec">{error}</Notice>}
      </form>
    </Modal>
  );
}

export function DeleteDialog({ items, trashEnabled, onClose }: { items: FileItem[]; trashEnabled: boolean; onClose: () => void }) {
  const [hard, setHard] = useState(!trashEnabled);
  const act = useFileAction((h: boolean) => fileApi.remove(items.map((i) => i.path), h));
  const { error, wrap } = useRun(onClose);
  const submit = wrap(() => act.mutateAsync(hard), hard ? '삭제했습니다' : '휴지통으로 옮겼습니다');
  return (
    <Modal
      open
      onClose={onClose}
      title="삭제"
      footer={
        <>
          <Button onClick={onClose}>취소</Button>
          <Button variant="danger" onClick={submit} disabled={act.isPending}>
            {hard ? '완전 삭제' : '휴지통으로'}
          </Button>
        </>
      }
    >
      <div className="grid gap-3">
        <p>
          <strong className="break-all">{items.length === 1 ? items[0].name : `${items[0].name} 외 ${items.length - 1}개`}</strong>
          {items.some((i) => i.is_dir) && <span className="text-muted"> (폴더는 안의 파일까지 모두)</span>}
        </p>
        {trashEnabled ? (
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={hard} onChange={(e) => setHard(e.target.checked)} />
            휴지통을 거치지 않고 완전히 삭제
          </label>
        ) : (
          <Notice tone="warn">휴지통이 꺼져 있어 바로 삭제되며 되돌릴 수 없습니다.</Notice>
        )}
        {error && <Notice tone="rec">{error}</Notice>}
      </div>
    </Modal>
  );
}
