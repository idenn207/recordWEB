import { Dialog } from '@base-ui/react/dialog';
import { type ReactNode, useEffect, useState } from 'react';
import { Button } from './button';
import { TextInput } from './field';

/**
 * 포커스를 가둬야 하는 작업(편집 폼, 파괴적 확인)에만 쓴다.
 * 패널은 가장 높은 층이라 floating 그림자를 쓰고, 안에 또 카드를 중첩하지 않는다.
 */
export function Modal({ open, onClose, title, children, footer, wide }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-black/60 transition-opacity duration-150 data-[ending-style]:opacity-0 data-[starting-style]:opacity-0" />
        <div className="pointer-events-none fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4 sm:items-center">
          <Dialog.Popup
            className={`pointer-events-auto my-auto w-full ${wide ? 'max-w-2xl' : 'max-w-md'} rounded-card border border-line bg-surface shadow-float transition duration-150 data-[ending-style]:translate-y-1 data-[ending-style]:opacity-0 data-[starting-style]:translate-y-1 data-[starting-style]:opacity-0`}
          >
            <Dialog.Title className="border-b border-line px-5 py-3.5 text-base font-semibold">{title}</Dialog.Title>
            <div className="px-5 py-4">{children}</div>
            {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
          </Dialog.Popup>
        </div>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  children,
  confirmLabel,
  danger,
  busy,
  requireText,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  /** 되돌릴 수 없는 큰 작업: 이 문구를 직접 입력해야 확인 버튼이 켜진다 (PATTERNS.md 1절) */
  requireText?: string;
}) {
  const [typed, setTyped] = useState('');
  useEffect(() => setTyped(''), [open]);
  const blocked = !!requireText && typed.trim() !== requireText;
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button onClick={onClose}>취소</Button>
          <Button variant={danger ? 'danger' : 'primary'} onClick={onConfirm} disabled={busy || blocked} title={blocked ? `“${requireText}”를 입력하면 켜집니다` : undefined}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="text-muted">{children}</div>
      {requireText && (
        <label className="mt-3 grid gap-1 text-xs font-semibold text-muted">
          확인하려면 <span className="text-ink">{requireText}</span> 를 입력하세요
          <TextInput value={typed} onChange={(e) => setTyped(e.target.value)} autoComplete="off" className="text-sm font-normal text-ink" />
        </label>
      )}
    </Modal>
  );
}
