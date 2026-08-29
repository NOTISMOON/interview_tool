/**
 * 导航与通用图标（线性风格，标准开源路径）。
 * 导出名与 @ant-design/icons 保持一致，便于直接替换 import 来源。
 */
import type { IconProps } from './Svg';
import { Svg, SvgFilled, BRAND } from './Svg';

/** 首页 */
export function HomeOutlined(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <path d="M9 22V12h6v10" />
    </Svg>
  );
}

/** 开始面试（播放圆钮） */
export function PlayCircleOutlined(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="10" />
      <path d="m10 8 6 4-6 4Z" />
    </Svg>
  );
}

/** 历史记录（时钟 + 回环箭头） */
export function HistoryOutlined(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
      <path d="M3 3v5h5" />
      <path d="M12 7v5l4 2" />
    </Svg>
  );
}

/** 社区（双人） */
export function TeamOutlined(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </Svg>
  );
}

/** 消息（气泡） */
export function MessageOutlined(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </Svg>
  );
}

/** 通知（铃铛 + 品牌青圆点） */
export function BellOutlined(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
      <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
    </Svg>
  );
}

/** 设置（调节滑杆） */
export function SettingOutlined(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M4 6h16M4 12h16M4 18h16" />
      <circle cx="9" cy="6" r="2" />
      <circle cx="15" cy="12" r="2" />
      <circle cx="7" cy="18" r="2" />
    </Svg>
  );
}

/** 退出登录 */
export function LogoutOutlined(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="m16 17 5-5-5-5" />
      <path d="M21 12H9" />
    </Svg>
  );
}

/** 闪电（雷霆，线性） */
export function ThunderboltOutlined(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8Z" />
    </Svg>
  );
}

/** 闪电面试实心（品牌 Logo 专用） */
export function ThunderboltFilled(props: IconProps) {
  return (
    <SvgFilled {...props}>
      <path d="M13 2 3 14h9l-1 8 10-12h-9l1-8Z" />
    </SvgFilled>
  );
}

/** 返回（左箭头） */
export function ArrowLeftOutlined(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M19 12H5" />
      <path d="m12 19-7-7 7-7" />
    </Svg>
  );
}

/** 下一步（右箭头） */
export function RightOutlined(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </Svg>
  );
}

/** 更多（三点） */
export function MoreOutlined(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="5" cy="12" r="1.5" />
      <circle cx="12" cy="12" r="1.5" />
      <circle cx="19" cy="12" r="1.5" />
    </Svg>
  );
}

/** 面板（仪表盘 2x2 网格） */
export function DashboardOutlined(props: IconProps) {
  return (
    <Svg {...props}>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </Svg>
  );
}

/** 暂停（圆钮） */
export function PauseCircleOutlined(props: IconProps) {
  return (
    <Svg {...props}>
      <circle cx="12" cy="12" r="10" />
      <path d="M10 15V9M14 15V9" />
    </Svg>
  );
}