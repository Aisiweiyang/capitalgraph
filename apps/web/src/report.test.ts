import { describe, expect, it } from "vitest";
import type { EvidenceFragment, FamilyDetail, FamiliesCompareOut, FlowsCompareOut, PenetrationResult } from "./api";
import {
  assembleReportHtml,
  buildReportEvidence,
  evidenceSup,
  staleCapturedAt,
  REPORT_DISCLAIMER,
} from "./report";

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

describe("报告证据引用表（v0.5 切片 C）", () => {
  const fragments: Record<string, EvidenceFragment[]> = {
    s1: [
      {
        fragment_id: "f1",
        field_path: "shareholders[0].ratio",
        raw_value: "51.00%",
        normalized_value: "51.00%",
        page_ref: "synthetic",
        content_sha256: "a".repeat(64),
        fetched_at: "2023-06-01T00:00:00Z",
        raw_stored: true,
        source_url: "internal://synthetic",
        document_title: "合成演示数据（虚构）",
      },
    ],
  };

  it("buildReportEvidence：编号按首次出现顺序，statement → 文档/路径/哈希前 12 位", () => {
    const evd = buildReportEvidence(["s1", "s1", "s2"], fragments);
    expect(evd.entries).toHaveLength(2);
    expect(evd.refByStatement).toEqual({ s1: 1, s2: 2 });
    expect(evd.entries[0]).toMatchObject({
      no: 1,
      statement_id: "s1",
      document_title: "合成演示数据（虚构）",
      field_path: "shareholders[0].ratio",
      content_sha256: "a".repeat(12),
    });
    expect(evd.entries[1].document_title).toContain("未登记");
  });

  it("行内上标：引用声明编号并去重排序；无引用为空", () => {
    const evd = buildReportEvidence(["s1", "s2"], fragments);
    expect(evidenceSup(["s2", "s1", "s1"], evd.refByStatement)).toBe("<sup>[1,2]</sup>");
    expect(evidenceSup(["s9"], evd.refByStatement)).toBe("");
    expect(evidenceSup(undefined, evd.refByStatement)).toBe("");
    expect(evidenceSup(["s1"], undefined)).toBe("");
  });

  it("穿透报告附证据上标与证据引用表", () => {
    const evd = buildReportEvidence(["s1"], fragments);
    const html = assembleReportHtml(
      { kind: "penetration", title: "穿透研究报告", data: penetration },
      { generatedAt: "2026-09-14T00:00:00Z", evidence: evd },
    );
    expect(html).toContain("证据引用表");
    expect(html).toContain("<sup>[1]</sup>");
    expect(html).toContain("shareholders[0].ratio");
    expect(html).toContain("a".repeat(12));
  });

  it("未提供证据时报告不含证据表（向后兼容）", () => {
    const html = assembleReportHtml(
      { kind: "penetration", title: "穿透研究报告", data: penetration },
      { generatedAt: "2026-09-14T00:00:00Z" },
    );
    expect(html).not.toContain("证据引用表");
    expect(html).not.toContain("<sup>");
  });
});

describe("对比报告组装（v0.5 切片 B）", () => {
  it("系族对比报告：窗口/族出现/消失/变化表", () => {
    const cmp = {
      from: "2022-01-01",
      to: "2023-01-01",
      algorithm_version: "cg-compare/1.0.0",
      min_control_ratio_percent: 50,
      family_count: { before: 2, after: 3, delta: 1 },
      added_families: [{ family_id: "p2", family_name: "李四", member_count: 3 }],
      removed_families: [{ family_id: "p0", family_name: "王五", member_count: 2 }],
      changed: [
        {
          family_id: "p1",
          family_name: "张三",
          controllers_added: [],
          controllers_removed: [],
          members_added: ["c9"],
          members_removed: [],
          members_added_names: ["新公司"],
          members_removed_names: [],
          member_count_before: 2,
          member_count_after: 3,
          region_coverage_before: 1,
          region_coverage_after: 2,
          cycle_count_before: 0,
          cycle_count_after: 0,
        },
      ],
      unchanged_count: 1,
      unassigned_entity_count: { before: 0, after: 0, delta: 0 },
      assumptions: ["对比口径"],
    } as unknown as FamiliesCompareOut;
    const html = assembleReportHtml(
      { kind: "families_compare", title: "系族格局对比报告", data: cmp },
      { generatedAt: "2026-09-14T00:00:00Z" },
    );
    expect(html).toContain("2022-01-01 → 2023-01-01");
    expect(html).toContain("族出现");
    expect(html).toContain("族消失");
    expect(html).toContain("族变化");
    expect(html).toContain("李四");
    expect(html).toContain("新公司");
    expect(html).toContain("cg-compare/1.0.0");
    expect(html).toContain(REPORT_DISCLAIMER);
  });

  it("流动对比报告：总量指标与流向对增减", () => {
    const cmp = {
      from: "2022-01-01",
      to: "2023-01-01",
      algorithm_version: "cg-compare/1.0.0",
      totals: {
        flow_count: { before: 5, after: 6, delta: 1 },
        total_cross_amount_wan: { before: 8000, after: 9000, delta: 1000 },
        hhi: { before: null, after: 9000, delta: null },
      },
      flows_added: [
        {
          from_region: "320000",
          to_region: "310000",
          edge_count: 1,
          amount_edges: 1,
          amount_wan: 1000,
          total_share_percent: null,
          ratio_missing_edges: 1,
        },
      ],
      flows_removed: [],
      flows_changed: [],
      flow_pair_delta_check: true,
      assumptions: ["对比口径"],
    } as unknown as FlowsCompareOut;
    const html = assembleReportHtml(
      { kind: "flows_compare", title: "区域流动格局对比报告", data: cmp },
      { generatedAt: "2026-09-14T00:00:00Z" },
    );
    expect(html).toContain("总量对比");
    expect(html).toContain("新增流向对");
    expect(html).toContain("320000 → 310000");
    expect(html).toContain("9000");
    expect(html).toContain("—");
    expect(html).not.toContain("<sup>");
  });
});

