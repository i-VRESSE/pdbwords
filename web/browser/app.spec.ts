import { expect, test } from "@playwright/test";

test("renders letters, caches repeated coordinates, and exports both PNGs and MVSJ", async ({
  page,
}) => {
  // Fetch real coordinates through the runner to avoid host browser proxy differences.
  await page.route("https://models.rcsb.org/**", async (route) => {
    const response = await fetch(route.request().url(), { signal: AbortSignal.timeout(60000) });
    const body = Buffer.from(await response.arrayBuffer());
    await route.fulfill({
      status: response.status,
      body,
      contentType: "application/octet-stream",
      headers: { "access-control-allow-origin": "*" },
    });
  });
  const downloads: string[] = [];
  page.on("request", (r) => {
    if (r.url().startsWith("https://models.rcsb.org/")) downloads.push(r.url());
  });
  await page.goto("./");
  await expect(page.locator("#status")).toContainText("protein letters ready", { timeout: 120000 });
  await page.locator("#text").fill("ABDO AA\nHELLO!");
  await expect(page.locator("#word")).toBeDisabled();
  await page.locator("#render").click();
  await expect(page.locator("#status")).toContainText("Punctuation omitted from 3D: !", {
    timeout: 120000,
  });
  expect(downloads.length).toBe(new Set(downloads).size);
  await expect(page.locator("#structures")).toContainText("A · 3IFZ");
  await page.locator("#reset").click();
  for (const id of ["mvs", "screenshot", "word"]) {
    const pending = page.waitForEvent("download");
    await page.locator(`#${id}`).click();
    const file = await pending;
    expect(await file.failure()).toBeNull();
    expect(file.suggestedFilename()).toMatch(id === "mvs" ? /\.mvsj$/ : /\.png$/);
    await expect(page.locator("#status")).not.toContainText("Export failed");
  }
  await page.getByRole("button", { name: "Try all letters (A–Z)" }).click();
  await expect(page.locator("#text")).toHaveValue("ABCDEFG\nHIJKLMN\nOPQRSTU\nVWXYZ");
  await expect(page.locator("#status")).toContainText("26 protein letters ready", {
    timeout: 120000,
  });
  await page.screenshot({ path: `test-results/alphabet-${test.info().project.name}.png` });
});

test("download failures and unsupported input are actionable", async ({ page }) => {
  await page.route("https://models.rcsb.org/**", (route) =>
    route.fulfill({ status: 503, body: "unavailable" }),
  );
  await page.goto("./");
  await expect(page.locator("#status")).toContainText("503", { timeout: 30000 });
  await expect(page.locator("#word")).toBeDisabled();
  await page.locator("#text").fill("ABC123");
  await page.locator("#render").click();
  await expect(page.locator("#status")).toContainText("Digits are not supported");
});

test("reports unavailable WebGL", async ({ page }) => {
  await page.addInitScript(() => {
    // oxlint-disable-next-line typescript/unbound-method
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      this: HTMLCanvasElement,
      ...args: Parameters<typeof original>
    ) {
      if (String(args[0]).startsWith("webgl")) return null;
      return original.apply(this, args);
    } as typeof original;
  });
  await page.goto("./");
  await expect(page.locator("#status")).toContainText("WebGL is unavailable");
});
