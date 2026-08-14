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
  build:{
    outDir: 'dist',
    assetsDir: 'assets',
    rollupOptions: {
      output: {
        entryFileNames: 'assets/[name].[hash].js',
  }   
    }
  },
  server: {
    host: '0.0.0.0', // 监听所有地址，允许外部访问（内网穿透需要）
    allowedHosts: true ,// 完全关闭主机检查（最快捷）
    port: 5645,
    open: true,
  },
});