import { expect, test } from "@playwright/test";

/**
 * 核心链路 E2E：
 * 导入演示数据(脚本预置) -> 检索企业 -> 打开详情 -> 穿透图 -> 来源证据 -> 时间点切换 -> 导出
 * 登录态由 setup 项目（auth.setup.ts）通过 API 预置。
 */

test.describe.serial("CapitalGraph CN 核心链路", () => {
  let entityUrl: string;

  test("检索企业", async ({ page }) => {
    await page.goto("/");
    const input = page.getByLabel("检索关键词");
    await input.fill("有限公司");
    await page.getByRole("button", { name: "检索" }).click();
    await expect(page.locator(".result-list li").first()).toBeVisible({ timeout: 15000 });
    await page.locator(".result-list li a").first().click();
    await expect(page.locator("h2")).not.toBeEmpty();
    entityUrl = page.url();
  });

  test("详情页含标识符与声明", async ({ page }) => {
    await page.goto(entityUrl);
    await expect(page.getByRole("heading", { name: "标识符" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "直接股东（当前）" })).toBeVisible();
  });

  test("查看来源证据片段", async ({ page }) => {
    await page.goto(entityUrl);
    const btn = page.getByRole("button", { name: "查看" }).first();
    await btn.click();
    await expect(page.getByRole("heading", { name: /证据片段/ })).toBeVisible({ timeout: 10000 });
  });

  test("穿透图展开与聚合面板", async ({ page }) => {
    await page.goto(entityUrl);
    await page.getByRole("link", { name: "在穿透图中查看该主体" }).click();
    await expect(page.locator('[data-testid="graph-canvas"] canvas').first()).toBeVisible({
      timeout: 20000,
    });
    await expect(page.getByRole("heading", { name: /股东聚合/ })).toBeVisible();
    await page.locator('input[type="range"]').fill("2");
    await expect(page.locator('[data-testid="graph-canvas"] canvas').first()).toBeVisible();
  });

  test("切换历史时间点", async ({ page }) => {
    await page.goto(entityUrl);
    await page.getByRole("link", { name: "在穿透图中查看该主体" }).click();
    // v0.5.1 起实体页也有日期输入（变更轨迹窗口），此处用穿透图页专属 testid 收窄
    await page.getByTestId("explore-at").fill("2020-01-01");
    await expect(page.locator(".side-pane h3")).toContainText("2020-01-01", { timeout: 15000 });
  });

  test("导出 CSV", async ({ page }) => {
    await page.goto(entityUrl);
    await page.getByRole("link", { name: "在穿透图中查看该主体" }).click();
    await expect(page.getByRole("button", { name: "导出 CSV" })).toBeVisible();
    const downloadPromise = page.waitForEvent("download", { timeout: 20000 });
    await page.getByRole("button", { name: "导出 CSV" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toContain(".csv");
  });

  test("导出 PNG", async ({ page }) => {
    await page.goto(entityUrl);
    await page.getByRole("link", { name: "在穿透图中查看该主体" }).click();
    await expect(page.locator('[data-testid="graph-canvas"] canvas').first()).toBeVisible({
      timeout: 20000,
    });
    const downloadPromise = page.waitForEvent("download", { timeout: 20000 });
    await page.getByRole("button", { name: "导出 PNG" }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toContain(".png");
  });
});
