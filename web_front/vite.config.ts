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
    // 仅扫描主入口，避免 prototype 等无关 HTML 进入依赖扫描（减少 IO 开销）
    entries: ['index.html'],
    include: [
      'react',
      'react-dom',
      'react-dom/client',
      'react-router-dom',
      'antd/es/config-provider',
      'antd/es/app',
      'antd/es/spin',
      'antd/es/locale/zh_CN',
      '@ant-design/icons',
      'axios',
      'zustand',
      'dayjs',
    ],
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name].[hash].js',
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