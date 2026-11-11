import { expect, test } from "@playwright/test";

test("a handler signs off a payout the agent could not pay", async ({
  page,
  request,
}) => {
  // Act as the agent through the API: approve $1,150.00, then try to pay it.
  await request.post("/api/claims/CLM-1003/start");
  await request.post("/api/claims/CLM-1003/decision", {
    data: {
      decision: "approve",
      payout: 1150,
      reason: "The fractured wrist is covered under Emergency Medical.",
      policy_section: "Section 7, Emergency Medical",
    },
  });
  const payment = await request.post("/api/claims/CLM-1003/payment", {
    data: { amount: 1150 },
  });
  expect(payment.status()).toBe(403);

  await page.goto("/claims/CLM-1003");
  await expect(
    page.getByText("Payment waits for a handler's sign-off."),
  ).toBeVisible();
  await expect(
    page.getByText("The fractured wrist is covered under Emergency Medical."),
  ).toBeVisible();
  await page.getByLabel("Handler").selectOption({ label: "Dana Whitfield" });
  await page
    .getByRole("button", { name: "Sign off and pay $1,150.00" })
    .click();
  await expect(
    page.getByText(/Paid \$1,150\.00, signed off by Dana Whitfield/),
  ).toBeVisible();

  await page.getByRole("link", { name: "Back to the queue" }).click();
  const row = page.getByRole("row").filter({ hasText: "CLM-1003" });
  await expect(row).toContainText("Decided");
  await expect(row).toContainText("$1,150.00");
});
