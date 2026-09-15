/** 研究快照导出：把当前研究上下文组装为自包含 HTML 报告（纯前端，零后端依赖）。

- 内联 CSS；图表以 dataURL（ECharts getDataURL / Cytoscape png）内嵌；
- 含数据口径（时点 at、阈值、算法版本）与免责声明；
- 所有文本经 HTML 转义，图表仅接受 data:image 前缀，杜绝注入。
 */

import type {
  EvidenceFragment,
  FamilyDetail,
  FamiliesCompareOut,
  FlowsCompareOut,
  FlowsSummaryOut,
  PenetrationResult,
  RegionFlowRow,
} from "./api";

export type ReportContext =
  | { kind: "penetration"; title: string; data: PenetrationResult }
  | { kind: "family"; title: string; data: FamilyDetail }
  | { kind: "flows"; title: string; data: FlowsSummaryOut; flows: RegionFlowRow[] }
  | { kind: "families_compare"; title: string; data: FamiliesCompareOut }
  | { kind: "flows_compare"; title: string; data: FlowsCompareOut };

export interface ReportOptions {
  generatedAt: string;
  chartPng?: string | null;
  at?: string | null;
  minRatioPercent?: string | null;
  /** 证据引用（v0.5 切片 C）：编号上标 + 报告尾部证据引用表。 */
  evidence?: ReportEvidence;
  /** 覆盖率摘要（v0.6 切片 C）：导出时并行获取，失败降级不显示。 */
  coverageSummary?: CoverageSummary;
}

export interface CoverageSummary {
  coverage_percent: number | null;
  total_active_statements: number;
  missing_statements: number;
}

/** 证据快照取证时间是否早于时点 − years 年（与 /evidence/staleness 同口径，ADR-020）。
 * 恰好等于阈值不算陈旧；缺快照时间或时间不可解析时不定性。 */
export function staleCapturedAt(
  capturedAt: string | null | undefined,
  at: string | null | undefined,
  years = 5,
): boolean {
  if (!capturedAt) return false;
  const captured = new Date(capturedAt).getTime();
  if (Number.isNaN(captured)) return false;
  const asOf = at ? new Date(`${at}T00:00:00Z`).getTime() : Date.now();
  if (Number.isNaN(asOf)) return false;
  const cutoff = new Date(asOf);
  cutoff.setUTCFullYear(cutoff.getUTCFullYear() - years);
  return captured < cutoff.getTime();
}

export interface ReportEvidenceEntry {
  no: number;
  statement_id: string;
  document_title: string;
  field_path: string;
  content_sha256: string;
  captured_at: string | null;
  stale: boolean;
  source_url: string;
}

export interface ReportEvidence {
  entries: ReportEvidenceEntry[];
  /** statement_id → 编号（出现顺序，从 1 起）。 */
  refByStatement: Record<string, number>;
  /** 判定陈旧用的阈值（年），供表格标注展示。 */
  stale_years: number;
}

/** 由证据反查结果组装报告证据引用（编号 = 首次出现顺序，确定性）。
 * v0.6：附快照取证时间与陈旧标记（阈值与证据工作台同参数）。 */
export function buildReportEvidence(
  statementIds: string[],
  evidence: Record<string, EvidenceFragment[]>,
  opts: { at?: string | null; years?: number } = {},
): ReportEvidence {
  const years = opts.years ?? 5;
  const refByStatement: Record<string, number> = {};
  const entries: ReportEvidenceEntry[] = [];
  for (const sid of statementIds) {
    if (refByStatement[sid] != null) continue;
    const fragments = evidence[sid] ?? [];
    refByStatement[sid] = entries.length + 1;
    const frag = fragments[0];
    const capturedAt = frag?.fetched_at || null;
    entries.push({
      no: entries.length + 1,
      statement_id: sid,
      document_title: frag?.document_title ?? "（未登记证据片段）",
      field_path: frag?.field_path ?? "—",
      content_sha256: (frag?.content_sha256 ?? "").slice(0, 12),
      captured_at: capturedAt,
      stale: staleCapturedAt(capturedAt, opts.at, years),
      source_url: frag?.source_url ?? "",
    });
  }
  return { entries, refByStatement, stale_years: years };
}

