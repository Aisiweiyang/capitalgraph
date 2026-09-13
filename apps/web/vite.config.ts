import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    // 路由级代码分割后，echarts（地图/桑基/趋势）集中在懒加载的 Flows chunk，
    // 按需加载不影响首屏；阈值仅用于把告警留给真正的回归（见 TEST_REPORT §v0.5.1）
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        // 重组件独立命名 chunk：体积分析时一眼可辨，仍由路由懒加载触发下载
        manualChunks(id) {
          if (id.includes("node_modules/echarts") || id.includes("node_modules/zrender")) {
            return "vendor-echarts";
          }
          if (id.includes("node_modules/cytoscape")) return "vendor-cytoscape";
        },
      },
    },
  },
  server: {
    port: 5273,
    proxy: {
      "/api": {
        // 同机并行运行其他项目（默认占用 8300）时可用 CG_API_PROXY 覆盖
        target: process.env.CG_API_PROXY ?? "http://127.0.0.1:8300",
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
