import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5273,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8300",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    // 仅跑单元测试；Playwright E2E 由 npx playwright test 单独执行
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
