import { describe, expect, it } from "vitest";
import type { EventItem, EventsOut } from "./api";
import {
  EVENT_TYPE_LABELS,
  eventTone,
  formatDelta,
  formatEventSummary,
  typeChips,
} from "./eventsDisplay";

function ev(partial: Partial<EventItem>): EventItem {
  return {
    event_type: "holding_added",
    event_type_label: EVENT_TYPE_LABELS[partial.event_type ?? "holding_added"] ?? "",
    subject_id: "s1",
    subject_name: "张三",
    object_id: "o1",
    object_name: "某公司",
    predicate: "holds_shares",
    statement_ids: ["p1"],
    prior_statement_ids: [],
    evidence_keys: ["p1"],
    before_percent: null,
    after_percent: null,
    delta_percent: null,
    ratio_comparable: false,
    ...partial,
  };
}

describe("eventsDisplay", () => {
  it("强度口径：新增为正、失效/丧失为负、比例变化为中性", () => {
    expect(eventTone("holding_added")).toBe("positive");
    expect(eventTone("control_gained")).toBe("positive");
    expect(eventTone("holding_removed")).toBe("negative");
    expect(eventTone("control_lost")).toBe("negative");
    expect(eventTone("guarantee_released")).toBe("negative");
    expect(eventTone("holding_ratio_changed")).toBe("neutral");
  });

  it("摘要：比例变化带前后值与差值；缺失比例显式标注不比较", () => {
    const changed = ev({
      event_type: "holding_ratio_changed",
      before_percent: 60,
      after_percent: 50,
      delta_percent: -10,
      ratio_comparable: true,
    });
    expect(formatEventSummary(changed)).toBe("张三 → 某公司 · 60% → 50%（-10%）");
    const unknown = ev({
      event_type: "holding_ratio_changed",
      before_percent: null,
      after_percent: 40,
      delta_percent: null,
      ratio_comparable: false,
    });
    expect(formatEventSummary(unknown)).toContain("比例缺失，不比较");
    const added = ev({ event_type: "holding_added", after_percent: 60 });
    expect(formatEventSummary(added)).toBe("张三 → 某公司 · 持股 60%");
    const removed = ev({ event_type: "holding_removed", before_percent: 60 });
    expect(formatEventSummary(removed)).toBe("张三 → 某公司 · 原持股 60%");
  });

  it("差值格式化：正数带加号，缺失为 —", () => {
    expect(formatDelta(10)).toBe("+10%");
    expect(formatDelta(-0.5)).toBe("-0.5%");
    expect(formatDelta(null)).toBe("—");
  });

  it("筛选 chips 由 counts_by_type 派生并带中文标签", () => {
    const out = {
      counts_by_type: [
        { event_type: "holding_added", label: "holding_added", count: 2 },
        { event_type: "control_lost", label: "control_lost", count: 1 },
      ],
    } as unknown as EventsOut;
    const chips = typeChips(out);
    expect(chips).toEqual([
      { type: "holding_added", label: "持股新增", count: 2 },
      { type: "control_lost", label: "控制权丧失", count: 1 },
    ]);
  });
});
