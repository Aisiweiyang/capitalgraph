/** AuthProvider 单测：初始态、登录/登出、角色门、坏 token 与 Provider 外调用。 */
import { act, render, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./auth";

function fakeJwt(sub: string, role: string): string {
  const b64 = (obj: object) => btoa(JSON.stringify(obj)).replace(/=+$/, "");
  return `${b64({ alg: "HS256" })}.${b64({ sub, role })}.sig`;
}

function probe() {
  const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider });
  return result;
}

beforeEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

afterEach(() => {
  localStorage.clear();
});

describe("AuthProvider", () => {
  it("无 token：匿名态，任何角色都不通过", () => {
    const r = probe();
    expect(r.current.username).toBeNull();
    expect(r.current.role).toBeNull();
    expect(r.current.hasRole("viewer")).toBe(false);
  });

  it("预置合法 viewer token：恢复登录态且角色门生效", () => {
    localStorage.setItem("cg_token", fakeJwt("viewer", "viewer"));
    const r = probe();
    expect(r.current.username).toBe("viewer");
    expect(r.current.role).toBe("viewer");
    expect(r.current.hasRole("viewer")).toBe(true);
    expect(r.current.hasRole("analyst")).toBe(false);
    expect(r.current.hasRole("admin")).toBe(false);
  });

  it("预置 analyst token：满足 analyst 及以下角色", () => {
    localStorage.setItem("cg_token", fakeJwt("a1", "analyst"));
    const r = probe();
    expect(r.current.hasRole("viewer")).toBe(true);
    expect(r.current.hasRole("analyst")).toBe(true);
    expect(r.current.hasRole("admin")).toBe(false);
  });

  it("坏 token：按匿名处理不崩溃", () => {
    localStorage.setItem("cg_token", "not-a-jwt");
    const r = probe();
    expect(r.current.role).toBeNull();
    expect(r.current.hasRole("viewer")).toBe(false);
  });

  it("login 成功：写入 token 并更新状态", async () => {
    const { api } = await import("./api");
    vi.spyOn(api, "login").mockResolvedValue({
      access_token: fakeJwt("newcomer", "analyst"),
      role: "analyst",
      username: "newcomer",
    });
    const r = probe();
    await act(async () => {
      await r.current.login("newcomer", "pw");
    });
    expect(localStorage.getItem("cg_token")).toBe(fakeJwt("newcomer", "analyst"));
    expect(r.current.username).toBe("newcomer");
    expect(r.current.role).toBe("analyst");
  });

  it("login 失败：状态与 token 保持原样", async () => {
    localStorage.setItem("cg_token", fakeJwt("viewer", "viewer"));
    const { api } = await import("./api");
    vi.spyOn(api, "login").mockRejectedValue(new Error("请求失败 (401)"));
    const r = probe();
    await act(async () => {
      await expect(r.current.login("x", "y")).rejects.toThrow("请求失败 (401)");
    });
    expect(r.current.username).toBe("viewer");
    expect(localStorage.getItem("cg_token")).toBe(fakeJwt("viewer", "viewer"));
  });

  it("logout：清空状态与 token", () => {
    localStorage.setItem("cg_token", fakeJwt("viewer", "viewer"));
    const r = probe();
    act(() => {
      r.current.logout();
    });
    expect(localStorage.getItem("cg_token")).toBeNull();
    expect(r.current.username).toBeNull();
    expect(r.current.hasRole("viewer")).toBe(false);
  });

  it("Provider 外调用 useAuth 抛出明确错误", () => {
      const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    function Broken() {
      useAuth();
      return null;
    }
    expect(() => render(<Broken />)).toThrow(/AuthProvider/);
    spy.mockRestore();
  });
});
