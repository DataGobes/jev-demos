import { expect, test } from "@playwright/test";

test("run example: table first, then a chart, in simulated mode", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Run/ }).click();
  await expect(page.getByTestId("chart")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByTestId("chart").locator("canvas")).toBeVisible();
  await expect(page.getByTestId("simulated")).toHaveText("SIMULATED");
  await expect(page.getByTestId("timing")).toContainText("jev");
  await expect(page.getByText(/% match/)).toBeVisible();
});

test("plain SQL shows a table and no panel", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("examples").selectOption({ label: "Plain SQL (no clause)" });
  await page.getByRole("button", { name: /Run/ }).click();
  await expect(page.locator("table")).toBeVisible();
  await expect(page.getByText(/% match/)).toHaveCount(0);
});

test("swapping an alternate makes no network request", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Run/ }).click();
  await expect(page.getByTestId("chart")).toBeVisible({ timeout: 10_000 });
  let calls = 0;
  page.on("request", (r) => { if (r.url().includes("/run")) calls += 1; });
  const title = await page.locator(".panel h3").first().textContent();
  await page.locator(".panel footer button").first().click();
  await expect(page.locator(".panel h3").first()).not.toHaveText(title ?? "");
  expect(calls).toBe(0);
});
