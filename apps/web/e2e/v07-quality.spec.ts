import { expect, test } from "@playwright/test";

/**
 * v0.7 端到端：证据工作台质量总览区（五维度计数 + 三条新规则候选表）。
 * 合成种子库（seed=40）生成器保证 USCC 全部合法、单连接器无跨源冲突，
 * 因此有效性/一致性为空态；唯一性候选数量随种子载荷浮动，只断言结构性事实。
 * 既有 19 项用例不得回归。
 */

test.describe.serial("CapitalGraph CN v0.7 质量总览", () => {
  test("五维度计数与规则表/空态渲染", async ({ page }) => {
    await page.goto("/evidence");
    const overview = page.getByTestId("quality-overview");
    await expect(overview).toBeVisible({ timeout: 20000 });

    // 六个维度计数卡片（v0.10 增比例合计维度）
    const cards = page.getByTestId("quality-counts").locator(".stat-card");
    await expect(cards).toHaveCount(6);

    // 有效性：合成库不变量（USCC 全部合法）→ 空态
    await expect(page.getByTestId("quality-validity-empty")).toBeVisible({
      timeout: 15000,
    });
    // 一致性：单连接器合成数据 → 空态
    await expect(page.getByTestId("quality-consistency-empty")).toBeVisible();

    // 唯一性：数量随载荷浮动，表格或空态二选一可见
    const uniqTable = page.getByTestId("quality-uniqueness-table");
    const uniqEmpty = page.getByTestId("quality-uniqueness-empty");
    if (await uniqTable.isVisible()) {
      const firstRow = uniqTable.locator("tbody tr").first();
      await expect(firstRow.locator("td").nth(1)).toContainText(/\d+ 条/);
      // 反查按钮把声明 ID 填入反查框
      await firstRow.getByRole("button", { name: "反查" }).click();
      await expect(page.getByTestId("evidence-query")).not.toHaveValue("");
    } else {
      await expect(uniqEmpty).toBeVisible();
    }

    // 口径说明可展开
    await expect(overview.getByText(/口径说明（cg-evidence-quality/)).toBeVisible();
  });
});
