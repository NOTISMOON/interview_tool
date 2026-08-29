import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  optimizeDeps: {
    // 开启自动扫描，确保 antd 等依赖被正确预构建
    include: [
      'react',
      'react-dom',
      'react-dom/client',
      'react/jsx-runtime',
      'react-router-dom',
      'axios',
      'zustand',
      'dayjs',
      'cos-js-sdk-v5',
      'antd',
      '@ant-design/icons',
      'react-is',
    ],
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    // 产出按模块维度拆分 + 并行加载：减少单 chunk 体积，利用 HTTP/2 并行与浏览器缓存
    modulePreload: {
      polyfill: true,
    },
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name].[hash].js',
        chunkFileNames: 'assets/[name].[hash].js',
        // 函数式分包：按依赖归属拆分，避免大而全的 vendor 导致首屏过大
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          // antd 组件库 + 图标 + 其 rc-* 依赖（先于 react 判断，避免 @ant-design/react-slick 误入 react-vendor）
          if (
            id.includes('/antd/') ||
            id.includes('/antd.esm') ||
            id.includes('@ant-design') ||
            id.includes('/rc-') ||
            id.includes('@rc-component') ||
            id.includes('/react-is/')
          ) {
            return 'antd-vendor';
          }
          // 核心框架：react 全家桶 + 状态管理（精确路径匹配，首屏必需）
          if (
            id.includes('/react/') ||
            id.includes('/react-dom/') ||
            id.includes('/react-router') ||
            id.includes('/scheduler/') ||
            id.includes('/zustand/') ||
            id.includes('/use-sync-external-store/')
          ) {
            return 'react-vendor';
          }
          // 通用工具：axios / dayjs（几乎所有页面使用）
          if (id.includes('/axios/') || id.includes('/dayjs/')) {
            return 'http-utils';
          }
          // 动画库 gsap（独立，配合懒加载页面按需拉取）
          if (id.includes('/gsap/')) {
            return 'gsap-vendor';
          }
          // 腾讯云 COS SDK（仅上传场景使用，独立避免污染主包）
          if (id.includes('cos-js-sdk')) {
            return 'cos-vendor';
          }
          // 其余第三方依赖合并为一个公共包
          return 'vendor';
        },
      },
    },
  },
  server: {
    host: '0.0.0.0',
    allowedHosts: true,
    port: 5645,
    open: true,
  },
});