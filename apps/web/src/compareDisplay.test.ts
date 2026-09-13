import { describe, expect, it } from "vitest";
import type { FamiliesCompareOut, FlowsCompareOut } from "./api";
import { familyCompareRows, flowsMetricRows } from "./compareDisplay";

function familiesCmp(partial: Partial<FamiliesCompareOut>): FamiliesCompareOut {
  return {
    from: "2022-01-01",
    to: "2023-01-01",
    min_control_ratio_percent: 50,
    algorithm_version: "cg-compare/1.0.0",
    family_count: { before: 1, after: 2, delta: 1 },
    added_families: [{ family_id: "p2", family_name: "李四", member_count: 3 }],
    removed_families: [{ family_id: "p0", family_name: "王五", member_count: 2 }],
    changed: [
      {
        family_id: "p1",
        family_name: "张三",
        controllers_added: [],
        controllers_removed: [],
        members_added: ["c9"],
        members_removed: ["c1", "c2"],
        members_added_names: ["丙公司"],
        members_removed_names: ["甲公司", "乙公司"],
        member_count_before: 3,
        member_count_after: 2,
        region_coverage_before: 1,
        region_coverage_after: 2,
        cycle_count_before: 0,
        cycle_count_after: 1,
      },
    ],
    unchanged_count: 0,
    unassigned_entity_count: { before: 0, after: 0, delta: 0 },
    assumptions: [],
    ...partial,
  } as FamiliesCompareOut;
}

describe("familyCompareRows", () => {
  it("族出现/消失/变化分行输出，变化行含成员增减明细", () => {
    const rows = familyCompareRows(familiesCmp({}));
    expect(rows).toHaveLength(3);
    expect(rows[0]).toEqual({ kind: "added", label: "族出现：李四", detail: "成员 3" });
    const changed = rows.find((r) => r.kind === "changed");
    expect(changed?.label).toBe("族变化：张三");
    expect(changed?.detail).toContain("新增成员 丙公司");
    expect(changed?.detail).toContain("移除成员 甲公司、乙公司");
    expect(changed?.detail).toContain("环路 0→1");
  });

  it("无变化时为空数组", () => {
    const rows = familyCompareRows(
      familiesCmp({ added_families: [], removed_families: [], changed: [] }),
    );
    expect(rows).toEqual([]);
  });
});

describe("flowsMetricRows", () => {
  const base = {
    from: "2022-01-01",
    to: "2023-01-01",
    algorithm_version: "cg-compare/1.0.0",
    flows_added: [{}],
    flows_removed: [{}, {}],
    flows_changed: [{}],
    flow_pair_delta_check: true,
    assumptions: [],
  } as unknown as FlowsCompareOut;

  it("总量三指标 before/after/delta 与流向对统计", () => {
    const cmp = {
      ...base,
      totals: {
        flow_count: { before: 5, after: 4, delta: -1 },
        total_cross_amount_wan: { before: 8000, after: 9000.5, delta: 1000.5 },
        hhi: { before: 8000, after: 9000, delta: 1000 },
      },
    } as unknown as FlowsCompareOut;
    const rows = flowsMetricRows(cmp);
    expect(rows[0]).toEqual({
      label: "省际流向条数",
      before: "5",
      after: "4",
      delta: "-1",
      deltaSign: "negative",
    });
    expect(rows[1].delta).toBe("+1,000.5");
    expect(rows[2].deltaSign).toBe("positive");
    expect(rows[3].delta).toBe("1 / 2 / 1");
  });

  it("HHI 缺失时差值显式为 —（unknown）", () => {
    const cmp = {
      ...base,
      totals: {
        flow_count: { before: 0, after: 2, delta: 2 },
        total_cross_amount_wan: { before: 0, after: 100, delta: 100 },
        hhi: { before: null, after: 10000, delta: null },
      },
    } as unknown as FlowsCompareOut;
    const rows = flowsMetricRows(cmp);
    expect(rows[2].before).toBe("—");
    expect(rows[2].delta).toBe("—");
    expect(rows[2].deltaSign).toBe("unknown");
  });
});
