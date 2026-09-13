/** 报告证据引用的异步收集（页面点击导出时调用；报告模块本体保持纯函数）。 */

import { api } from "./api";
import { buildReportEvidence, type ReportEvidence } from "./report";

const MAX_EVIDENCE = 200; // lookup 单次上限

/** 汇总声明的证据并组装引用表；失败时返回 undefined（报告不附证据表，不阻断导出）。 */
export async function collectReportEvidence(
  statementIds: string[],
): Promise<ReportEvidence | undefined> {
  const unique = [...new Set(statementIds)].slice(0, MAX_EVIDENCE);
  if (unique.length === 0) return undefined;
  try {
    const out = await api.evidenceLookup(unique);
    return buildReportEvidence(unique, out.evidence);
  } catch {
    return undefined;
  }
}
