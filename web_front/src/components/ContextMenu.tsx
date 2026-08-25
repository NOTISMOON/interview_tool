/** 通用右键浮窗（ContextMenu）：点击项执行并关闭，点击外部/Esc/滚动自动关闭。 */
import { useEffect, useRef } from 'react';

/** 菜单项定义 */
export interface ContextMenuItem {
  key: string;
  label: string;
  icon?: React.ReactNode;
  danger?: boolean;
  onClick: () => void;
}

interface ContextMenuProps {
  x: number;
  y: number;
  items: ContextMenuItem[];
  onClose: () => void;
}

const MENU_MIN_WIDTH = 150;
const ITEM_HEIGHT = 36;

const ContextMenu = ({ x, y, items, onClose }: ContextMenuProps) => {
  const ref = useRef<HTMLDivElement>(null);

  // 点击外部 / Esc / 滚动 / 窗口尺寸变化时关闭
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    const handleClose = () => onClose();
    document.addEventListener('mousedown', handleClick);
    document.addEventListener('keydown', handleKey);
    window.addEventListener('scroll', handleClose, true);
    window.addEventListener('resize', handleClose);
    return () => {
      document.removeEventListener('mousedown', handleClick);
      document.removeEventListener('keydown', handleKey);
      window.removeEventListener('scroll', handleClose, true);
      window.removeEventListener('resize', handleClose);
    };
  }, [onClose]);

  // 防溢出视口：右/下边界 clamp
  const menuHeight = items.length * ITEM_HEIGHT + 12;
  const left = Math.min(x, window.innerWidth - MENU_MIN_WIDTH - 8);
  const top = Math.min(y, window.innerHeight - menuHeight - 8);

  return (
    <div ref={ref} className="fixed z-[1000]" style={{ left: Math.max(8, left), top: Math.max(8, top) }}>
      <div className="bg-white border border-[#E1E4E8] rounded-xl shadow-lg py-1.5 min-w-[150px]">
        {items.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => {
              item.onClick();
              onClose();
            }}
            className={`w-full text-left px-4 py-2 text-sm flex items-center gap-2 hover:bg-[#F6F8FA] transition-colors ${
              item.danger ? 'text-[#CF222E]' : 'text-[#0D1117]'
            }`}
          >
            {item.icon}
            {item.label}
          </button>
        ))}
      </div>
    </div>
  );
};

export default ContextMenu;
