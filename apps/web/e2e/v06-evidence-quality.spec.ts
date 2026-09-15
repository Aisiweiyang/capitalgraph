import { expect, test } from "@playwright/test";

/**
 * v0.6 端到端补充（切片 D）：证据工作台的覆盖率趋势区与时效风险区。
 * 合成种子库（seed=40）中仅质押证据快照取证时间为 2019-01-01（其余为建库当日），
 * 因此默认阈值 5 年下恰有一条候选；阈值放大到 30 年后回到空态。
 * 既有 16 项用例不得回归（core-flow.spec.ts + v05-pages.spec.ts）。
 */

test.describe.serial("CapitalGraph CN v0.6 证据质量", () => {
  test("覆盖率趋势区：图表与逐年表格渲染", async ({ page }) => {
    await page.goto("/evidence");
    const table = page.getByTestId("coverage-timeline-table");
    await expect(table).toBeVisible({ timeout: 20000 });
    // 合成数据覆盖多个生效年度：行数非空即可（年度数随种子载荷浮动）
    const rows = table.locator("tbody tr");
    await expect(rows.first()).toBeVisible({ timeout: 15000 });
    // 首行五列（年度/声明数/缺失/覆盖率/较上年）均有值
    const firstRowCells = rows.first().locator("td");
    await expect(firstRowCells).toHaveCount(5);
    // 趋势图（EChart）渲染
    await expect(page.locator(".evidence-trend canvas").first()).toBeVisible({
      timeout: 20000,
    });
  });

  test("时效风险区：默认 5 年阈值列出质押候选，放大阈值回到空态", async ({ page }) => {
    await page.goto("/evidence");
    // 默认阈值 5 年：2019-01-01 取证的质押证据距今 > 5 年，唯一候选
    const staleTable = page.getByTestId("staleness-table");
    await expect(staleTable).toBeVisible({ timeout: 20000 });
    await expect(staleTable.locator("tbody tr")).toHaveCount(1);
    await expect(staleTable).toContainText("pledge");
    await expect(staleTable).toContainText("2019-01-01");
    // 阈值放大到 30 年：无早于 1996 年的证据 → 空态
    await page.getByTestId("staleness-years").selectOption("30");
    await expect(page.getByTestId("staleness-empty")).toBeVisible({ timeout: 15000 });
    await expect(page.getByTestId("staleness-empty")).toContainText("当前阈值下没有候选声明");
    // 回到 5 年：候选重新出现（纯查询，无副作用）
    await page.getByTestId("staleness-years").selectOption("5");
    await expect(staleTable).toBeVisible({ timeout: 15000 });
  });

  test("viewer 视角：扫描入库按钮隐藏并提示需要 analyst 角色", async ({ page }) => {
    await page.goto("/evidence");
    // E2E 登录态为 viewer：写通道按钮不出现，仅展示角色提示
    await expect(page.getByTestId("staleness-scan")).toHaveCount(0);
    const hint = page.getByTestId("staleness-scan-hint");
    await expect(hint).toBeVisible({ timeout: 20000 });
    await expect(hint).toContainText("登录 analyst 后");
    // 候选列表本身对 viewer 可见（只读通道）
    await expect(page.getByTestId("staleness-table")).toBeVisible({ timeout: 15000 });
  });
});
