import { readFile } from "node:fs/promises";
import { expect, test } from "@playwright/test";

test("spacing updates automatically; exports preserve spacing and genuine transparent alpha", async ({
  page,
}) => {
  await page.route("https://models.rcsb.org/**", async (route) => {
    const response = await fetch(route.request().url());
    await route.fulfill({
      status: response.status,
      body: Buffer.from(await response.arrayBuffer()),
      contentType: "application/octet-stream",
      headers: { "access-control-allow-origin": "*" },
    });
  });
  await page.goto("./");
  await expect(page.locator("#status")).toContainText("protein letters ready", { timeout: 120000 });
  await page.locator("#text").fill("ABDO!");
  await page.locator("#background").selectOption("transparent");
  await page.locator("#render").click();
  await expect(page.locator("#word")).toBeEnabled({ timeout: 120000 });
  await page.locator("#spacing").fill("60");
  await expect(page.locator("#spacing-value")).toHaveText("60%");
  await expect(page.locator("#mvs")).toBeEnabled({ timeout: 120000 });
  const pending = page.waitForEvent("download");
  await page.locator("#mvs").click();
  const file = await pending;
  const scene = JSON.parse(await readFile((await file.path())!, "utf8")) as {
    metadata: { description: string };
  };
  expect(scene.metadata.description).toContain("Extra letter spacing: 0.6");
  expect(JSON.stringify(scene)).not.toContain("blob:");
  for (const id of ["screenshot", "word"]) {
    const output = page.waitForEvent("download");
    await page.locator(`#${id}`).click();
    const result = await output;
    const bytes = await readFile((await result.path())!);
    const dimensions = await page.evaluate(async (values) => {
      const bitmap = await createImageBitmap(
        new Blob([new Uint8Array(values)], { type: "image/png" }),
      );
      const canvas = document.createElement("canvas");
      canvas.width = bitmap.width;
      canvas.height = bitmap.height;
      const context = canvas.getContext("2d")!;
      context.drawImage(bitmap, 0, 0);
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
      let transparent = 0,
        opaque = 0,
        antialiased = 0;
      for (let i = 3; i < pixels.length; i += 4) {
        if (pixels[i] === 0) transparent++;
        else if (pixels[i] === 255) opaque++;
        else antialiased++;
      }
      bitmap.close();
      return { width: canvas.width, height: canvas.height, transparent, opaque, antialiased };
    }, Array.from(bytes));
    expect(dimensions.width).toBe(1600);
    expect(dimensions.height).toBe(900);
    expect(dimensions.transparent).toBeGreaterThan(10000);
    expect(dimensions.opaque).toBeGreaterThan(100);
    expect(dimensions.antialiased).toBeGreaterThan(100);
    await result.saveAs(`test-results/${id}-${test.info().project.name}.png`);
  }
  await page.screenshot({
    path: `test-results/studio-${test.info().project.name}.png`,
    fullPage: true,
  });
});
