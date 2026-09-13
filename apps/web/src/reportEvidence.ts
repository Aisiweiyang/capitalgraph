/** 报告证据引用的异步收集（页面点击导出时调用；报告模块本体保持纯函数）。
 *
 * v0.5.1：/evidence/lookup 单次上限 200 条声明，这里按批切分调用并合并结果，
 * 使报告证据表可覆盖至 MAX_REPORT_EVIDENCE 条；任一批失败整体降级为
 * "无证据表"（不阻断报告导出，维持 v0.5 语义）。
 */

import { api, type EvidenceFragment } from "./api";
import { buildReportEvidence, type ReportEvidence } from "./report";

/** 与后端 /evidence/lookup 单次上限一致（routers/evidence.py _LOOKUP_LIMIT）。 */
export const EVIDENCE_LOOKUP_CHUNK = 200;
/** 报告证据表总量上限：超出部分不收集（超大规模报告请分批导出）。 */
export const MAX_REPORT_EVIDENCE = 1000;

/** 把声明 ID 列表按 size 切批（保持顺序，末批可短）。 */
export function chunkIds(ids: string[], size: number = EVIDENCE_LOOKUP_CHUNK): string[][] {
  const chunks: string[][] = [];
  for (let i = 0; i < ids.length; i += size) {
    chunks.push(ids.slice(i, i + size));
  }
  return chunks;
}

/** 汇总声明的证据并组装引用表；失败时返回 undefined（报告不附证据表，不阻断导出）。 */
export async function collectReportEvidence(
  statementIds: string[],
): Promise<ReportEvidence | undefined> {
  const unique = [...new Set(statementIds)].slice(0, MAX_REPORT_EVIDENCE);
  if (unique.length === 0) return undefined;
  const merged: Record<string, EvidenceFragment[]> = {};
  try {
    for (const chunk of chunkIds(unique)) {
      const out = await api.evidenceLookup(chunk);
      Object.assign(merged, out.evidence);
    }
  } catch {
    return undefined;
  }
  return buildReportEvidence(unique, merged);
}
