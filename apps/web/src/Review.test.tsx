/** Review 页组件测试：质量问题处置按钮调用 resolveQualityIssue 并刷新。 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const reviewItems = vi.fn();
const qualityIssues = vi.fn();
const riskFlags = vi.fn();
const resolveQualityIssue = vi.fn();

vi.mock("./api", () => ({
  api: {
    reviewItems: (...a: unknown[]) => reviewItems(...a),
    qualityIssues: (...a: unknown[]) => qualityIssues(...a),
    riskFlags: (...a: unknown[]) => riskFlags(...a),
    resolveQualityIssue: (...a: unknown[]) => resolveQualityIssue(...a),
    resolveReview: vi.fn(),
  },
}));

vi.mock("./auth", () => ({
  useAuth: () => ({ hasRole: () => true, username: "analyst", role: "analyst" }),
}));

import { ReviewPage } from "./pages/Review";

function mockData() {
  reviewItems.mockResolvedValue([]);
  riskFlags.mockResolvedValue([]);
  qualityIssues.mockResolvedValue([
    {
      id: "q1",
      rule_name: "stale_source",
      severity: "warning",
      entity_id: "e1",
      status: "open",
      detail: { statement_id: "sid-1" },
    },
  ]);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockData();
});

describe("ReviewPage 数据质量问题区", () => {
  it("渲染登记行（规则/严重度/状态）", async () => {
    render(
      <MemoryRouter>
        <ReviewPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("数据质量问题")).toBeTruthy();
    expect(await screen.findByText("stale_source")).toBeTruthy();
    expect(screen.getByText("warning")).toBeTruthy();
    expect(screen.getByText("open")).toBeTruthy();
  });

  it("处置按钮调用 resolveQualityIssue 并刷新", async () => {
    render(
      <MemoryRouter>
        <ReviewPage />
      </MemoryRouter>,
    );
    const btn = await screen.findByRole("button", { name: "标记已处理" });
    fireEvent.click(btn);
    await waitFor(() =>
      expect(resolveQualityIssue).toHaveBeenCalledWith("q1", "已甄别"),
    );
    // 刷新：qualityIssues 被再次拉取
    await waitFor(() => expect(qualityIssues.mock.calls.length).toBeGreaterThanOrEqual(2));
  });

  it("deep-link：detail 内声明 ID 生成证据链接", async () => {
    render(
      <MemoryRouter>
        <ReviewPage />
      </MemoryRouter>,
    );
    const link = await screen.findByRole("link", { name: "证据" });
    expect(link.getAttribute("href")).toBe("/evidence?statements=sid-1");
  });
});
