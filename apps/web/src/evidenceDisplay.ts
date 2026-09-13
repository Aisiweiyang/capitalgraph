/** 证据工作台的展示口径（纯函数，供覆盖率卡片与单测使用）。 */

import type { CoverageGroup, EvidenceCoverageOut } from "./api";

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
