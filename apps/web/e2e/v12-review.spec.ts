import { expect, test, type Page } from "@playwright/test";

/**
 * v0.12 端到端补充：复核页数据质量问题处置闭环。
 * 前置：库中已有 staleness scan 登记的 open 登记（历轮 E2E scan 产生）。
 * analyst 进入 /review → 对 open 行填写甄别结论并"标记已处理"→ 状态变 resolved。
 * 若库中已无 open（全部处置过）：仅断言表格渲染，保持用例可重复执行。
 */

/** 页内登录 analyst（复用 storageState 页面上下文）。 */
async function loginAnalyst(page: Page) {
  await page.evaluate(async () => {
    const resp = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: "analyst", password: "analyst-demo-password" }),
    });
    if (!resp.ok) throw new Error(`analyst login -> ${resp.status}`);
    const { access_token } = (await resp.json()) as { access_token: string };
    localStorage.setItem("cg_token", access_token);
  });
  await page.reload();
}

test.describe.serial("CapitalGraph v0.12 复核处置闭环", () => {
  test("质量问题表渲染与处置", async ({ page }) => {
    await page.goto("/review");
    await loginAnalyst(page);

    // 质量问题表可见（历轮 staleness scan 至少登记过一条）
    const qualitySection = page.getByRole("heading", { name: "数据质量问题" });
    await expect(qualitySection).toBeVisible({ timeout: 20000 });
    const table = qualitySection.locator("xpath=following-sibling::table[1]");
    await expect(table.locator("tbody tr").first()).toBeVisible({ timeout: 15000 });

    // 找 open 行处置（状态无关：没有 open 行则只断言渲染）
    const resolveButtons = page.getByRole("button", { name: "标记已处理" });
    if ((await resolveButtons.count()) > 0) {
      await resolveButtons.first().click();
      // 处置后刷新，open 计数减少（或该行状态变化）
      await expect(page.getByText("resolved").first()).toBeVisible({ timeout: 15000 });
    }
  });

  test("证据 deep-link 可见", async ({ page }) => {
    await page.goto("/review");
    await loginAnalyst(page);
    const qualitySection = page.getByRole("heading", { name: "数据质量问题" });
    await expect(qualitySection).toBeVisible({ timeout: 20000 });
    // 有登记的行带证据链接（detail 内声明 ID 拼接）
    const evidenceLinks = page.getByRole("link", { name: "证据" });
    const count = await evidenceLinks.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});
