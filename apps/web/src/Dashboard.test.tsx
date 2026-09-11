import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { DashboardPage, BarChart } from "./pages/Dashboard";

vi.mock("./api", () => ({
  api: {
    stats: vi.fn(() =>
      Promise.resolve({
        entities_total: 42,
        entities_by_kind: { company: 30, person: 10, fund: 2 },
        statements_total: 88,
        statements_by_predicate: { holds_shares: 60, controls: 28 },
        statements_by_status: { active: 70, superseded: 18 },
        statements_by_year: { "2019": 30, "2020": 58 },
        sources_total: 12,
        snapshots_total: 20,
        review_open: 3,
        runs_total: 4,
        runs_failed: 0,
        last_run: {
          connector_id: "synthetic",
          status: "success",
          started_at: "2026-09-11T08:00:00",
          finished_at: "2026-09-11T08:00:05",
        },
      }),
    ),
  },
}));

function renderDashboard() {
  return render(
    <MemoryRouter>
      <DashboardPage />
    </MemoryRouter>,
  );
}

describe("DashboardPage", () => {
  it("渲染统计卡片与分布图表", async () => {
    renderDashboard();
    expect(await screen.findByText("数据总览")).toBeInTheDocument();
    expect(await screen.findByText("实体总数")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    // 类型分布使用中文标签
    expect(screen.getByText("企业")).toBeInTheDocument();
    expect(screen.getByText("自然人")).toBeInTheDocument();
    expect(screen.getByText("持股")).toBeInTheDocument();
    expect(screen.getByText("2020 年")).toBeInTheDocument();
  });

  it("快捷入口与最近采集信息可见", async () => {
    renderDashboard();
    expect(await screen.findByText(/最近采集/)).toBeInTheDocument();
    expect(screen.getByText("股权穿透图")).toBeInTheDocument();
  });
});

describe("BarChart", () => {
  it("空数据时显示空状态", () => {
    render(
      <MemoryRouter>
        <BarChart title="测试图" data={[]} labelFor={(k) => k} horizontal />
      </MemoryRouter>,
    );
    expect(screen.getByText("暂无数据")).toBeInTheDocument();
  });
});
