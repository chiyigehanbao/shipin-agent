import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Vite 配置：React、路径别名、开发代理
// 本机 Comfy Desktop 常占用 127.0.0.1:8000，幻帧后端默认用 8010
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    open: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
      '/media': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
      },
    },
  },
})