describe("报告证据成色（v0.6 切片 C）", () => {
  const frag = (sid: string, fetched_at: string): EvidenceFragment[] => [
    {
      fragment_id: `f-${sid}`,
      field_path: `p/${sid}`,
      raw_value: sid,
      normalized_value: sid,
      page_ref: "synthetic",
      content_sha256: "b".repeat(64),
      fetched_at,
      raw_stored: true,
      source_url: "",
      document_title: "doc",
    },
  ];
  const evidence = {
    s_old: frag("s_old", "2019-01-01T00:00:00+00:00"),
    s_new: frag("s_new", "2023-06-01T00:00:00+00:00"),
  };

  it("staleCapturedAt：恰好等于 N 年不算陈旧；缺快照时间的证据不定性", () => {
    expect(staleCapturedAt("2019-01-01T00:00:00Z", "2024-01-02", 5)).toBe(true);
    expect(staleCapturedAt("2019-01-02T00:00:00Z", "2024-01-02", 5)).toBe(false);
    expect(staleCapturedAt(null, "2024-01-02", 5)).toBe(false);
    expect(staleCapturedAt("not-a-date", "2024-01-02", 5)).toBe(false);
  });

  it("buildReportEvidence 附快照时间与陈旧标记（阈值可传，默认 5 年）", () => {
    const evd = buildReportEvidence(["s_old", "s_new"], evidence, { at: "2024-01-02" });
    expect(evd.stale_years).toBe(5);
    expect(evd.entries[0].captured_at).toBe("2019-01-01T00:00:00+00:00");
    expect(evd.entries[0].stale).toBe(true);
    expect(evd.entries[1].stale).toBe(false);
    const tight = buildReportEvidence(["s_old"], evidence, { at: "2024-01-02", years: 8 });
    expect(tight.entries[0].stale).toBe(false);
  });

  it("证据引用表新增快照时间列，陈旧条目标注且说明只提示不认定", () => {
    const evd = buildReportEvidence(["s_old", "s_new"], evidence, { at: "2024-01-02" });
    const html = assembleReportHtml(
      { kind: "penetration", title: "穿透研究报告", data: penetration },
      { generatedAt: "2026-09-14T00:00:00Z", evidence: evd },
    );
    expect(html).toContain("快照时间");
    expect(html).toContain("陈旧(&gt;5 年)");
    expect(html).toContain("2019-01-01");
    expect(html).toContain("只提示");
    expect(html).toContain("class=\"stale\"");
  });

  it("报告元信息附覆盖率摘要；未传时不含该行（降级不显示）", () => {
    const withCov = assembleReportHtml(
      { kind: "penetration", title: "穿透研究报告", data: penetration },
      {
        generatedAt: "2026-09-14T00:00:00Z",
        coverageSummary: { coverage_percent: 99.95, total_active_statements: 2008, missing_statements: 1 },
      },
    );
    expect(withCov).toContain("证据覆盖率");
    expect(withCov).toContain("99.95%");
    expect(withCov).toContain("2008");
    const without = assembleReportHtml(
      { kind: "penetration", title: "穿透研究报告", data: penetration },
      { generatedAt: "2026-09-14T00:00:00Z" },
    );
    expect(without).not.toContain("证据覆盖率");
  });
});
