import { describe, expect, it } from "vitest";
import type { FamilyDetail, PenetrationResult } from "./api";
import { assembleReportHtml, REPORT_DISCLAIMER } from "./report";

const penetration: PenetrationResult = {
  root: "e1",
  direction: "up",
  entity_name: "示例甲有限公司<script>",
  names: { e1: "示例甲有限公司<script>", p1: "张测试" },
  at: null,
  truncated: false,
  visited_nodes: 3,
  paths: [],
  control_paths: [],
  cycles: [["e1", "p1", "e1"]],
  cross_holdings: [],
  aggregates: [
    {
      entity_id: "p1",
      entity_kind: "person",
      effective_percent: 51,
      direct_percent: 51,
      path_count: 1,
      unknown_ratio: false,
      statement_ids: ["s1"],
    },
  ],
  ubo_candidates: [
    {
      entity_id: "p1",
      entity_kind: "person",
      effective_percent: 51,
      voting_percent: null,
      has_control_statement: true,
      basis: ["R1"],
      confidence: 1,
      statement_ids: ["s1"],
    },
  ],
  assumptions: ["路径乘积法"],
  warnings: [],
  algorithm_version: "cg-penetration/1.0.0",
  config_hash: "h".repeat(64),
  config: {
    max_depth: 6,
    min_ratio_percent: 0.01,
    max_paths: 5000,
    max_nodes: 20000,
    timeout_seconds: 10,
  },
};

const family: FamilyDetail = {
  family_id: "p1",
  controllers: ["p1"],
  controller_names: ["张测试"],
  member_count: 2,
  region_coverage: 2,
  regions: [],
  region_unknown: 0,
  cycle_count: 0,
  internal_edge_count: 1,
  density: 0.5,
  truncated: false,
  at: "2020-01-01",
  algorithm_version: "cg-families/1.0.0",
  config_hash: "f".repeat(64),
  min_control_ratio_percent: 50,
  members: [
    {
      entity_id: "p1",
      name: "张测试",
      kind: "person",
      region_code: null,
      controller: "p1",
      path: ["p1"],
      path_names: ["张测试"],
      depth: 0,
      statement_ids: [],
    },
  ],
  cycles: [],
  unassigned_entity_count: 0,
  assumptions: ["控制类边口径"],
};

describe("研究报告组装", () => {
  const opts = {
    generatedAt: "2026-09-13T00:00:00Z",
    at: null,
    minRatioPercent: "50",
  };

  it("穿透报告：免责声明、算法版本、口径与表格齐全", () => {
    const html = assembleReportHtml(
      { kind: "penetration", title: "穿透研究报告", data: penetration },
      opts,
    );
    expect(html).toContain(REPORT_DISCLAIMER);
    expect(html).toContain("cg-penetration/1.0.0");
    expect(html).toContain("配置哈希");
    expect(html).toContain("张测试");
    expect(html).toContain("51");
    expect(html).toContain("路径乘积法");
  });

  it("富文本注入被转义", () => {
    const html = assembleReportHtml(
      { kind: "penetration", title: "穿透研究报告", data: penetration },
      opts,
    );
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });

  it("系族报告：控制阈值口径与成员表", () => {
    const html = assembleReportHtml(
      { kind: "family", title: "系族研究报告", data: family },
      opts,
    );
    expect(html).toContain("cg-families/1.0.0");
    expect(html).toContain("50%");
    expect(html).toContain("成员与被控路径");
    expect(html).toContain("张测试");
    expect(html).toContain(REPORT_DISCLAIMER);
  });

  it("流动报告：区域表与口径说明；dataURL 之外图片被拒", () => {
    const flowsCtx = {
      kind: "flows" as const,
      title: "资本流动研究报告",
      data: {
        regions: [
          {
            region: "110000",
            inflow_wan: 300,
            outflow_wan: 1000,
            net_wan: -700,
            outflow_edges: 2,
            inflow_edges: 1,
          },
        ],
        hhi: 5000,
        flow_count: 1,
        internal_edges: 0,
        unknown_region_edges: 0,
        total_cross_amount_wan: 1000,
        cycles: {
          cycle_count: 0,
          cross_region_cycle_edges: 0,
          cross_region_cycle_amount_edges: 0,
        },
        at: null,
      },
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
    };
    const html = assembleReportHtml(flowsCtx, { ...opts, chartPng: "javascript:alert(1)" });
    expect(html).toContain("流出集中度".replace("流出集中度", "110000"));
    expect(html).toContain("HHI = 各省流出金额份额");
    expect(html).not.toContain('src="javascript:');
    // dataURL 图表被接受
    const withPng = assembleReportHtml(flowsCtx, {
      ...opts,
      chartPng: "data:image/png;base64,AAA",
    });
    expect(withPng).toContain('src="data:image/png;base64,AAA"');
  });
});
