import { fireEvent, render, screen, act } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { SearchPage, kindLabel } from "./pages/Search";
import { AuthProvider } from "./auth";

describe("kindLabel", () => {
  it("maps entity kinds to Chinese labels", () => {
    expect(kindLabel("person")).toBe("自然人");
    expect(kindLabel("listed_company")).toBe("上市公司");
    expect(kindLabel("government_body")).toBe("政府/国资机构");
  });

  it("falls back to raw kind for unknown values", () => {
    expect(kindLabel("alien")).toBe("alien");
    expect(kindLabel(null)).toBe("未知");
  });
});

describe("SearchPage", () => {
  it("renders empty state and search controls before searching", () => {
    render(
      <AuthProvider>
        <MemoryRouter>
          <SearchPage />
        </MemoryRouter>
      </AuthProvider>,
    );
    expect(screen.getByRole("button", { name: "检索" })).toBeDisabled();
    expect(screen.getByText(/输入关键词开始检索/)).toBeInTheDocument();
  });
});

describe("SearchPage 加载更多", () => {
  it("点击加载更多合并下一页结果并按剩余数收敛", async () => {
    const { api } = await import("./api");
    const spy = vi
      .spyOn(api, "search")
      .mockResolvedValueOnce({
        total: 2,
        hits: [{ id: "a", kind: "company", primary_name: "甲公司", score: 1 }],
      })
      .mockResolvedValueOnce({
        total: 2,
        hits: [{ id: "b", kind: "company", primary_name: "乙公司", score: 0.8 }],
      });

    render(
      <MemoryRouter>
        <SearchPage />
      </MemoryRouter>,
    );
    const input = screen.getByLabelText("检索关键词");
    act(() => {
      fireEvent.change(input, { target: { value: "公司" } });
    });
    fireEvent.submit(screen.getByRole("button", { name: "检索" }).closest("form")!);
    expect(await screen.findByText("甲公司")).toBeTruthy();
    const more = screen.getByTestId("search-load-more");
    expect(more).toHaveTextContent(/剩余 1 条/);

    act(() => {
      fireEvent.click(more);
    });
    expect(await screen.findByText("乙公司")).toBeTruthy();
    expect(screen.queryByTestId("search-load-more")).toBeNull();
    expect(spy).toHaveBeenCalledTimes(2);
  });
});
