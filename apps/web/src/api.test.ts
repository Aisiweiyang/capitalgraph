/** API 客户端（request/鉴权头/错误分支）单测：mock 全局 fetch，不打真实后端。 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, getToken, setToken } from "./api";

const mockFetch = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", mockFetch);
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  localStorage.clear();
});

function jsonResp(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("request 请求层", () => {
  it("成功：POST JSON、携带 localStorage 中的鉴权头并解析响应", async () => {
    setToken("tok-123");
    mockFetch.mockResolvedValueOnce(jsonResp(200, { access_token: "x", role: "viewer" }));

    const out = await api.login("viewer", "pw");

    expect(out.access_token).toBe("x");
    const [, init] = mockFetch.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    const headers = init.headers as Headers;
    expect(headers.get("Authorization")).toBe("Bearer tok-123");
    expect(headers.get("Content-Type")).toBe("application/json");
  });

  it("401：清除本地 token 并抛出登录提示", async () => {
    setToken("stale-token");
    mockFetch.mockResolvedValueOnce(jsonResp(401, { detail: "x" }));

    await expect(api.stats()).rejects.toSatisfy(
      (e: ApiError) => e instanceof ApiError && e.status === 401 && e.message === "请先登录",
    );
    expect(getToken()).toBeNull();
  });

  it("非 2xx：错误消息取响应体 detail", async () => {
    mockFetch.mockResolvedValueOnce(jsonResp(422, { detail: "years 须在 1..30" }));

    await expect(api.evidenceStaleness({ years: 99 })).rejects.toSatisfy(
      (e: ApiError) => e.status === 422 && e.message === "years 须在 1..30",
    );
  });

  it("非 JSON 错误体：回退默认消息", async () => {
    mockFetch.mockResolvedValueOnce(new Response("server exploded", { status: 500 }));

    await expect(api.stats()).rejects.toSatisfy(
      (e: ApiError) => e.status === 500 && e.message.includes("请求失败 (500)"),
    );
  });
});

describe("token 存取", () => {
  it("setToken(null) 清除且 getToken 返回空", () => {
    setToken("a");
    expect(getToken()).toBe("a");
    setToken(null);
    expect(getToken()).toBeNull();
  });
});
