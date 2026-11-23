import { type APIRequestContext, expect, test } from "@playwright/test";

// These tests stand in for the queue agent and the claim agent by calling the
// API through the dashboard's proxy, and watch the pages update without a reload.

async function send(
  request: APIRequestContext,
  path: string,
  data: object,
  method: "post" | "put" = "post",
) {
  const response = await request[method](path, { data });
  expect(response.ok()).toBe(true);
  return (await response.json()) as { run_id: string };
}

test("the queue page shows the agent's to-do list", async ({
  page,
  request,
}) => {
  await page.goto("/");
  const panel = page.locator("section", {
    has: page.getByRole("heading", { name: "Agent's to-do list" }),
  });
  await expect(panel).toBeVisible();

  const { run_id } = await send(request, "/api/runs", { cap: 2 });
  await send(
    request,
    `/api/runs/${run_id}/todos`,
    {
      todos: [
        { task: "Work CLM-1013", status: "in_progress" },
        { task: "Work CLM-1014", status: "to_do" },
      ],
    },
    "put",
  );
  await expect(panel.getByText("capped at 2 claims")).toBeVisible();
  await expect(panel.getByRole("listitem")).toHaveText([
    "In progressWork CLM-1013",
    "To doWork CLM-1014",
  ]);

  await send(
    request,
    `/api/runs/${run_id}/todos`,
    {
      todos: [
        { task: "Work CLM-1013", status: "done" },
        { task: "Work CLM-1014", status: "done" },
      ],
    },
    "put",
  );
  await send(request, `/api/runs/${run_id}/finish`, {
    summary: "Worked 2 claims.",
  });
  await expect(panel.getByRole("listitem")).toHaveText([
    "DoneWork CLM-1013",
    "DoneWork CLM-1014",
  ]);
  await expect(panel.getByText("Worked 2 claims.")).toBeVisible();
  await expect(panel.getByText(/^Run finished at/)).toBeVisible();
});

test("the claim page shows the sections the agent read", async ({
  page,
  request,
}) => {
  await send(request, "/api/claims/CLM-1016/start", { thread_id: "e2e-3" });
  await send(request, "/api/claims/CLM-1016/steps", {
    kind: "read",
    content:
      "Claims manual, section 9: Repeat claims\n\nBefore deciding any claim, check the history.",
  });
  await page.goto("/claims/CLM-1016");
  const read = page.locator("details", {
    hasText: "Claims manual, section 9: Repeat claims",
  });
  await expect(read.locator(".step-label")).toHaveText("Read");
  await expect(read.getByText(/check the history/)).toBeHidden();
  await read.locator("summary").click();
  await expect(read.getByText(/check the history/)).toBeVisible();
});

test("a claim that fails twice needs a handler", async ({ page, request }) => {
  for (const attempt of [1, 2]) {
    await send(request, "/api/claims/CLM-1015/start", {
      thread_id: `e2e-fail-${String(attempt)}`,
    });
    await send(request, "/api/claims/CLM-1015/release", {
      reason: `Attempt ${String(attempt)} timed out`,
    });
  }
  await page.goto("/");
  const row = page.getByRole("row", { name: /CLM-1015/ });
  await expect(row.getByText("Needs a handler")).toBeVisible();
  await row.getByRole("link", { name: "CLM-1015" }).click();
  await expect(
    page.locator(".claim-heading").getByText("Needs a handler"),
  ).toBeVisible();
  await expect(page.getByText(/left for a handler/)).toBeVisible();
  await expect(page.getByText("Failed Attempt 2 timed out")).toBeVisible();
});
