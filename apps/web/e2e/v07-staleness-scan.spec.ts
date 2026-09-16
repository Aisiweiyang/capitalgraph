import { expect, test, type Page } from "@playwright/test";

/**
 * v0.7 端到端补充：analyst 视角的时效扫描入库写通道。
 * viewer 只能看到角色提示（已有用例覆盖）；analyst 能看到"扫描入库"按钮，
 * 点击后候选幂等登记进复核通道：首次 created=N/skipped=0，重复点击 created=0/skipped=N。
 */

/** 页内登录 analyst 并把 token 写入 localStorage（复用 viewer storageState 的页面上下文）。 */
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

test.describe.serial("CapitalGraph CN v0.7 时效扫描入库（analyst 写通道）", () => {
  test("扫描按钮可见且幂等登记：created → skipped", async ({ page }) => {
    await page.goto("/evidence");
    await loginAnalyst(page);

    // 默认 5 年阈值下恰有质押候选（2019-01-01 取证）
    await expect(page.getByTestId("staleness-table")).toBeVisible({ timeout: 20000 });
    const scan = page.getByTestId("staleness-scan");
    await expect(scan).toBeVisible();
    await expect(scan).toContainText("扫描入库");
    // viewer 提示不再出现
    await expect(page.getByTestId("staleness-scan-hint")).toHaveCount(0);

    // 扫描：计数与库历史状态无关（可重复执行），规则名正确
    await scan.click();
    const result = page.getByTestId("staleness-scan-result");
    await expect(result).toBeVisible({ timeout: 15000 });
    await expect(result).toContainText(/已入库 \d+ 条（跳过重复 \d+ 条）· 规则 stale_source/);

    // 重复扫描：全部跳过（幂等）
    await page.getByTestId("staleness-scan").click();
    await expect(result).toContainText(/已入库 0 条（跳过重复 [1-9]\d* 条）· 规则 stale_source/);
  });
});


test.describe.serial("CapitalGraph CN v0.8 质量登记（analyst 写通道）", () => {
  test("三类候选幂等登记复核通道", async ({ page }) => {
    await page.goto("/evidence");
    await loginAnalyst(page);

    const scan = page.getByTestId("quality-scan");
    await expect(scan).toBeVisible({ timeout: 20000 });

    // 登记结果与库历史状态无关（可重复执行）；规则名清单随文案输出
    await scan.click();
    const result = page.getByTestId("quality-scan-result");
    await expect(result).toBeVisible({ timeout: 15000 });
    await expect(result).toContainText(
      /已入库 \d+ 条（跳过重复 \d+ 条）· identifier_validity\/duplicate_statement\/cross_source_conflict/,
    );

    // 幂等：再次登记 created=0
    await page.getByTestId("quality-scan").click();
    await expect(result).toContainText(/已入库 0 条（跳过重复 \d+ 条）/);
  });
});
