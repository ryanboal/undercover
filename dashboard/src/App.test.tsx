import { cleanup, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ApiError, claim, renderAt, stubApi } from "./testing";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("opens a claim's page", async () => {
  stubApi({ "GET /api/claims/CLM-1001": claim });
  renderAt("/claims/CLM-1001");
  expect(await screen.findByRole("heading", { level: 1 })).toBeDefined();
  expect(screen.getByRole("heading", { level: 1 }).textContent).toContain(
    "CLM-1001",
  );
});

it("says when a claim is not found", async () => {
  stubApi({
    "GET /api/claims/CLM-9999": new ApiError(404, "Claim CLM-9999 not found"),
  });
  renderAt("/claims/CLM-9999");
  expect(await screen.findByText("Claim CLM-9999 not found")).toBeDefined();
});

it("has no page at an unknown address", () => {
  stubApi({});
  renderAt("/nowhere");
  expect(screen.getByText("There is no page here.")).toBeDefined();
});
