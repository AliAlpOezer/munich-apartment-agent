import { env } from "cloudflare:workers";
import { describe, expect, it } from "vitest";
import { loadSettings, nextScheduledRun, SCHEDULE } from "../src/config";
import wranglerConfig from "../wrangler.jsonc?raw";

const vars = env as unknown as Record<string, unknown>;

describe("loadSettings", () => {
  it("reads the deployed criteria", () => {
    const s = loadSettings(vars);
    expect(s.criteria).toMatchObject({
      maxWarmRentEur: 650, availableBy: "2027-01-31", maxBikeMinutes: 30, bikeSpeedKmh: 22,
    });
    expect(s.criteria.anchors.map((a) => a.label)).toEqual(["TUM", "SAP"]);
  });

  it("fails loudly on a malformed value instead of filtering wrongly", () => {
    expect(() => loadSettings({ ...vars, MAX_WARM_RENT_EUR: "abc" })).toThrow(/MAX_WARM_RENT_EUR/);
    expect(() => loadSettings({ ...vars, AVAILABLE_BY: "31.01.2027" })).toThrow(/AVAILABLE_BY/);
    expect(() => loadSettings({ ...vars, ANCHORS: [] })).toThrow(/ANCHORS/);
    expect(() => loadSettings({ ...vars, ROUTER_URL: "http://insecure" })).toThrow(/ROUTER_URL/);
  });
});

describe("schedule", () => {
  it("matches the cron trigger in wrangler.jsonc", () => {
    expect(wranglerConfig).toContain(`"crons": ["${SCHEDULE.cron}"]`);
  });

  it("predicts the next hourly run inside the window", () => {
    expect(nextScheduledRun(new Date("2026-10-22T12:34:00Z")).toISOString()).toBe("2026-10-22T13:00:00.000Z");
    expect(nextScheduledRun(new Date("2026-10-22T22:10:00Z")).toISOString()).toBe("2026-10-23T05:00:00.000Z");
    expect(nextScheduledRun(new Date("2026-10-22T02:00:00Z")).toISOString()).toBe("2026-10-22T05:00:00.000Z");
    expect(nextScheduledRun(new Date("2026-10-22T04:59:00Z")).toISOString()).toBe("2026-10-22T05:00:00.000Z");
  });
});
