import { defineConfig } from "vite-plus";
import { readFile } from "node:fs/promises";

export default defineConfig({
  base: process.env.PAGES_BASE ?? "/pdbwords/",
  plugins: [
    {
      name: "alphabet-attribution",
      async generateBundle() {
        for (const name of ["LICENSE", "ASSET_LICENSE.md"]) {
          this.emitFile({
            type: "asset",
            fileName: name,
            source: await readFile(new URL(`../${name}`, import.meta.url), "utf8"),
          });
        }
      },
    },
  ],
  test: { include: ["src/**/*.test.ts"] },
  lint: { ignorePatterns: ["dist/**"], options: { typeAware: true, typeCheck: true } },
  fmt: { ignorePatterns: ["dist/**", "pnpm-lock.yaml"] },
});
