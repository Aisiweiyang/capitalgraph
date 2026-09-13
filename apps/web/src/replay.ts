/** 按年回放纯逻辑：帧索引、年末口径、串行预取 + 节流渲染（可单测，无 React 依赖）。

请求预算 = 年份数 × 2 个请求（/flows/summary 与 /flows/regions 各一）；
abort 后立即静默停止，不抛错（取消是正常路径，见 ADR-016 口径）。
 */

import type { FlowsSummaryOut, RegionFlowRow, TimelineRow } from "./api";

export interface ReplayFrame {
  year: number;
  summary: FlowsSummaryOut;
  flows: RegionFlowRow[];
}

/** 帧索引：timeline 出现过的年份去重升序。 */
export function replayYears(timeline: TimelineRow[]): number[] {
  return [...new Set(timeline.map((t) => t.year))].sort((a, b) => a - b);
}

/** 年份 → 年末日期（回放帧的 at 口径：时点过滤左闭右开，年末含全年声明）。 */
export function yearEndIso(year: number): string {
  return `${year}-12-31`;
}

export interface ReplayOptions {
  years: number[];
  fetchFrame: (year: number, signal: AbortSignal) => Promise<ReplayFrame>;
  onFrame: (frame: ReplayFrame) => void;
  intervalMs?: number;
  signal: AbortSignal;
}

/** 串行预取 + 节流渲染：取一帧、渲染一帧、等待间隔；abort 即停。 */
export async function runReplay(opts: ReplayOptions): Promise<void> {
  const intervalMs = opts.intervalMs ?? 600;
  for (const year of opts.years) {
    if (opts.signal.aborted) return;
    const frame = await opts.fetchFrame(year, opts.signal);
    if (opts.signal.aborted) return; // 帧取到但已取消：不渲染过期帧
    opts.onFrame(frame);
    await delay(intervalMs, opts.signal);
  }
}

function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    const onAbort = () => {
      clearTimeout(timer);
      resolve();
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}
