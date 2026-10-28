import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Vite 配置
// 开发期通过 /api 代理到后端，避免跨域配置的来回折腾。
// 生产部署时改为院内网关地址，前端代码不需要动。
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: Number(process.env.VITE_PORT) || 5173,
    host: '127.0.0.1',
    proxy: {
      '/api': {
        // 默认代理到本机 8000；本机已有别的副本占用 8000 时，
        // 用 VITE_API_TARGET 指到另一个端口即可，不必改代码。
        target: process.env.VITE_API_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
    watch: {
      // 编辑器（含某些 IDE 与自动化工具）保存文件时会先写临时目录/临时文件，
      // Vite 的 fs watcher 会去监听它们并抛 EBUSY 把 dev server 整个搞崩。
      // Windows 上这个坑很常见，直接忽略掉这些路径。
      ignored: [
        '**/node_modules/**',
        '**/.git/**',
        '**/dist/**',
        '**/.*.tmpdir/**',
        '**/*.tmpdir/**',
        '**/.*.tmp',
        '**/*.swp',
      ],
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1500,
  },
})
