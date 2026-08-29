/**
 * 自定义图标库统一出口。
 *
 * 导出名与 @ant-design/icons 保持一致，页面中只需将
 * `import { XxxOutlined } from '@ant-design/icons'`
 * 替换为
 * `import { XxxOutlined } from '@/components/icons'`
 * 即可切换为定制线性风图标，JSX 用法不变。
 */
export type { IconProps } from './Svg';
export * from './navigation';
export * from './business';
export * from './social';