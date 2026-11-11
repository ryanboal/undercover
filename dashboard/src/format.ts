import type { DecisionKind, Status } from "./api";

const dollars = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});
const day = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeZone: "UTC",
});
const moment = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short",
});

const time = new Intl.DateTimeFormat("en-US", { timeStyle: "medium" });

export const AGENT = "UnderCover Agent";

export const statusLabels: Record<Status, string> = {
  waiting: "Waiting",
  in_progress: "In progress",
  waiting_for_sign_off: "Waiting for sign-off",
  decided: "Decided",
};

export const decisionLabels: Record<DecisionKind, string> = {
  approve: "Approve",
  decline: "Decline",
  refer: "Refer",
};

export function money(amount: number): string {
  return dollars.format(amount);
}

export function date(isoDate: string): string {
  return day.format(new Date(isoDate));
}

export function dateTime(isoTimestamp: string): string {
  return moment.format(new Date(isoTimestamp));
}

export function clock(isoTimestamp: string): string {
  return time.format(new Date(isoTimestamp));
}

export function words(identifier: string): string {
  const spaced = identifier.replaceAll("_", " ");
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
