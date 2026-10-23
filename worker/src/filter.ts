// Pure match rules: no I/O, no model. Permissive on missing data: an unknown value never rejects,
// because a parse miss is likelier than a free flat. The same rules run twice: on the search card
// (rent is the card figure, a lower bound) and again once the detail page resolves the warm rent.

import type { Criteria } from "./config";
import type { ListingFacts } from "./types";

export interface Verdict {
  matched: boolean;
  reasons: string[];
}

const DAY_MS = 86_400_000;

/** Best figure to hold against the warm-rent cap: warm, else cold, else the card figure. The
 *  fallbacks are lower bounds (warm >= cold), so a too-low guess is corrected by the detail page. */
export function effectiveWarmRent(f: ListingFacts): number | null {
  return f.priceWarm ?? f.priceCold ?? f.priceListed;
}

export function evaluate(f: ListingFacts, c: Criteria, today: string): Verdict {
  const reasons: string[] = [];

  const rent = effectiveWarmRent(f);
  if (rent !== null && rent > c.maxWarmRentEur) {
    reasons.push(`rent ${Math.round(rent)} € > ${c.maxWarmRentEur} €`);
  }

  if (f.sizeSqm !== null && f.sizeSqm < c.minSizeSqm) {
    reasons.push(`size ${f.sizeSqm} m² < ${c.minSizeSqm} m²`);
  }

  // No date means "ab sofort": available now, which is inside a window that starts today.
  if (f.availableFrom !== null && f.availableFrom > c.availableBy) {
    reasons.push(`available from ${f.availableFrom}, after ${c.availableBy}`);
  }

  if (f.availableTo !== null) {
    const start = f.availableFrom !== null && f.availableFrom > today ? f.availableFrom : today;
    const stayDays = Math.round((Date.parse(f.availableTo) - Date.parse(start)) / DAY_MS);
    if (stayDays < c.minStayDays) {
      reasons.push(`temporary: only ${Math.max(stayDays, 0)} days (until ${f.availableTo})`);
    }
  }

  // Commute: e-bike to every anchor, or a short ride to the transit line. Unknown keeps.
  const bikeOk = f.bikeMinutes === null || f.bikeMinutes <= c.maxBikeMinutes;
  const transitOk = f.stopMinutes !== null && f.stopMinutes <= c.maxBikeToStopMinutes;
  if (!bikeOk && !transitOk) {
    const transit = f.stopMinutes !== null
      ? `; ${Math.round(f.stopMinutes)} min to the ${c.transitLine} > ${c.maxBikeToStopMinutes} min`
      : "";
    reasons.push(`bike ${Math.round(f.bikeMinutes!)} min > ${c.maxBikeMinutes} min${transit}`);
  }

  return { matched: reasons.length === 0, reasons };
}
