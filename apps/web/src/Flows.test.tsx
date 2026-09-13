import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { FlowsPage } from "./pages/Flows";

vi.mock("./components/EChart", async (importOriginal) => {
  // jsdom 无 canvas：图组件替换为静态占位，仅保留导出的映射常量供页面使用
  const original = await importOriginal<typeof import("./components/EChart")>();
  return {
    ...original,
    EChart: ({ className }: { className?: string }) => (
      <div data-testid="echart-stub" className={className} />
    ),
  };
});

vi.mock("./api", () => ({
  api: {
    flowsSummary: vi.fn(() =>
      Promise.resolve({
        regions: [
          { region: "110000", inflow_wan: 300, outflow_wan: 1000, net_wan: -700, outflow_edges: 2, inflow_edges: 1 },
          { region: "310000", inflow_wan: 1000, outflow_wan: 300, net_wan: 700, outflow_edges: 1, inflow_edges: 2 },
        ],
        hhi: 5000,
        flow_count: 2,
        internal_edges: 1,
        unknown_region_edges: 0,
        total_cross_amount_wan: 1300,
        cycles: { cycle_count: 1, cross_region_cycle_edges: 1, cross_region_cycle_amount_edges: 1 },
        at: null,
      }),
    ),
    flowsRegions: vi.fn(() =>
      Promise.resolve({
        at: null,
        count: 1,
        flows: [
          {
            from_region: "110000",
            to_region: "310000",
            edge_count: 2,
            amount_edges: 2,
            amount_wan: 1000,
            total_share_percent: 60,
            ratio_missing_edges: 0,
          },
        ],
      }),
    ),
    flowsIndustries: vi.fn(() =>
      Promise.resolve({
        at: null,
        rows: [{ from_region: "110000", industry: "金融业", edge_count: 1, amount_wan: 800 }],
        missing_industry_edges: 0,
      }),
    ),
    flowsTimeline: vi.fn(() =>
      Promise.resolve({
        at: null,
        timeline: [{ year: 2018, edge_count: 1, amount_wan: 1000, amount_missing_edges: 0 }],
      }),
    ),
    entitiesByRegion: vi.fn(() =>
      Promise.resolve({
        region_code: "110000",
        count: 1,
        entities: [{ id: "e1", kind: "company", primary_name: "测试公司", industry: "金融业" }],
      }),
    ),
  },
}));

function renderFlows() {
  return render(
    <MemoryRouter>
      <FlowsPage />
    </MemoryRouter>,
  );
}

describe("FlowsPage", () => {
  it("渲染流动性指标卡片与图表占位", async () => {
    renderFlows();
    expect(await screen.findByText("省际流向")).toBeInTheDocument();
    expect(screen.getByText("流出集中度 HHI")).toBeInTheDocument();
    expect(screen.getAllByTestId("echart-stub").length).toBeGreaterThanOrEqual(4);
  });

  it("提示合成演示数据与地图来源", async () => {
    renderFlows();
    expect(await screen.findByText(/合成演示数据/)).toBeInTheDocument();
    expect(screen.getByText(/DataV.GeoAtlas/)).toBeInTheDocument();
  });
});

describe("FlowsPage 按年回放控件", () => {
  it("渲染播放/暂停按钮、年份滑块与帧信息", async () => {
    renderFlows();
    expect(await screen.findByRole("button", { name: "播放" })).toBeInTheDocument();
    expect(screen.getByTestId("replay-slider")).toBeInTheDocument();
    expect(screen.getByText(/共 1 帧/)).toBeInTheDocument();
    // 初始未回放：无"退出回放"
    expect(screen.queryByText(/退出回放/)).not.toBeInTheDocument();
  });

  it("点击播放后进入回放帧并显示退出", async () => {
    renderFlows();
    fireEvent.click(await screen.findByRole("button", { name: "播放" }));
    expect(await screen.findByText(/回放帧：2018 年/)).toBeInTheDocument();
    expect(screen.getByText(/第 1\/1 帧/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "暂停" })).toBeInTheDocument();
    expect(screen.getByText(/退出回放/)).toBeInTheDocument();
  });
});