/** 行内证据编号上标：<sup>[1,3]</sup>；无引用时为空串。 */
export function evidenceSup(
  statementIds: readonly string[] | undefined,
  refByStatement: Record<string, number> | undefined,
): string {
  if (!statementIds || !refByStatement) return "";
  const nos = [
    ...new Set(
      statementIds
        .map((sid) => refByStatement[sid])
        .filter((n): n is number => n != null),
    ),
  ].sort((a, b) => a - b);
  if (nos.length === 0) return "";
  return `<sup>[${nos.join(",")}]</sup>`;
}

export const REPORT_DISCLAIMER =
  "本报告为算法候选结果，仅供研究参考，不构成法律认定、信用结论或投资建议。";

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function esc(value: string | number | null | undefined): string {
  return escapeHtml(value == null ? "—" : String(value));
}

type Cell = string | number | null | { html: string };

function renderCell(cell: Cell): string {
  if (cell != null && typeof cell === "object" && "html" in cell) return cell.html;
  return esc(cell);
}

function table(headers: string[], rows: Cell[][]): string {
  return [
    "<table>",
    "<thead><tr>",
    ...headers.map((h) => `<th>${esc(h)}</th>`),
    "</tr></thead><tbody>",
    ...rows.map(
      (row) => "<tr>" + row.map((cell) => `<td>${renderCell(cell)}</td>`).join("") + "</tr>",
    ),
    "</tbody></table>",
  ].join("");
}

function metaRow(label: string, value: string): string {
  return `<div class="meta"><span class="meta-label">${esc(label)}</span>${esc(value)}</div>`;
}

function coverageSummaryText(c: CoverageSummary): string {
  const pct = c.coverage_percent != null ? `${c.coverage_percent}%` : "—";
  return `${pct}（有效声明 ${c.total_active_statements} · 缺失 ${c.missing_statements}）`;
}

function chartImage(chartPng: string | null | undefined): string {
  if (!chartPng || !chartPng.startsWith("data:image/")) return "";
  return `<img class="chart" alt="图表" src="${chartPng}" />`;
}

