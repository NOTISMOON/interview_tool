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
      'classnames',
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