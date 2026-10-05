import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

test("renders letters, caches repeated coordinates, and exports both PNGs and MVSJ", async ({
  page,
}) => {
  // Software WebGL on CI renders several PNGs and the full alphabet in this test.
  test.setTimeout(360000);
  // Fetch real coordinates through the runner to avoid host browser proxy differences.
  await page.route(/https:\/\/(models|files)\.rcsb\.org\//, async (route) => {
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
    if (/https:\/\/(models|files)\.rcsb\.org\//.test(r.url())) downloads.push(r.url());
  });
  await page.goto("./");
  await expect(page.locator("#status")).toContainText("protein letters ready", { timeout: 120000 });
  // Cover repeats, wrapping, digits and punctuation with fewer export tiles.
  // The full alphabet is rendered below without exporting every letter again.
  await page.locator("#text").fill("ABDO AA\n36!");
  await expect(page.locator("#word")).toBeDisabled();
  await page.locator("#render").click();
  await expect(page.locator("#status")).toContainText("Punctuation omitted from 3D: !", {
    timeout: 120000,
  });
  expect(downloads.length).toBe(new Set(downloads).size);
  await expect(page.locator("#structures")).toContainText("A · 3IFZ");
  await expect(page.locator("#structures")).toContainText("3 · 9GC7");
  await expect(page.locator("#structures")).toContainText("6 · 5J4A");
  await page.locator("#reset").click();
  for (const id of ["mvs", "screenshot", "word"]) {
    await test.step(`Export ${id}`, async () => {
      const pending = page.waitForEvent("download");
      await page.locator(`#${id}`).click();
      const file = await pending;
      expect(await file.failure()).toBeNull();
      expect(file.suggestedFilename()).toMatch(id === "mvs" ? /\.mvsj$/ : /\.png$/);
      await expect(page.locator("#status")).not.toContainText("Export failed");
    });
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
  await page.locator("#text").fill("ABC٢");
  await page.locator("#render").click();
  await expect(page.locator("#status")).toContainText("Unsupported characters: ٢");
});

test("renders all digits without letters and embeds portable coordinates", async ({ page }) => {
  test.setTimeout(300000);
  await page.route(/https:\/\/(models|files)\.rcsb\.org\//, async (route) => {
    const response = await fetch(route.request().url(), { signal: AbortSignal.timeout(60000) });
    await route.fulfill({
      status: response.status,
      body: Buffer.from(await response.arrayBuffer()),
      headers: { "access-control-allow-origin": "*" },
    });
  });
  await page.goto("./");
  await expect(page.locator("#status")).toContainText("protein letters ready", { timeout: 120000 });
  await page.getByRole("button", { name: "Try all digits (0–9)" }).click();
  await expect(page.locator("#text")).toHaveValue("01234\n56789");
  await expect(page.locator("#status")).toContainText("10 protein characters ready", {
    timeout: 240000,
  });
  await expect(page.locator("#structures a")).toHaveCount(10);
  await expect(page.locator("#structures")).toContainText("8 · 3PON");
  const pending = page.waitForEvent("download");
  await page.locator("#mvs").click();
  const file = await pending;
  const scene = JSON.parse(await readFile((await file.path())!, "utf8")) as {
    root: { children: { kind: string; params: { url: string } }[] };
    metadata: { description: string };
  };
  const downloads = scene.root.children.filter((n) => n.kind === "download");
  expect(downloads).toHaveLength(10);
  for (const node of downloads)
    expect(node.params.url).toMatch(/^data:application\/octet-stream;base64,/);
  expect(scene.metadata.description).toContain("9gc7-assembly2.cif");
  expect(scene.metadata.description).toContain("3pon-assembly3.cif");
  await page.screenshot({ path: `test-results/digits-${test.info().project.name}.png` });
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
