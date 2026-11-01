import { expect, test } from "@playwright/test";
import { alertOf, mockBackend } from "./mock";

test.describe("dashboard", () => {
  test("overview explains the market in plain words", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/");

    await expect(page.getByRole("status").filter({ hasText: "Live" })).toBeVisible();
    await expect(page.getByText("Buyers are leading")).toBeVisible();
    await expect(page.getByRole("link", { name: "Bitcoin" }).first()).toBeVisible();
    await expect(page.getByText(/Big purchase: \$60\.0K of Bitcoin/)).toBeVisible();
  });

  test("every sidebar section opens its own page", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/");

    const pages: [string, string][] = [
      ["Coins & prices", "What each coin costs at this moment"],
      ["Unusual moments", "Nothing unusual|Big purchase"],
      ["Where the money is", "The coins people traded the most"],
      ["Buyers vs sellers", "Who is pushing harder"],
      ["Latest trades", "Real trades as they happen"],
      ["How it works", "How does this page work"],
      ["Settings", "Choose how the page looks"],
    ];
    for (const [menu, text] of pages) {
      await page.getByRole("navigation").getByRole("link", { name: new RegExp(menu) }).click();
      await expect(page.getByText(new RegExp(text)).first()).toBeVisible();
    }
  });

  test("search a coin, open its page and switch the chart range", async ({ page }) => {
    const backend = await mockBackend(page);
    await page.goto("/#/prices");

    await page.getByPlaceholder(/search a coin/i).fill("doge");
    await expect(page.getByText("Showing 1 of 3 coins.")).toBeVisible();
    await page.getByPlaceholder(/search a coin/i).fill("btc");
    await page.getByRole("link", { name: "Open Bitcoin" }).click();

    await expect(page).toHaveURL(/#\/coin\/BTCUSDT$/);
    await expect(page.getByRole("heading", { name: /Bitcoin/ }).first()).toBeVisible();
    await expect(page.getByText("Money traded in 24 hours")).toBeVisible();
    await expect(page.getByText("In short:")).toBeVisible();

    await page.getByRole("button", { name: "24 hours" }).click();
    await expect.poll(() => backend.seriesRequests).toContain(1440);
    await expect(page.getByText(/Over the last 24 hours/)).toBeVisible();

    await page.getByRole("link", { name: "← All coins" }).click();
    await expect(page).toHaveURL(/#\/prices$/);
  });

  test("a coin page can be opened directly and survives a reload", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/#/coin/ETHUSDT");
    await expect(page.getByRole("heading", { name: /Ethereum/ }).first()).toBeVisible();

    await page.reload();
    await expect(page.getByRole("heading", { name: /Ethereum/ }).first()).toBeVisible();
  });

  test("settings: dark theme and watchlist are remembered", async ({ page }) => {
    await mockBackend(page);
    await page.goto("/#/settings");

    await page.getByRole("radio", { name: "Dark" }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

    await page.getByLabel(/Bitcoin BTC/).check();
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");

    await page.goto("/#/overview");
    await expect(page.getByRole("heading", { name: "My watchlist" })).toBeVisible();
    await expect(page.locator("a.coin[href='#/coin/BTCUSDT']")).toBeVisible();
  });

  test("alerts: a pop-up appears for a new unusual moment, but not for old ones", async ({ page }) => {
    const backend = await mockBackend(page);
    await page.goto("/#/settings");
    await page.getByRole("switch", { name: /Alert me about unusual moments/ }).check();
    await expect(page.getByRole("status").filter({ hasText: "Live" })).toBeVisible(); // first data has arrived

    await expect(page.locator(".toast")).toHaveCount(0);      // the alert that was already there is not announced

    backend.push([alertOf("new1", { s: "ETHUSDT", ts: Date.now(), detail: { side: "sell", notional: 90_000, ratio: 1200 } })]);
    const toast = page.locator(".toast");
    await expect(toast).toHaveCount(1);
    await expect(toast).toContainText("Big sale: $90.0K of Ethereum");

    await toast.getByRole("link", { name: "Open Ethereum" }).click();
    await expect(page).toHaveURL(/#\/coin\/ETHUSDT$/);
  });

  test("alerts below the chosen big-trade size stay quiet", async ({ page }) => {
    const backend = await mockBackend(page);
    await page.goto("/#/settings");
    await page.getByRole("switch", { name: /Alert me about unusual moments/ }).check();
    await expect(page.getByRole("status").filter({ hasText: "Live" })).toBeVisible(); // first data has arrived
    await page.getByLabel("Smallest big trade to show").selectOption("100000");

    backend.push([alertOf("small", { ts: Date.now(), detail: { side: "buy", notional: 40_000, ratio: 500 } })]);
    await page.waitForTimeout(1200);

    await expect(page.locator(".toast")).toHaveCount(0);
  });

  test("shows a friendly message when the data service is down", async ({ page }) => {
    await page.routeWebSocket(/\/ws$/, (ws) => void ws.close());
    await page.goto("/");

    await expect(page.getByText(/data service is not answering/)).toBeVisible();
  });
});
