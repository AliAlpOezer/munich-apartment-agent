import { describe, expect, it } from "vitest";
import type { Criteria } from "../src/config";
import { evaluate } from "../src/filter";
import type { ListingFacts } from "../src/types";

const criteria: Criteria = {
  anchors: [{ label: "TUM", name: "TUM", lat: 48.26, lng: 11.67 }],
  transitLine: "U6",
  transitStops: [{ label: "Freimann", name: "U6 Freimann", lat: 48.19, lng: 11.61 }],
  maxBikeToStopMinutes: 10,
  maxWarmRentEur: 650,
  minSizeSqm: 10,
  availableBy: "2027-01-31",
  minStayDays: 90,
  maxBikeMinutes: 30,
  bikeSpeedKmh: 22,
};
const today = "2026-10-22";
const base: ListingFacts = {
  priceListed: 600, priceWarm: null, priceCold: null, sizeSqm: 14,
  availableFrom: "2026-11-01", availableTo: null, bikeMinutes: 18, stopMinutes: null,
};
const check = (patch: Partial<ListingFacts>) => evaluate({ ...base, ...patch }, criteria, today);

describe("evaluate", () => {
  it("matches a listing inside every limit", () => {
    expect(check({})).toEqual({ matched: true, reasons: [] });
  });

  it("caps rent on warm, then cold, then the card figure", () => {
    expect(check({ priceWarm: 651 }).reasons).toEqual(["rent 651 € > 650 €"]);
    expect(check({ priceWarm: 650 }).matched).toBe(true);
    expect(check({ priceCold: 700, priceListed: 600 }).matched).toBe(false);
    expect(check({ priceWarm: 640, priceListed: 700 }).matched).toBe(true); // resolved warm wins
  });

  it("keeps listings whose rent, size, date or bike time is unknown", () => {
    expect(check({ priceListed: null, sizeSqm: null, availableFrom: null, bikeMinutes: null }).matched).toBe(true);
  });

  it("rejects small rooms", () => {
    expect(check({ sizeSqm: 9 }).reasons).toEqual(["size 9 m² < 10 m²"]);
  });

  it("accepts anything available by the end of January 2027, including past start dates", () => {
    expect(check({ availableFrom: "2026-09-15" }).matched).toBe(true);
    expect(check({ availableFrom: "2027-01-31" }).matched).toBe(true);
    expect(check({ availableFrom: "2027-02-01" }).reasons).toEqual(["available from 2027-02-01, after 2027-01-31"]);
  });

  it("rejects temporary sublets shorter than the minimum stay, counted from move-in", () => {
    expect(check({ availableFrom: "2026-11-01", availableTo: "2027-01-15" }).reasons).toEqual([
      "temporary: only 75 days (until 2027-01-15)",
    ]);
    expect(check({ availableFrom: "2026-11-01", availableTo: "2027-03-31" }).matched).toBe(true);
    // Started in the past: the stay counts from today.
    expect(check({ availableFrom: "2026-08-01", availableTo: "2026-12-31" }).matched).toBe(false);
    expect(check({ availableFrom: null, availableTo: "2026-10-01" }).reasons).toEqual([
      "temporary: only 0 days (until 2026-10-01)",
    ]);
  });

  it("accepts a long ride when a transit stop is a short ride away", () => {
    expect(check({ bikeMinutes: 45, stopMinutes: 10 }).matched).toBe(true);
    expect(check({ bikeMinutes: 45, stopMinutes: 12.4 }).reasons).toEqual([
      "bike 45 min > 30 min; 12 min to the U6 > 10 min",
    ]);
    expect(check({ bikeMinutes: null, stopMinutes: 40 }).matched).toBe(true); // unknown ride keeps
  });

  it("rejects commutes over the limit and reports every failed rule", () => {
    expect(check({ bikeMinutes: 30 }).matched).toBe(true);
    expect(check({ bikeMinutes: 30.4, sizeSqm: 8 }).reasons).toEqual([
      "size 8 m² < 10 m²",
      "bike 30 min > 30 min",
    ]);
  });
});
