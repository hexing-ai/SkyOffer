import { chromium } from "@playwright/test";
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const origin = (process.env.DEMO_URL ?? "http://127.0.0.1:4173/SkyOffer").replace(/\/$/, "");
const output = resolve(process.env.SCREENSHOT_DIR ?? "../docs/images");
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1, reducedMotion: "reduce" });
const errors = [];
page.on("pageerror", error => errors.push(error.message));
const failedResponses = [];
page.on("response", response => { if (response.url().startsWith(origin) && response.status() >= 400) failedResponses.push(`${response.status()} ${response.url()}`); });
page.on("request", request => { assert.notEqual(request.method(), "POST", "Read-only demo must not POST applicant data"); });

async function screenshot(name) {
  await page.evaluate(() => document.fonts.ready);
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
  assert.equal(overflow, false, `${name}: horizontal overflow`);
  await page.screenshot({ path: resolve(output, name), fullPage: false });
}

try {
  await page.goto(`${origin}/`, { waitUntil: "networkidle" });
  await page.getByRole("heading", { level: 1 }).waitFor();
  await screenshot("home-desktop.png");
  await page.getByText("查看这条要求的官网依据", { exact: true }).click();
  await page.getByRole("link", { name: /香港大学项目招生页/ }).waitFor({ state: "visible" });
  await page.getByRole("link", { name: "开始选校", exact: true }).first().click();
  await page.getByRole("heading", { name: "选校建议示例", exact: true }).waitFor();
  await screenshot("advice-desktop.png");
  const evidence = page.getByRole("button", { name: /官网依据|字段级|证据/ }).first();
  if (await evidence.count()) { await evidence.click(); }
  await page.getByRole("link", { name: "项目数据库", exact: true }).click();
  await page.getByRole("link", { name: /查看项目详情与官网依据/ }).first().waitFor();
  assert.equal(await page.getByRole("link", { name: /查看项目详情与官网依据/ }).count(), 20);
  await screenshot("programs-desktop.png");
  await page.getByRole("link", { name: /查看项目详情与官网依据/ }).first().click();
  await page.getByRole("link", { name: /打开项目官网/ }).waitFor();
  await page.locator(".field-evidence summary").first().click();
  await page.locator(".field-evidence[open] .evidence-list").waitFor({ state: "visible" });
  await screenshot("evidence-desktop.png");
  await page.getByRole("link", { name: "申请档案", exact: true }).click();
  await page.getByRole("heading", { name: "示例申请档案", exact: true }).waitFor();
  assert.equal(await page.locator("input, textarea").count(), 0);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${origin}/`, { waitUntil: "networkidle" });
  await screenshot("home-mobile.png");
  await page.getByRole("link", { name: "开始选校", exact: true }).first().click();
  await page.getByRole("heading", { name: "选校建议示例", exact: true }).waitFor();
  await screenshot("advice-mobile.png");
  assert.deepEqual(errors, []);
  assert.deepEqual(failedResponses, []);
  console.log("Demo navigation, read-only profile, 20 programs, source details and mobile overflow checks passed.");
} finally {
  await browser.close();
}
