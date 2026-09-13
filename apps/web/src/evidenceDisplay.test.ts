import { describe, expect, it } from "vitest";
import type { EvidenceCoverageOut } from "./api";
import { coverageHeadline } from "./evidenceDisplay";

function out(partial: Partial<EvidenceCoverageOut>): EvidenceCoverageOut {
  return {
    at: null,
    algorithm_version: "cg-evidence-coverage/1.0.0",
    total_active_statements: 4,
    covered_statements: 3,
    missing_statements: 1,
    coverage_percent: 75,
    by_predicate: [],
    by_connector: [],
    by_year: [],
    missing_sample_size: 1,
    missing_samples: [],
    assumptions: [],
    ...partial,
  } as EvidenceCoverageOut;
}

describe("coverageHeadline", () => {
  it("全量覆盖：百分比取整展示，无薄弱分组", () => {
    const h = coverageHeadline(out({ coverage_percent: 100, missing_statements: 0 }));
    expect(h.percentText).toBe("100%");
    expect(h.missingText).toBe("0");
    expect(h.weakest).toBeNull();
  });

  it("存在缺失时按谓词找出覆盖率最低的分组", () => {
    const h = coverageHeadline(
      out({
        coverage_percent: 75,
        by_predicate: [
          { key: "holds_shares", total: 2, covered: 1, missing: 1, coverage_percent: 50 },
          { key: "controls", total: 2, covered: 2, missing: 0, coverage_percent: 100 },
        ],
      }),
    );
    expect(h.percentText).toBe("75%");
    expect(h.weakest?.label).toBe("holds_shares");
    expect(h.weakest?.group.missing).toBe(1);
  });

  it("空库：百分比为 —", () => {
    const h = coverageHeadline(
      out({ total_active_statements: 0, covered_statements: 0, coverage_percent: null }),
    );
    expect(h.percentText).toBe("—");
    expect(h.totalText).toBe("0");
  });
});
