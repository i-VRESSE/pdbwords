/** Regenerate README images from a running production preview. */
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { chromium, expect } from "@playwright/test";

const output = process.env.README_IMAGES_DIR
  ? resolve(process.env.README_IMAGES_DIR)
  : fileURLToPath(new URL("../docs/images/", import.meta.url));
const url = process.env.PDBWORDS_URL ?? "http://127.0.0.1:4173/pdbwords/";
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH,
  args: ["--enable-unsafe-swiftshader"],
});
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1,
    acceptDownloads: true,
  });
  // Match browser tests: fetch coordinates through Node for consistent proxy handling.
  await page.route(/https:\/\/(models|files)\.rcsb\.org\//, async (route) => {
    const response = await fetch(route.request().url(), { signal: AbortSignal.timeout(60000) });
    await route.fulfill({
      status: response.status,
      body: Buffer.from(await response.arrayBuffer()),
      contentType: "application/octet-stream",
      headers: { "access-control-allow-origin": "*" },
    });
  });
  await page.goto(url);
  await expect(page.locator("#status")).toContainText("protein letters ready", {
    timeout: 120000,
  });
  await page.locator("#text").fill("pdbwords");
  await page.locator("#render").click();
  await expect(page.locator("#status")).toContainText("8 protein letters ready", {
    timeout: 120000,
  });
  await page.locator("#reset").click();
  await page.screenshot({ path: resolve(output, "pdbwords-app.png"), fullPage: true });
  console.log("Saved pdbwords-app.png");

  for (const [button, ready, filename] of [
    ["Try all letters (A–Z)", "26 protein letters ready", "alphabet.png"],
    ["Try all digits (0–9)", "10 protein characters ready", "digits.png"],
  ]) {
    await page.getByRole("button", { name: button }).click();
    await expect(page.locator("#status")).toContainText(ready, { timeout: 240000 });
    const pending = page.waitForEvent("download", { timeout: 240000 });
    await page.locator("#word").click();
    const download = await pending;
    const failure = await download.failure();
    if (failure) throw new Error(`${filename}: ${failure}`);
    await download.saveAs(resolve(output, filename));
    console.log(`Saved ${filename}`);
  }
  console.log(`README images written to ${output}`);
} finally {
  await browser.close();
}
