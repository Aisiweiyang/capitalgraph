import { expect, test, type Page } from "@playwright/test";

/**
 * v0.5 端到端补充（切片 D）：系谱页列表→详情、实体页风险传导区、流动页回放、
 * 任一页报告下载、异动页与证据工作台、双时点对比模式、deep-link 证据。
 * 既有 8 项核心链路用例不得回归（core-flow.spec.ts）。
 */

/** 浏览器上下文内调用后端 API（复用 storageState 里的登录 token）。 */
async function apiGet(page: Page, path: string) {
  return page.evaluate(async (p) => {
    const token = localStorage.getItem("cg_token");
    const resp = await fetch(p, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!resp.ok) throw new Error(`GET ${p} -> ${resp.status}`);
    return resp.json();
  }, path);
}

test.describe.serial("CapitalGraph v0.5 页面", () => {
  test("异动页：事件流列表与类型筛选", async ({ page }) => {
    await page.goto("/events");
    await expect(page.locator(".timeline-item").first()).toBeVisible({ timeout: 20000 });
    // 默认窗口（2022-01-01 → 2023-01-01）恰好是合成数据持股转移窗口
    await expect(page.getByTestId("events-list").locator(".timeline-item")).toHaveCount(2);
    // 类型筛选：只留失效事件
    await page.getByTestId("events-type").selectOption("holding_removed");
    await expect(page.getByTestId("events-list").locator(".timeline-item")).toHaveCount(1);
    // 事件上的 deep-link 指向证据工作台
    await expect(
      page.getByTestId("events-list").locator('[data-testid="event-evidence-link"]').first(),
    ).toBeVisible();
    // 回到全部
    await page.getByTestId("events-type").selectOption("");
    await expect(page.getByTestId("events-list").locator(".timeline-item")).toHaveCount(2);
    // 点击事件跳转相关实体：实体页"变更轨迹"区呈现该实体的前后对比摘要
    await page.getByTestId("events-list").locator("a", { hasText: "实体" }).first().click();
    await expect(page.getByRole("heading", { name: /变更轨迹/ })).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("entity-events").locator(".timeline-item")).toHaveCount(2);
  });

  test("资本系谱：列表 → 族详情 → 成员证据 deep-link", async ({ page }) => {
    await page.goto("/families");
    const firstRow = page.locator(".families-layout table tbody tr").first();
    await firstRow.click({ timeout: 20000 });
    await expect(page.getByRole("heading", { name: /族详情/ })).toBeVisible();
    // 族子图渲染
    await expect(page.locator("canvas").first()).toBeVisible({ timeout: 20000 });
    // 成员行携带证据 deep-link，点击打开证据工作台反查结果
    const evidenceLink = page.locator(".family-detail").getByRole("link", { name: "证据" }).first();
    await expect(evidenceLink).toBeVisible();
    await evidenceLink.click();
    await expect(page.getByTestId("evidence-lookup-result")).toBeVisible({ timeout: 15000 });
    await expect(page.locator(".evidence-page h2")).toHaveText(/证据工作台/);
  });

  test("资本系谱对比模式：双时点差异高亮", async ({ page }) => {
    await page.goto("/families");
    await page.getByTestId("families-compare-toggle").click();
    const section = page.getByTestId("families-compare");
    await expect(section).toBeVisible({ timeout: 20000 });
    // 转移窗口内系族格局必有变化
    await expect(section.locator("table.compare-table tr").first()).toBeVisible({
      timeout: 20000,
    });
    await expect(section.getByRole("button", { name: "导出对比报告" })).toBeVisible();
  });

  test("流动页对比模式：总量指标差值", async ({ page }) => {
    await page.goto("/flows");
    await page.getByTestId("flows-compare-toggle").click();
    await expect(page.getByTestId("flows-compare-metrics")).toBeVisible({ timeout: 20000 });
    await expect(
      page.getByTestId("flows-compare-metrics").locator("tr").nth(1),
    ).toContainText("省际流向条数");
  });

  test("流动页按年回放：拖动滑块切换帧年份", async ({ page }) => {
    await page.goto("/flows");
    const slider = page.getByTestId("replay-slider");
    await expect(slider).toBeVisible({ timeout: 20000 });
    const max = Number(await slider.getAttribute("max"));
    expect(max).toBeGreaterThan(0);
    await slider.fill(String(max));
    // 帧年份标签出现（异步取帧）
    await expect(page.getByText(/回放帧：\d{4} 年/)).toBeVisible({ timeout: 20000 });
  });

  test("实体页风险传导区（担保/质押场景）", async ({ page }) => {
    await page.goto("/");
    // 在检索结果中探测存在担保链/质押敞口的实体（合成数据 C1-C7 区域）
    const hits = (await apiGet(
      page,
      "/api/v1/entities/search?q=" + encodeURIComponent("有限公司") + "&limit=100",
    )) as { hits: { id: string }[] };
    expect(hits.hits.length).toBeGreaterThan(0);
    let riskEntity: string | null = null;
    for (const hit of hits.hits) {
      const chains = (await apiGet(page, `/api/v1/risk/chains/${hit.id}`)) as {
        chains: unknown[];
        cycles: unknown[];
        pledges: unknown[];
      };
      if (chains.chains.length + chains.cycles.length + chains.pledges.length > 0) {
        riskEntity = hit.id;
        break;
      }
    }
    expect(riskEntity).not.toBeNull();
    await page.goto(`/entities/${riskEntity}`);
    await expect(page.getByRole("heading", { name: /风险传导/ })).toBeVisible({ timeout: 20000 });
  });

  test("穿透页一键导出研究报告（自包含 HTML）", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("检索关键词").fill("有限公司");
    await page.getByRole("button", { name: "检索" }).click();
    await page.locator(".result-list li a").first().click({ timeout: 20000 });
    await page.getByRole("link", { name: "在穿透图中查看该主体" }).click();
    await expect(page.locator('[data-testid="graph-canvas"] canvas').first()).toBeVisible({
      timeout: 30000,
    });
    const downloadPromise = page.waitForEvent("download", { timeout: 30000 });
    await page.getByRole("button", { name: "导出报告" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/^report_penetration_.*\.html$/);
  });

  test("证据工作台：覆盖率卡片、缺失口径与声明反查", async ({ page }) => {
    await page.goto("/evidence");
    await expect(page.getByTestId("coverage-total")).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId("coverage-total")).toContainText("100%");
    // 按声明反查：取异动事件的证据键（真实 statement id）
    const events = (await apiGet(
      page,
      "/api/v1/events?from=2022-01-01&to=2023-01-01",
    )) as { events: { evidence_keys: string[] }[] };
    const sid = events.events[0].evidence_keys[0];
    await page.getByTestId("evidence-query").fill(sid);
    await page.getByRole("button", { name: "反查证据" }).click();
    const result = page.getByTestId("evidence-lookup-result");
    await expect(result).toBeVisible({ timeout: 15000 });
    await expect(result).toContainText("命中 1/1");
    // 来源文档导航树可用
    await expect(page.getByText(/按来源文档浏览/)).toBeVisible();
  });
});
