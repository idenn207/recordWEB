import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// 개발 중에는 /api를 NestJS(5000)로 넘긴다. 운영에서는 NestJS가 빌드된 dist를 직접 서빙한다.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5173, proxy: { '/api': 'http://localhost:5000' } },
  resolve: { alias: { '@': new URL('./src', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1') } },
});
