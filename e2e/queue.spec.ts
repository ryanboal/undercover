import { expect, test } from "@playwright/test";

test("the queue shows the 25 claims and opens one", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Claims queue" }),
  ).toBeVisible();
  const rows = page.getByRole("table").getByRole("row");
  await expect(rows).toHaveCount(26);
  await expect(rows.nth(1)).toContainText("Maya Patel");
  await expect(rows.nth(1)).toContainText("$420.00");

  await page.getByRole("link", { name: "CLM-1001" }).click();
  await expect(page).toHaveURL(/\/claims\/CLM-1001$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "CLM-1001",
  );
});
