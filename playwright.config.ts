import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./browser",
  timeout: 180000,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:4173/pdbwords/", acceptDownloads: true },
  webServer: {
    command: "pnpm exec vp preview --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173/pdbwords/",
    reuseExistingServer: !process.env.CI,
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        launchOptions: {
          executablePath: process.env.CHROMIUM_PATH,
          args: ["--enable-unsafe-swiftshader"],
        },
      },
    },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "mobile", use: { ...devices["iPhone 13"] } },
  ],
});
