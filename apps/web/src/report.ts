/** 研究快照导出：把当前研究上下文组装为自包含 HTML 报告（纯前端，零后端依赖）。

- 内联 CSS；图表以 dataURL（ECharts getDataURL / Cytoscape png）内嵌；
- 含数据口径（时点 at、阈值、算法版本）与免责声明；
- 所有文本经 HTML 转义，图表仅接受 data:image 前缀，杜绝注入。
 */

import type { FamilyDetail, FlowsSummaryOut, PenetrationResult, RegionFlowRow } from "./api";

export type ReportContext =
  | { kind: "penetration"; title: string; data: PenetrationResult }
  | { kind: "family"; title: string; data: FamilyDetail }
  | { kind: "flows"; title: string; data: FlowsSummaryOut; flows: RegionFlowRow[] };

export interface ReportOptions {
  generatedAt: string;
  chartPng?: string | null;
  at?: string | null;
  minRatioPercent?: string | null;
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

function table(headers: string[], rows: (string | number | null)[][]): string {
  return [
    "<table>",
    "<thead><tr>",
    ...headers.map((h) => `<th>${esc(h)}</th>`),
    "</tr></thead><tbody>",
    ...rows.map(
      (row) => "<tr>" + row.map((cell) => `<td>${esc(cell)}</td>`).join("") + "</tr>",
    ),
    "</tbody></table>",
  ].join("");
}

function metaRow(label: string, value: string): string {
  return `<div class="meta"><span class="meta-label">${esc(label)}</span>${esc(value)}</div>`;
}

function chartImage(chartPng: string | null | undefined): string {
  if (!chartPng || !chartPng.startsWith("data:image/")) return "";
  return `<img class="chart" alt="图表" src="${chartPng}" />`;
}

function sections(ctx: ReportContext): string {
  if (ctx.kind === "penetration") {
    const d = ctx.data;
    return [
      "<h2>UBO 候选</h2>",
      table(
        ["主体", "类型", "有效权益%", "表决权%", "依据数"],
        d.ubo_candidates.map((u) => [
          d.names[u.entity_id] ?? u.entity_id,
          u.entity_kind ?? "—",
          u.effective_percent,
          u.voting_percent,
          u.basis.length,
        ]),
      ),
      "<h2>股东聚合</h2>",
      table(
        ["主体", "有效权益%", "直接持股%", "路径数", "比例缺失"],
        d.aggregates.map((a) => [
          d.names[a.entity_id] ?? a.entity_id,
          a.effective_percent,
          a.direct_percent,
          a.path_count,
          a.unknown_ratio ? "是" : "否",
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
        ["成员", "类型", "被控路径", "区域"],
        d.members.map((m) => [
          m.name,
          m.kind ?? "—",
          m.path_names.join(" → "),
          m.region_code ?? "未知",
        ]),
      ),
      "<h2>算法假设</h2>",
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

export function assembleReportHtml(ctx: ReportContext, opts: ReportOptions): string {
  const algorithmVersion =
    ctx.kind === "flows" ? "cg-flows 聚合（ADR-014 口径）" : ctx.data.algorithm_version;
  const configHash = ctx.kind === "flows" ? "" : ctx.data.config_hash;
  const title = esc(ctx.title);
  const subtitle =
    ctx.kind === "penetration"
      ? `根主体：${esc(ctx.data.entity_name)} · 方向：${ctx.data.direction === "up" ? "向上穿透" : "向下穿透"}`
      : ctx.kind === "family"
        ? `族 ID：${esc(ctx.data.family_id)} · 控制阈值：${esc(opts.minRatioPercent ?? ctx.data.min_control_ratio_percent)}%`
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
</style>
</head>
<body>
<h1>${title}</h1>
<p>${subtitle}</p>
${metaRow("生成时间", opts.generatedAt)}
${metaRow("数据时点 at", opts.at ?? "当前")}
${metaRow("控制/比例阈值", opts.minRatioPercent ? `${opts.minRatioPercent}%` : "默认")}
${metaRow("算法版本", algorithmVersion)}
${configHash ? metaRow("配置哈希", configHash) : ""}
${metaRow("数据来源", "确定性合成演示数据（虚构主体）")}
${chartImage(opts.chartPng)}
${sections(ctx)}
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
