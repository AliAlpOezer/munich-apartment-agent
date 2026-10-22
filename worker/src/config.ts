export interface Anchor {
  label: string; // short, shown next to bike minutes ("TUM")
  name: string;
  lat: number;
  lng: number;
}

export interface Criteria {
  anchors: Anchor[];
  maxWarmRentEur: number;
  minSizeSqm: number;
  availableBy: string; // ISO date: latest acceptable move-in
  minStayDays: number; // shorter temporary sublets are rejected
  maxBikeMinutes: number;
  bikeSpeedKmh: number;
}

export interface Settings {
  criteria: Criteria;
  maxPages: number;
  manualRunCooldownMinutes: number;
  routerUrl: string;
}

/** Mirrors `triggers.crons` in wrangler.jsonc ("0 5-22 * * *"); a test keeps the two in sync. */
export const SCHEDULE = { cron: "0 5-22 * * *", fromHourUtc: 5, toHourUtc: 22 } as const;

export function nextScheduledRun(now: Date): Date {
  const next = new Date(now);
  next.setUTCMinutes(0, 0, 0);
  next.setUTCHours(next.getUTCHours() + 1);
  if (next.getUTCHours() > SCHEDULE.toHourUtc) next.setUTCDate(next.getUTCDate() + 1);
  if (next.getUTCHours() > SCHEDULE.toHourUtc || next.getUTCHours() < SCHEDULE.fromHourUtc) {
    next.setUTCHours(SCHEDULE.fromHourUtc);
  }
  return next;
}

function num(env: Record<string, unknown>, key: string, min: number, max: number): number {
  const v = Number(env[key]);
  if (!Number.isFinite(v) || v < min || v > max) {
    throw new Error(`config ${key}=${JSON.stringify(env[key])} must be a number in [${min}, ${max}]`);
  }
  return v;
}

function isoDate(env: Record<string, unknown>, key: string): string {
  const v = env[key];
  if (typeof v !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(v) || Number.isNaN(Date.parse(v))) {
    throw new Error(`config ${key}=${JSON.stringify(v)} must be an ISO date (yyyy-mm-dd)`);
  }
  return v;
}

function anchors(raw: unknown): Anchor[] {
  const list = typeof raw === "string" ? JSON.parse(raw) : raw;
  if (!Array.isArray(list) || list.length === 0) throw new Error("config ANCHORS must be a non-empty array");
  return list.map((a, i) => {
    const ok =
      a && typeof a.label === "string" && typeof a.name === "string" &&
      Number.isFinite(a.lat) && Number.isFinite(a.lng);
    if (!ok) throw new Error(`config ANCHORS[${i}] needs label, name, lat, lng`);
    return { label: a.label, name: a.name, lat: a.lat, lng: a.lng };
  });
}

/** Validate the wrangler vars once per invocation; a bad deploy fails loudly, not silently. */
export function loadSettings(env: Record<string, unknown>): Settings {
  const routerUrl = String(env.ROUTER_URL ?? "");
  if (!/^https:\/\//.test(routerUrl)) throw new Error("config ROUTER_URL must be an https URL");
  return {
    criteria: {
      anchors: anchors(env.ANCHORS),
      maxWarmRentEur: num(env, "MAX_WARM_RENT_EUR", 50, 10_000),
      minSizeSqm: num(env, "MIN_SIZE_SQM", 0, 500),
      availableBy: isoDate(env, "AVAILABLE_BY"),
      minStayDays: num(env, "MIN_STAY_DAYS", 0, 3650),
      maxBikeMinutes: num(env, "MAX_BIKE_MINUTES", 1, 240),
      bikeSpeedKmh: num(env, "BIKE_SPEED_KMH", 5, 45),
    },
    maxPages: num(env, "MAX_PAGES", 1, 20),
    manualRunCooldownMinutes: num(env, "MANUAL_RUN_COOLDOWN_MINUTES", 0, 1440),
    routerUrl: routerUrl.replace(/\/+$/, ""),
  };
}
