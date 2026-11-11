import { expect, test } from "@playwright/test";

test("the agent's steps appear on an open claim page", async ({
  page,
  request,
}) => {
  await page.goto("/claims/CLM-1005");
  await expect(page.getByText("No steps yet.")).toBeVisible();
  await page.evaluate(() => {
    document.body.dataset.loaded = "once";
  });

  // Act as the agent through the API while the page stays open.
  await request.post("/api/claims/CLM-1005/start");
  await request.post("/api/claims/CLM-1005/steps", {
    data: { kind: "tool_call", text: 'get_claim(claim_id="CLM-1005")' },
  });
  await request.post("/api/claims/CLM-1005/steps", {
    data: { kind: "tool_result", text: 'get_claim: {"claim_id":"CLM-1005"}' },
  });

  await expect(page.getByText('get_claim(claim_id="CLM-1005")')).toBeVisible();
  await expect(page.getByText("Result of get_claim")).toBeVisible();
  await expect(
    page.getByText("The agent is working on this claim."),
  ).toBeVisible();
  await expect(page.locator("body")).toHaveAttribute("data-loaded", "once");
});
