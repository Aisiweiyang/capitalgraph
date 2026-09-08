import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const stateFile = path.join(path.dirname(fileURLToPath(import.meta.url)), ".auth-state.json");

test("准备登录态", async ({ request }) => {
  const resp = await request.post("/api/v1/auth/login", {
    data: { username: "viewer", password: "viewer-demo-password" },
  });
  expect(resp.ok()).toBeTruthy();
  const { access_token } = await resp.json();
  fs.mkdirSync(path.dirname(stateFile), { recursive: true });
  fs.writeFileSync(
    stateFile,
    JSON.stringify({
      cookies: [],
      origins: [{ origin: "http://127.0.0.1:5273", localStorage: [{ name: "cg_token", value: access_token }] }],
    }),
  );
});

export { stateFile };
