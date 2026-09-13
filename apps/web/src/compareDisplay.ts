/** 格局对比的展示口径（纯函数，供系谱页/流动页对比模式复用与单测）。 */

import type { FamiliesCompareOut, FlowsCompareOut } from "./api";

export interface CompareRow {
  kind: "added" | "removed" | "changed";
  label: string;
  detail: string;
}

/** 系族对比 → 展示行（新增/消失/变化，全部列出）。 */
export function familyCompareRows(cmp: FamiliesCompareOut): CompareRow[] {
  const rows: CompareRow[] = [];
  for (const f of cmp.added_families) {
    rows.push({
      kind: "added",
      label: `族出现：${f.family_name}`,
      detail: `成员 ${f.member_count ?? "?"}`,
    });
  }
  for (const f of cmp.removed_families) {
    rows.push({
      kind: "removed",
      label: `族消失：${f.family_name}`,
      detail: `原成员 ${f.member_count ?? "?"}`,
    });
  }
  for (const c of cmp.changed) {
    const parts: string[] = [];
    if (c.members_added.length) parts.push(`新增成员 ${c.members_added_names.join("、")}`);
    if (c.members_removed.length) parts.push(`移除成员 ${c.members_removed_names.join("、")}`);
    if (c.controllers_added.length) parts.push(`控制人 +${c.controllers_added.length}`);
    if (c.controllers_removed.length) parts.push(`控制人 -${c.controllers_removed.length}`);
    if (c.cycle_count_before !== c.cycle_count_after)
      parts.push(`环路 ${c.cycle_count_before}→${c.cycle_count_after}`);
    if (c.path_changed?.length) {
      const detail =
        c.path_changed_detail ??
        c.path_changed.map((p) => ({
          member_name: p.member,
          controller_before_name: p.controller_before,
          controller_after_name: p.controller_after,
        }));
      parts.push(
        detail
          .map((p) => `${p.member_name}: ${p.controller_before_name} → ${p.controller_after_name}`)
          .join("；"),
      );
    }
    rows.push({
      kind: "changed",
      label: `族变化：${c.family_name}`,
      detail: parts.join("；") || "结构变化",
    });
  }
  return rows;
}

export interface MetricRow {
  label: string;
  before: string;
  after: string;
  delta: string;
  deltaSign: "positive" | "negative" | "zero" | "unknown";
}

function deltaInfo(delta: number | null): { text: string; sign: MetricRow["deltaSign"] } {
  if (delta == null) return { text: "—", sign: "unknown" };
  if (delta === 0) return { text: "0", sign: "zero" };
  return { text: `${delta > 0 ? "+" : ""}${delta.toLocaleString("zh-CN")}`, sign: delta > 0 ? "positive" : "negative" };
}

/** 区域流动对比 → 指标行（总量三指标 + 变化流向对数）。 */
export function flowsMetricRows(cmp: FlowsCompareOut): MetricRow[] {
  const fmt = (v: number | null | undefined) =>
    v == null ? "—" : Number(v).toLocaleString("zh-CN");
  const amountDelta = deltaInfo(
    cmp.totals.total_cross_amount_wan.delta == null
      ? null
      : cmp.totals.total_cross_amount_wan.delta,
  );
  const hhiDelta = deltaInfo(cmp.totals.hhi.delta);
  const flowDelta = deltaInfo(cmp.totals.flow_count.delta);
  return [
    {
      label: "省际流向条数",
      before: fmt(cmp.totals.flow_count.before),
      after: fmt(cmp.totals.flow_count.after),
      delta: flowDelta.text,
      deltaSign: flowDelta.sign,
    },
    {
      label: "跨省金额（万元）",
      before: fmt(cmp.totals.total_cross_amount_wan.before),
      after: fmt(cmp.totals.total_cross_amount_wan.after),
      delta: amountDelta.text,
      deltaSign: amountDelta.sign,
    },
    {
      label: "流出集中度 HHI",
      before: fmt(cmp.totals.hhi.before),
      after: fmt(cmp.totals.hhi.after),
      delta: hhiDelta.text,
      deltaSign: hhiDelta.sign,
    },
    {
      label: "新增/消失/变化流向对",
      before: "—",
      after: "—",
      delta: `${cmp.flows_added.length} / ${cmp.flows_removed.length} / ${cmp.flows_changed.length}`,
      deltaSign: "zero",
    },
  ];
}
