import { describe, expect, it } from "vitest";
import {
  formatChain,
  formatNominal,
  formatPropagationLevel,
  isClosedRing,
  riskFlagLabel,
} from "./riskDisplay";

describe("riskDisplay", () => {
  it("链条格式化与环闭合判定", () => {
    expect(formatChain(["甲", "乙", "丙"])).toBe("甲 → 乙 → 丙");
    expect(isClosedRing(["甲", "乙", "丙", "甲"])).toBe(true);
    expect(isClosedRing(["甲", "乙", "丙"])).toBe(false);
    expect(isClosedRing(["甲"])).toBe(false);
  });

  it("金额口径：齐备给合计，缺失显式计数不补值", () => {
    expect(formatNominal(800, 0)).toBe("800 万元");
    expect(formatNominal(18000, 0)).toBe("1.8 亿");
    expect(formatNominal(null, 1)).toBe("金额未知（缺 1 段）");
    expect(formatNominal(null, 2)).toBe("金额未知（缺 2 段）");
    expect(formatNominal(null, 0)).toBe("金额未知");
  });

  it("传导层与标记标签文案", () => {
    expect(formatPropagationLevel(2, ["甲", "乙"], "800 万元")).toBe(
      "第 2 层：甲、乙（800 万元）",
    );
    expect(riskFlagLabel("guarantee_cycle")).toBe("互保圈");
    expect(riskFlagLabel("guarantee_chain_exposure")).toBe("担保传导受累");
    expect(riskFlagLabel("unknown_kind")).toBe("unknown_kind");
  });
});
