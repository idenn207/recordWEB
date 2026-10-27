import { Menu } from '@base-ui/react/menu';
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

/** 행마다 버튼을 늘어놓지 않고 아이콘 하나로 여는 메뉴. 포털로 떠서 테이블의 스크롤 영역에 잘리지 않는다. */
export function RowMenu({ label, items }: { label: string; items: RowMenuItem[] }) {
  return (
    <Menu.Root>
      <Menu.Trigger render={<IconButton icon="more" label={label} />} />
      <Menu.Portal>
        <Menu.Positioner side="bottom" align="end" sideOffset={4} className="z-40">
          <Menu.Popup className="min-w-44 rounded-control border border-line bg-surface p-1 shadow-float outline-none">
            {items.map((it) => (
              <Menu.Item
                key={it.label}
                disabled={it.disabled}
                onClick={it.onClick}
                title={it.disabled ? it.reason : undefined}
                className={cn('flex w-full cursor-pointer items-center gap-2 rounded-md px-2.5 py-1.5 text-left outline-none data-[highlighted]:bg-muted-bg data-[disabled]:cursor-not-allowed data-[disabled]:opacity-45', it.danger ? 'text-rec' : 'text-ink')}
              >
                {it.icon && <Icon name={it.icon} size={16} />}
                {it.label}
              </Menu.Item>
            ))}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}
