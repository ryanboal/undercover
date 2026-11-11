import { cleanup, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { renderAt, stubApi } from "./testing";

const instructions = `# The UnderCover Agent

You decide claims with \`decide_claim\`.

# Policy Wording

## 1. Your plan

| Benefit | Economy |
|---|---|
| Deductible | $100 |
`;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the instructions and the wording, read only", async () => {
  stubApi({ "GET /api/instructions": { instructions } });
  renderAt("/instructions");
  expect(
    await screen.findByRole("heading", { name: "The UnderCover Agent" }),
  ).toBeDefined();
  expect(screen.getByRole("heading", { name: "1. Your plan" })).toBeDefined();
  expect(screen.getByRole("table")).toBeDefined();
  expect(screen.getByRole("cell", { name: "$100" })).toBeDefined();
  expect(screen.getByText("decide_claim").tagName).toBe("CODE");
  expect(screen.queryByRole("textbox")).toBeNull();
  expect(screen.queryByRole("button")).toBeNull();
  expect(
    screen.getByRole("link", { name: "Instructions" }).className,
  ).toContain("active");
});

it("says when the instructions cannot be loaded", async () => {
  stubApi({});
  renderAt("/instructions");
  expect(await screen.findByText("Failed to fetch")).toBeDefined();
});
