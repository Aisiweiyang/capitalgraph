/** 证据工作台的展示口径（纯函数，供覆盖率卡片、趋势图、时效区与单测使用）。 */

import type {
  CoverageGroup,
  CoverageTimelineRow,
  EvidenceCoverageOut,
  EvidenceStalenessOut,
  StalenessScanOut,
} from "./api";
import type { EChartsCoreOption } from "./components/EChart";

export interface CoverageHeadline {
  percentText: string;
  totalText: string;
  missingText: string;
  /** 覆盖率最低且有缺失的分组（按谓词优先），供"最薄弱环节"提示。 */
  weakest: { label: string; group: CoverageGroup } | null;
}

export function coverageHeadline(out: EvidenceCoverageOut): CoverageHeadline {
  const percentText =
    out.coverage_percent != null ? `${out.coverage_percent.toFixed(2).replace(/\.00$/, "")}%` : "—";
  const weakestGroup = [...out.by_predicate]
    .filter((g) => g.missing > 0)
    .sort((a, b) => a.coverage_percent! - b.coverage_percent!)[0];
  return {
    percentText,
    totalText: out.total_active_statements.toLocaleString("zh-CN"),
    missingText: out.missing_statements.toLocaleString("zh-CN"),
    weakest: weakestGroup
      ? { label: String(weakestGroup.key), group: weakestGroup }
      : null,
  };
}

/** 覆盖率趋势折线图：年度为 x 轴，覆盖率为单序列（无数据年份断线，不补值）。 */
export function coverageTimelineOption(timeline: CoverageTimelineRow[]): EChartsCoreOption {
  return {
    grid: { left: 48, right: 16, top: 24, bottom: 28 },
    tooltip: {
      trigger: "axis",
      valueFormatter: (v: unknown) => (v == null ? "—" : `${v}%`),
    },
    xAxis: { type: "category", data: timeline.map((r) => String(r.year)) },
    yAxis: { type: "value", min: 0, max: 100, axisLabel: { formatter: "{value}%" } },
    series: [
      {
        name: "覆盖率",
        type: "line",
        data: timeline.map((r) => r.coverage_percent),
        connectNulls: false,
      },
    ],
  };
}

/** 逐年前后的变化量展示：正数带 + 号，无前值为 —。 */
export function deltaText(delta: number | null): string {
  if (delta == null) return "—";
  return `${delta > 0 ? "+" : ""}${delta}`;
}

/** 时效区摘要行：截止日期与候选数。 */
export function stalenessSummaryText(out: EvidenceStalenessOut): string {
  return `截止 ${out.cutoff} · 候选 ${out.stale_count} 条`;
}

/** 扫描入库结果行：created/skipped 与规则名。 */
export function stalenessScanText(out: StalenessScanOut): string {
  return `已入库 ${out.created} 条（跳过重复 ${out.skipped} 条）· 规则 ${out.rule_name}`;
}