function sections(ctx: ReportContext, opts: ReportOptions): string {
  const refs = opts.evidence?.refByStatement;
  if (ctx.kind === "penetration") {
    const d = ctx.data;
    return [
      "<h2>UBO 候选</h2>",
      table(
        ["主体", "类型", "有效权益%", "表决权%", "依据数", "证据"],
        d.ubo_candidates.map((u) => [
          d.names[u.entity_id] ?? u.entity_id,
          u.entity_kind ?? "—",
          u.effective_percent,
          u.voting_percent,
          u.basis.length,
          { html: evidenceSup(u.statement_ids, refs) },
        ]),
      ),
      "<h2>股东聚合</h2>",
      table(
        ["主体", "有效权益%", "直接持股%", "路径数", "比例缺失", "证据"],
        d.aggregates.map((a) => [
          d.names[a.entity_id] ?? a.entity_id,
          a.effective_percent,
          a.direct_percent,
          a.path_count,
          a.unknown_ratio ? "是" : "否",
          { html: evidenceSup(a.statement_ids, refs) },
        ]),
      ),
      d.cycles.length
        ? `<h2>环路（${d.cycles.length}）</h2><ul>${d.cycles
            .map(
              (c) =>
                `<li>${esc(c.map((n) => d.names[n] ?? n).join(" → "))}</li>`,
            )
            .join("")}</ul>`
        : "",
      "<h2>算法假设</h2>",
      `<ul>${d.assumptions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>`,
    ].join("");
  }
  if (ctx.kind === "family") {
    const d = ctx.data;
    return [
      `<h2>系族概况</h2>`,
      table(
        ["控制人", "成员数", "覆盖省份", "族内环路", "持股密度"],
        [
          [
            d.controller_names.join("、"),
            d.member_count,
            d.region_coverage,
            d.cycle_count,
            d.density,
          ],
        ],
      ),
      "<h2>成员与被控路径</h2>",
      table(
        ["成员", "类型", "被控路径", "区域", "证据"],
        d.members.map((m) => [
          m.name,
          m.kind ?? "—",
          m.path_names.join(" → "),
          m.region_code ?? "未知",
          { html: evidenceSup(m.statement_ids, refs) },
        ]),
      ),
      "<h2>算法假设</h2>",
      `<ul>${d.assumptions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>`,
    ].join("");
  }
  if (ctx.kind === "families_compare") {
    const d = ctx.data;
    const changedRows = d.changed.map((c) => [
      c.family_name,
      `${c.member_count_before} → ${c.member_count_after}`,
      c.members_added_names.join("、") || "—",
      c.members_removed_names.join("、") || "—",
      `${c.cycle_count_before} → ${c.cycle_count_after}`,
    ]);
    return [
      `<h2>族总数：${d.family_count.before} → ${d.family_count.after}（未变化 ${d.unchanged_count}）</h2>`,
      "<h2>族出现</h2>",
      table(
        ["族（控制人）", "成员数"],
        d.added_families.map((f) => [f.family_name, f.member_count ?? "—"]),
      ),
      "<h2>族消失</h2>",
      table(
        ["族（控制人）", "原成员数"],
        d.removed_families.map((f) => [f.family_name, f.member_count ?? "—"]),
      ),
      "<h2>族变化</h2>",
      changedRows.length
        ? table(["族", "成员数", "新增成员", "移除成员", "环路数"], changedRows)
        : "<p>无</p>",
      "<h2>口径说明</h2>",
      `<ul>${d.assumptions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>`,
    ].join("");
  }
  if (ctx.kind === "flows_compare") {
    const d = ctx.data;
    const fmt = (v: number | null | undefined) => (v == null ? "—" : String(v));
    const pair = (p: {
      from_region: string;
      to_region: string;
      edge_count_before?: number;
      edge_count_after?: number;
      edge_count?: number;
      amount_before_wan?: number | null;
      amount_after_wan?: number | null;
      amount_wan?: number | null;
    }) => [
      `${p.from_region} → ${p.to_region}`,
      p.edge_count_before != null
        ? `${p.edge_count_before} → ${p.edge_count_after}`
        : (p.edge_count ?? "—"),
      fmt(p.amount_before_wan != null ? p.amount_before_wan : p.amount_wan),
      fmt(p.amount_after_wan != null ? p.amount_after_wan : p.amount_wan),
    ];
    return [
      "<h2>总量对比</h2>",
      table(
        ["指标", "before", "after", "delta"],
        [
          ["省际流向条数", d.totals.flow_count.before, d.totals.flow_count.after, d.totals.flow_count.delta],
          ["跨省金额（万元）", d.totals.total_cross_amount_wan.before, d.totals.total_cross_amount_wan.after, d.totals.total_cross_amount_wan.delta],
          ["HHI", fmt(d.totals.hhi.before), fmt(d.totals.hhi.after), fmt(d.totals.hhi.delta)],
        ],
      ),
      "<h2>新增流向对</h2>",
      d.flows_added.length ? table(["流向", "笔数", "before金额", "after金额"], d.flows_added.map(pair)) : "<p>无</p>",
      "<h2>消失流向对</h2>",
      d.flows_removed.length ? table(["流向", "笔数", "before金额", "after金额"], d.flows_removed.map(pair)) : "<p>无</p>",
      "<h2>变化流向对</h2>",
      d.flows_changed.length ? table(["流向", "笔数", "before金额", "after金额"], d.flows_changed.map(pair)) : "<p>无</p>",
      "<h2>口径说明</h2>",
      `<ul>${d.assumptions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>`,
    ].join("");
  }
  const s = ctx.data;
  return [
    "<h2>区域汇总</h2>",
    table(
      ["省份", "流入(万元)", "流出(万元)", "净额(万元)", "流出笔数", "流入笔数"],
      s.regions.map((r) => [r.region, r.inflow_wan, r.outflow_wan, r.net_wan, r.outflow_edges, r.inflow_edges]),
    ),
    "<h2>省际流向 TOP</h2>",
    table(
      ["流出省", "流入省", "笔数", "金额(万元)", "比例缺失边"],
      ctx.flows.slice(0, 30).map((f) => [
        f.from_region,
        f.to_region,
        f.edge_count,
        f.amount_wan,
        f.ratio_missing_edges,
      ]),
    ),
    "<h2>口径说明</h2>",
    `<ul>
      <li>流动 = 资本放置类声明（holds_shares / invests_in），controls 不计入；</li>
      <li>跨省判定要求两端 region_code 齐备，缺失边显式计数；</li>
      <li>金额口径 = amount_scaled 求和（万元），缺失金额不计入合计；</li>
      <li>HHI = 各省流出金额份额（百分点）平方和（0..10000）。</li>
    </ul>`,
  ].join("");
}

