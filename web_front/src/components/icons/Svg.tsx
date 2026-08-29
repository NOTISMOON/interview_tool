/**
 * 自定义 SVG 图标基础工厂。
 *
 * 全站统一视觉规范：
 * - 线性描边 1.7px，round 端点/拐角
 * - 默认颜色 currentColor（跟随文本色，配合 tailwind text-* 任意着色）
 * - 琥珀金点缀统一使用 #D9A441（如通知圆点、闪电尖端、收藏星形）
 *
 * @param props size 图标尺寸（默认 1em），其余透传至 <svg>
 */
import type { SVGProps } from 'react';

/** 图标通用 Props：支持外置尺寸与任意 SVG 属性透传 */
export interface IconProps extends SVGProps<SVGSVGElement> {
  size?: number | string;
}

/** 线性图标（描边风格，默认不填充） */
export function Svg({ size = '1em', children, ...rest }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.7}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

/** 实心图标（Filled 变体：fill 当前色，无描边） */
export function SvgFilled({ size = '1em', children, ...rest }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="currentColor"
      stroke="none"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

/** 品牌青（点缀色常量，仅用于需要品牌强调的局部路径） */
export const BRAND = '#D9A441';