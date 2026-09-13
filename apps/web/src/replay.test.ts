import { describe, expect, it, vi } from "vitest";
import { replayYears, runReplay, yearEndIso, type ReplayFrame } from "./replay";

function frameOf(year: number): ReplayFrame {
  return { year, summary: { at: String(year) } as never, flows: [] };
}

describe("replay 纯逻辑", () => {
  it("帧索引：年份去重升序", () => {
    expect(
      replayYears([
        { year: 2021, edge_count: 1, amount_wan: 1, amount_missing_edges: 0 },
        { year: 2018, edge_count: 1, amount_wan: 1, amount_missing_edges: 0 },
        { year: 2021, edge_count: 1, amount_wan: 1, amount_missing_edges: 0 },
      ]),
    ).toEqual([2018, 2021]);
  });

  it("年末日期口径", () => {
    expect(yearEndIso(2020)).toBe("2020-12-31");
  });

  it("串行预取 + 节流渲染：取一帧渲染一帧", async () => {
    vi.useFakeTimers();
    const calls: number[] = [];
    const rendered: number[] = [];
    const controller = new AbortController();
    const done = runReplay({
      years: [2018, 2019, 2020],
      fetchFrame: async (year) => {
        calls.push(year);
        return frameOf(year);
      },
      onFrame: (f) => rendered.push(f.year),
      intervalMs: 100,
      signal: controller.signal,
    });
    await vi.advanceTimersByTimeAsync(0);
    expect(calls).toEqual([2018]); // 串行：第一帧取完才取第二帧
    expect(rendered).toEqual([2018]);
    await vi.advanceTimersByTimeAsync(100);
    expect(calls).toEqual([2018, 2019]);
    await vi.advanceTimersByTimeAsync(300);
    await done;
    expect(calls).toEqual([2018, 2019, 2020]);
    expect(rendered).toEqual([2018, 2019, 2020]);
    vi.useRealTimers();
  });

  it("abort 后静默停止，不渲染过期帧", async () => {
    const calls: number[] = [];
    const rendered: number[] = [];
    const controller = new AbortController();
    const done = runReplay({
      years: [2018, 2019, 2020, 2021],
      fetchFrame: async (year) => {
        calls.push(year);
        if (year === 2019) controller.abort(); // 第二帧到手时取消
        return frameOf(year);
      },
      onFrame: (f) => rendered.push(f.year),
      intervalMs: 5,
      signal: controller.signal,
    });
    await done;
    expect(calls).toEqual([2018, 2019]);
    expect(rendered).toEqual([2018]); // 已取消：2019 帧不渲染
  });
});