function evidenceTableSection(evidence: ReportEvidence): string {
  if (evidence.entries.length === 0) return "";
  const staleCount = evidence.entries.filter((e) => e.stale).length;
  return [
    "<h2>证据引用表</h2>",
    staleCount
      ? `<p class="meta">其中 ${staleCount} 条证据快照取证时间早于数据时点 − ${evidence.stale_years} 年，标注为陈旧——只提示、不构成认定。</p>`
      : "",
    table(
      ["编号", "声明 ID", "来源文档", "字段路径", "内容哈希（前 12 位）", "快照时间", "链接"],
      evidence.entries.map((e) => [
        `[${e.no}]`,
        e.statement_id,
        e.document_title,
        e.field_path,
        e.content_sha256 || "—",
        {
          html:
            esc(e.captured_at ? e.captured_at.slice(0, 10) : "—") +
            (e.stale ? ` <span class="stale">陈旧(&gt;${evidence.stale_years} 年)</span>` : ""),
        },
        e.source_url || "—",
      ]),
    ),
  ].join("");
}

export function assembleReportHtml(ctx: ReportContext, opts: ReportOptions): string {
  const algorithmVersion =
    ctx.kind === "flows" ? "cg-flows 聚合（ADR-014 口径）" : ctx.data.algorithm_version;
  const configHash =
    ctx.kind === "penetration" || ctx.kind === "family" ? ctx.data.config_hash : "";
  const title = esc(ctx.title);
  const subtitle =
    ctx.kind === "penetration"
      ? `根主体：${esc(ctx.data.entity_name)} · 方向：${ctx.data.direction === "up" ? "向上穿透" : "向下穿透"}`
      : ctx.kind === "family"
        ? `族 ID：${esc(ctx.data.family_id)} · 控制阈值：${esc(opts.minRatioPercent ?? ctx.data.min_control_ratio_percent)}%`
        : ctx.kind === "families_compare"
          ? `对比窗口：${esc(ctx.data.from)} → ${esc(ctx.data.to)} · 控制阈值 ${esc(ctx.data.min_control_ratio_percent)}%`
          : ctx.kind === "flows_compare"
            ? `对比窗口：${esc(ctx.data.from)} → ${esc(ctx.data.to)} · 跨省金额 ${esc(ctx.data.totals.total_cross_amount_wan.before)} → ${esc(ctx.data.totals.total_cross_amount_wan.after)} 万元`
            : `覆盖省份：${ctx.data.regions.length} · 省际流向：${ctx.data.flow_count}`;
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>${title}</title>
<style>
  body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; color: #1c2430; margin: 32px auto; max-width: 960px; }
  h1 { font-size: 22px; border-bottom: 2px solid #1f6feb; padding-bottom: 8px; }
  h2 { font-size: 16px; margin-top: 24px; }
  table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 13px; }
  th, td { border: 1px solid #d5dce6; padding: 5px 8px; text-align: left; }
  th { background: #f0f4fa; }
  .meta { font-size: 12px; color: #4a5568; margin: 2px 0; }
  .meta-label { display: inline-block; min-width: 9em; color: #7a8699; }
  .chart { max-width: 100%; border: 1px solid #d5dce6; margin: 12px 0; }
  .disclaimer { margin-top: 32px; padding: 12px; background: #fff7e8; border: 1px solid #e8a13c; font-size: 13px; }
  footer { margin-top: 16px; font-size: 11px; color: #98a2b3; }
  sup { color: #1f6feb; }
</style>
</head>
<body>
<h1>${title}</h1>
<p>${subtitle}</p>
${metaRow("生成时间", opts.generatedAt)}
${metaRow("数据时点 at", opts.at ?? (ctx.kind === "families_compare" || ctx.kind === "flows_compare" ? `${ctx.data.from} → ${ctx.data.to}` : "当前"))}
${metaRow("控制/比例阈值", opts.minRatioPercent ? `${opts.minRatioPercent}%` : "默认")}
${metaRow("算法版本", algorithmVersion)}
${configHash ? metaRow("配置哈希", configHash) : ""}
${metaRow("数据来源", "确定性合成演示数据（虚构主体）")}
${opts.coverageSummary ? metaRow("证据覆盖率", coverageSummaryText(opts.coverageSummary)) : ""}
${chartImage(opts.chartPng)}
${sections(ctx, opts)}
${opts.evidence ? evidenceTableSection(opts.evidence) : ""}
<div class="disclaimer">${esc(REPORT_DISCLAIMER)}</div>
<footer>CapitalGraph CN 研究快照 · 报告由前端本地生成，未上传任何数据。</footer>
</body>
</html>`;
}

export function downloadReport(filename: string, html: string): void {
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
