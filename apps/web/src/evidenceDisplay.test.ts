import { describe, expect, it } from "vitest";
import type { EvidenceCoverageOut } from "./api";
import { coverageHeadline } from "./evidenceDisplay";

function out(partial: Partial<EvidenceCoverageOut>): EvidenceCoverageOut {
  return {
    at: null,
    algorithm_version: "cg-evidence-coverage/1.0.0",
    total_active_statements: 4,
    covered_statements: 3,
    missing_statements: 1,
    coverage_percent: 75,
    by_predicate: [],
    by_connector: [],
    by_year: [],
    missing_sample_size: 1,
    missing_samples: [],
    assumptions: [],
    ...partial,
  } as EvidenceCoverageOut;
}

describe("coverageHeadline", () => {
  it("全量覆盖：百分比取整展示，无薄弱分组", () => {
    const h = coverageHeadline(out({ coverage_percent: 100, missing_statements: 0 }));
    expect(h.percentText).toBe("100%");
    expect(h.missingText).toBe("0");
    expect(h.weakest).toBeNull();
  });

  it("存在缺失时按谓词找出覆盖率最低的分组", () => {
    const h = coverageHeadline(
      out({
        coverage_percent: 75,
        by_predicate: [
          { key: "holds_shares", total: 2, covered: 1, missing: 1, coverage_percent: 50 },
          { key: "controls", total: 2, covered: 2, missing: 0, coverage_percent: 100 },
        ],
      }),
    );
    expect(h.percentText).toBe("75%");
    expect(h.weakest?.label).toBe("holds_shares");
    expect(h.weakest?.group.missing).toBe(1);
  });

  it("空库：百分比为 —", () => {
    const h = coverageHeadline(
      out({ total_active_statements: 0, covered_statements: 0, coverage_percent: null }),
    );
    expect(h.percentText).toBe("—");
    expect(h.totalText).toBe("0");
  });
});

// ---------------- v0.6 切片 A：覆盖率趋势组装（ADR-019）

import { CoverageTimelineRow } from "./api";
import { coverageTimelineOption, deltaText } from "./evidenceDisplay";

function tl(year: number, coverage_percent: number | null): CoverageTimelineRow {
  return {
    year,
    total: 4,
    covered: 2,
    missing: 2,
    coverage_percent,
    delta_vs_prev: null,
  };
}

describe("coverageTimelineOption", () => {
  it("年度作为类目轴，覆盖率为单序列", () => {
    const opt = coverageTimelineOption([tl(2020, 50), tl(2021, 75)]) as {
      xAxis: { data: string[] };
      series: { data: (number | null)[] }[];
    };
    expect(opt.xAxis.data).toEqual(["2020", "2021"]);
    expect(opt.series).toHaveLength(1);
    expect(opt.series[0].data).toEqual([50, 75]);
  });

  it("无覆盖率的年份保留 null 占位（断线不补值）", () => {
    const opt = coverageTimelineOption([tl(2020, null), tl(2021, 100)]) as {
      series: { data: (number | null)[] }[];
    };
    expect(opt.series[0].data).toEqual([null, 100]);
  });

  it("空数据：轴与序列为空数组（页面据此显式空态）", () => {
    const opt = coverageTimelineOption([]) as {
      xAxis: { data: string[] };
      series: { data: unknown[] }[];
    };
    expect(opt.xAxis.data).toEqual([]);
    expect(opt.series[0].data).toEqual([]);
  });
});

describe("deltaText", () => {
  it("正数带加号，负数原样，空值占位", () => {
    expect(deltaText(50)).toBe("+50");
    expect(deltaText(-25)).toBe("-25");
    expect(deltaText(null)).toBe("—");
  });
});

// ---------------- v0.6 切片 B：时效区展示口径（ADR-020）

import type { EvidenceStalenessOut, StalenessScanOut } from "./api";
import { qualityScanText, stalenessScanText, stalenessSummaryText } from "./evidenceDisplay";

const staleOut = {
  at: "2024-01-02",
  years: 5,
  cutoff: "2019-01-02",
  algorithm_version: "cg-evidence-staleness/1.0.0",
  stale_count: 1,
  stale_candidates: [],
  assumptions: [],
} as EvidenceStalenessOut;

it("stalenessSummaryText：截止日期 + 候选数", () => {
  expect(stalenessSummaryText(staleOut)).toBe("截止 2019-01-02 · 候选 1 条");
});

it("stalenessScanText：入库/跳过计数与规则名", () => {
  const scan = {
    at: "2024-01-02",
    years: 5,
    total_candidates: 1,
    created: 1,
    skipped: 0,
    rule_name: "stale_source",
  } as StalenessScanOut;
  expect(stalenessScanText(scan)).toBe("已入库 1 条（跳过重复 0 条）· 规则 stale_source");
  expect(stalenessScanText({ ...scan, created: 0, skipped: 1 })).toBe(
    "已入库 0 条（跳过重复 1 条）· 规则 stale_source",
  );
});


describe("qualityScanText", () => {
  it("登记计数与规则名随文案输出", () => {
    expect(
      qualityScanText({
        at: "2026-09-16",
        total_candidates: 2,
        created: 1,
        skipped: 1,
        by_rule: { identifier_validity: 1, duplicate_statement: 0, cross_source_conflict: 0 },
        rule_names: ["identifier_validity", "duplicate_statement", "cross_source_conflict"],
      }),
    ).toBe("已入库 1 条（跳过重复 1 条）· identifier_validity/duplicate_statement/cross_source_conflict");
  });
});
