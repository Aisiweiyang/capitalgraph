import { beforeEach, describe, expect, it, vi } from "vitest";
import type { EvidenceLookupOut } from "./api";
import { chunkIds, collectReportEvidence, EVIDENCE_LOOKUP_CHUNK } from "./reportEvidence";

const apiMock = vi.hoisted(() => ({ evidenceLookup: vi.fn() }));
vi.mock("./api", () => ({
  api: { evidenceLookup: apiMock.evidenceLookup },
}));

import { api } from "./api";

function lookupOut(ids: string[]): EvidenceLookupOut {
  const evidence: EvidenceLookupOut["evidence"] = {};
  for (const sid of ids) {
    evidence[sid] = [
      {
        fragment_id: `f-${sid}`,
        field_path: `path/${sid}`,
        raw_value: sid,
        normalized_value: sid,
        page_ref: "synthetic",
        content_sha256: "a".repeat(64),
        raw_stored: true,
        source_url: "internal://synthetic",
        document_title: "合成演示数据（虚构）",
      },
    ];
  }
  return { requested: ids.length, found: ids.length, missing_statement_ids: [], evidence };
}

describe("chunkIds", () => {
  it("按 200 切批、保持顺序、末批可短", () => {
    const ids = Array.from({ length: 450 }, (_, i) => `s${i}`);
    const chunks = chunkIds(ids);
    expect(chunks.map((c) => c.length)).toEqual([200, 200, 50]);
    expect(chunks.flat()).toEqual(ids);
  });

  it("空列表不产生批次；自定义 size 生效", () => {
    expect(chunkIds([])).toEqual([]);
    expect(chunkIds(["a", "b", "c"], 2)).toEqual([["a", "b"], ["c"]]);
  });

  it("默认批次大小与服务端上限一致", () => {
    expect(EVIDENCE_LOOKUP_CHUNK).toBe(200);
  });
});

describe("collectReportEvidence", () => {
  beforeEach(() => {
    apiMock.evidenceLookup.mockReset();
  });

  it("跨批合并证据并按首现顺序编号", async () => {
    apiMock.evidenceLookup.mockImplementation((ids: string[]) =>
      Promise.resolve(lookupOut(ids)),
    );
    const ids = ["s1", "s2", "s1", "s3"];
    const out = await collectReportEvidence(ids);
    expect(apiMock.evidenceLookup).toHaveBeenCalledTimes(1); // 去重后仅 3 条
    expect(apiMock.evidenceLookup.mock.calls[0][0]).toEqual(["s1", "s2", "s3"]);
    expect(out?.refByStatement).toEqual({ s1: 1, s2: 2, s3: 3 });
    expect(out?.entries[0].field_path).toBe("path/s1");
  });

  it("超过单批上限时自动分批（250 条 → 2 次调用）", async () => {
    apiMock.evidenceLookup.mockImplementation((ids: string[]) =>
      Promise.resolve(lookupOut(ids)),
    );
    const ids = Array.from({ length: 250 }, (_, i) => `s${i}`);
    const out = await collectReportEvidence(ids);
    expect(apiMock.evidenceLookup).toHaveBeenCalledTimes(2);
    expect(out?.entries).toHaveLength(250);
  });

  it("总量截断至 1000（1500 条输入只收集 1000）", async () => {
    apiMock.evidenceLookup.mockImplementation((ids: string[]) =>
      Promise.resolve(lookupOut(ids)),
    );
    const ids = Array.from({ length: 1500 }, (_, i) => `s${i}`);
    const out = await collectReportEvidence(ids);
    expect(out?.entries).toHaveLength(1000);
    expect(apiMock.evidenceLookup).toHaveBeenCalledTimes(5); // 1000 / 200
  });

  it("任一批失败整体降级为 undefined（不阻断报告导出）", async () => {
    apiMock.evidenceLookup.mockImplementation((ids: string[]) =>
      ids[0] === "s200"
        ? Promise.reject(new Error("500"))
        : Promise.resolve(lookupOut(ids)),
    );
    const ids = Array.from({ length: 400 }, (_, i) => `s${i}`);
    const out = await collectReportEvidence(ids);
    expect(out).toBeUndefined();
  });

  it("空输入不发起请求", async () => {
    expect(await collectReportEvidence([])).toBeUndefined();
    expect(apiMock.evidenceLookup).not.toHaveBeenCalled();
  });

  it("api 引用与 mock 绑定一致（防 mock 失效）", () => {
    expect(api.evidenceLookup).toBe(apiMock.evidenceLookup);
  });
});
