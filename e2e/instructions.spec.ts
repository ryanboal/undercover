import { expect, test } from "@playwright/test";

test("the instructions page shows the agent's instructions, read only", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Instructions" }).click();
  await expect(
    page.getByRole("heading", { name: "The UnderCover Agent" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "UnderCover Travel Insurance: Policy Wording",
    }),
  ).toBeVisible();
  for (const section of [
    "3. Trip Delay",
    "7. Emergency Medical",
    "10. How we work out your payment",
  ]) {
    await expect(page.getByRole("heading", { name: section })).toBeVisible();
  }
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByRole("textbox")).toHaveCount(0);
  await expect(page.getByRole("button")).toHaveCount(0);
});
