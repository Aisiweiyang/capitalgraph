import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { FamiliesPage } from "./pages/Families";

vi.mock("./components/FamilyGraph", () => ({
  // jsdom 无 canvas：系族子图替换为静态占位
  FamilyGraph: () => <div data-testid="family-graph-stub" />,
}));

const listPayload = {
  at: null,
  algorithm_version: "cg-families/1.0.0",
  config_hash: "a".repeat(64),
  min_control_ratio_percent: 50,
  count: 1,
  returned: 1,
  unassigned_entity_count: 3,
  missing_ratio_holding_edges: 1,
  assumptions: ["控制类边 = controls 声明 + 比例 ≥ 阈值的 holds_shares 声明；"],
  families: [
    {
      family_id: "p1",
      controllers: ["p1"],
      controller_names: ["王伟"],
      member_count: 3,
      region_coverage: 2,
      regions: [
        ["110000", 1],
        ["310000", 1],
      ],
      region_unknown: 1,
      cycle_count: 1,
      internal_edge_count: 3,
      density: 0.5,
      truncated: false,
    },
  ],
};

const detailPayload = {
  ...listPayload.families[0],
  at: null,
  algorithm_version: "cg-families/1.0.0",
  config_hash: "a".repeat(64),
  min_control_ratio_percent: 50,
  members: [
    {
      entity_id: "p1",
      name: "王伟",
      kind: "person",
      region_code: null,
      controller: "p1",
      path: ["p1"],
      path_names: ["王伟"],
      depth: 0,
      statement_ids: [],
    },
    {
      entity_id: "c1",
      name: "华康科技北京有限公司",
      kind: "company",
      region_code: "110000",
      controller: "p1",
      path: ["p1", "c1"],
      path_names: ["王伟", "华康科技北京有限公司"],
      depth: 1,
      statement_ids: ["s1"],
    },
  ],
  cycles: [["王伟", "华康科技北京有限公司", "王伟"]],
  unassigned_entity_count: 3,
  assumptions: ["控制类边 = controls 声明 + 比例 ≥ 阈值的 holds_shares 声明；"],
};

const flowsPayload = {
  rows: [
    {
      from_family: "p1",
      to_family: "p2",
      edge_count: 2,
      amount_edges: 1,
      amount_wan: 800,
      amount_missing_edges: 1,
    },
  ],
  intra_family_edges: 3,
  ungrouped_edges: 1,
  family_names: { p1: "王伟", p2: "李娜" },
  algorithm_version: "cg-families/1.0.0",
  at: null,
  count: 1,
};

vi.mock("./api", () => ({
  api: {
    families: vi.fn(() => Promise.resolve(listPayload)),
    family: vi.fn(() => Promise.resolve(detailPayload)),
    familiesFlows: vi.fn(() => Promise.resolve(flowsPayload)),
  },
}));

function renderFamilies() {
  return render(
    <MemoryRouter>
      <FamiliesPage />
    </MemoryRouter>,
  );
}

describe("FamiliesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("渲染系族列表与统计卡片", async () => {
    renderFamilies();
    expect(await screen.findByText("识别系族")).toBeInTheDocument();
    expect(await screen.findByText("王伟")).toBeInTheDocument();
    expect(screen.getByText("无控制人实体")).toBeInTheDocument();
    expect(screen.getByText("缺比例持股边")).toBeInTheDocument();
  });

  it("点击系族后加载成员路径、环路标记与族间流向", async () => {
    renderFamilies();
    fireEvent.click(await screen.findByText("王伟"));
    expect(await screen.findByTestId("family-graph-stub")).toBeInTheDocument();
    expect(screen.getAllByText(/被控路径/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/族内环路/)).toBeInTheDocument();
    // 族间流向：family_names 解析后的显示名；金额 800 万元直接展示
    expect(await screen.findByText(/李娜/)).toBeInTheDocument();
    expect(screen.getByText("800")).toBeInTheDocument();
  });

  it("声明算法候选与免责口径", async () => {
    renderFamilies();
    expect(await screen.findByText(/不构成法律认定或投资建议/)).toBeInTheDocument();
    expect(screen.getByText(/cg-families\/1\.0\.0/)).toBeInTheDocument();
  });
});
