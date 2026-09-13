/** 变更事件流的展示口径（纯函数，供异动页/实体页变更轨迹复用与单测）。 */

import type { EventItem, EventsOut } from "./api";

export const EVENT_TYPE_LABELS: Record<string, string> = {
  holding_added: "持股新增",
  holding_removed: "持股失效",
  holding_ratio_changed: "持股比例增减",
  control_gained: "控制权获得",
  control_lost: "控制权丧失",
  guarantee_added: "担保新增",
  guarantee_released: "担保解除",
  pledge_added: "质押新增",
  pledge_released: "质押解除",
  statement_added: "声明新增",
  statement_removed: "声明失效",
};

/** 异动强度：新增/获得为正向，失效/丧失为负向，比例变化为中性变动。 */
export function eventTone(type: string): "positive" | "negative" | "neutral" {
  if (type.endsWith("_removed") || type === "control_lost" || type === "guarantee_released")
    return "negative";
  if (type.endsWith("_added") || type === "control_gained") return "positive";
  return "neutral";
}

/** 事件一句话摘要：主体 → 对象 + 比例描述。 */
export function formatEventSummary(ev: EventItem): string {
  const ratio =
    ev.event_type === "holding_ratio_changed"
      ? ev.ratio_comparable
        ? `${ev.before_percent}% → ${ev.after_percent}%（${formatDelta(ev.delta_percent)}）`
        : `${ev.before_percent ?? "?"}% → ${ev.after_percent ?? "?"}%（比例缺失，不比较）`
      : ev.event_type.endsWith("_added") && ev.after_percent != null
        ? `持股 ${ev.after_percent}%`
        : ev.event_type.endsWith("_removed") && ev.before_percent != null
          ? `原持股 ${ev.before_percent}%`
          : "";
  return `${ev.subject_name} → ${ev.object_name}${ratio ? ` · ${ratio}` : ""}`;
}

export function formatDelta(delta: number | null): string {
  if (delta == null) return "—";
  const sign = delta > 0 ? "+" : "";
  return `${sign}${delta}%`;
}

/** 按事件类型筛选（type 为空串/undefined 时返回全部）。 */
export function filterEvents(events: EventItem[], type: string | undefined): EventItem[] {
  if (!type) return events;
  return events.filter((e) => e.event_type === type);
}

/** 时间线分组：按事件类型 → 计数（供筛选条 chips）。 */
export function typeChips(out: EventsOut): { type: string; label: string; count: number }[] {
  return out.counts_by_type.map((c) => ({
    type: c.event_type,
    label: EVENT_TYPE_LABELS[c.event_type] ?? c.label,
    count: c.count,
  }));
}
