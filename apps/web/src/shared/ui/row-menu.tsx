import { Menu, MenuButton, MenuItem, MenuItems } from '@headlessui/react';
import { cn } from '../lib/cn';
import { IconButton } from './button';
import { Icon, type IconName } from './icon';

export interface RowMenuItem {
  label: string;
  icon?: IconName;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
  /** 비활성일 때 이유를 title로 보여 준다 (예: 녹화 중인 파일은 수정할 수 없음) */
  reason?: string;
}

/**
 * 행마다 버튼을 늘어놓지 않고 아이콘 하나로 여는 메뉴.
 * anchor를 쓰면 패널이 body에 떠서 테이블의 스크롤 영역에 잘리지 않는다.
 */
export function RowMenu({ label, items }: { label: string; items: RowMenuItem[] }) {
  return (
    <Menu>
      <MenuButton as={IconButton} icon="more" label={label} />
      <MenuItems anchor={{ to: 'bottom end', gap: 4 }} className="z-40 min-w-44 rounded-lg border border-line bg-card p-1 shadow-float focus-visible:outline-none">
        {items.map((it) => (
          <MenuItem key={it.label} disabled={it.disabled}>
            <button
              type="button"
              onClick={it.onClick}
              title={it.disabled ? it.reason : undefined}
              className={cn('flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left data-[focus]:bg-tint data-[disabled]:opacity-45', it.danger ? 'text-rec' : 'text-ink')}
            >
              {it.icon && <Icon name={it.icon} size={16} />}
              {it.label}
            </button>
          </MenuItem>
        ))}
      </MenuItems>
    </Menu>
  );
}
