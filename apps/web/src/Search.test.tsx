import { render, screen } from "@testing-library/react";
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
