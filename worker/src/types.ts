export type ListingType = "wg_room" | "studio" | "flat" | "house" | "unknown";

/** What one search-result card tells us. Lister identity is deliberately not parsed. Facts a source
 *  only publishes on its detail page are null here (see `Source.detailOnly`). */
export interface ScrapedListing {
  externalId: string;
  url: string;
  title: string | null;
  listingType: ListingType;
  kindLabel: string | null; // "3er WG", "2-Zimmer-Wohnung"
  place: string | null; // "Garching b. München", "München Freimann"
  street: string | null;
  lat: number | null;
  lng: number | null;
  priceListed: number | null; // card figure; basis ambiguous, resolved by the detail page
  sizeSqm: number | null;
  availableFrom: string | null; // ISO date; null = available now
  availableTo: string | null; // ISO date; set for temporary sublets
  swap: boolean; // flat swap (Tausch): needs a flat of the user's own in exchange
}

export interface AnchorTime {
  label: string;
  minutes: number;
  km: number;
}

export interface BikeTime {
  minutes: number; // slowest anchor: the commute that must fit the limit
  km: number;
  source: "valhalla" | "estimate";
  perAnchor: AnchorTime[];
  stop: AnchorTime | null; // nearest transit stop by bike, null when no stops are configured
}

/** The facts the filter decides on. */
export interface ListingFacts {
  priceListed: number | null;
  priceWarm: number | null;
  priceCold: number | null;
  sizeSqm: number | null;
  availableFrom: string | null;
  availableTo: string | null;
  bikeMinutes: number | null;
  stopMinutes: number | null;
  swap: boolean;
}

export type Stage = "pending_detail" | "matched" | "rejected";
export type Triage = "new" | "seen" | "interested" | "dismissed";
export const TRIAGE_VALUES: readonly Triage[] = ["new", "seen", "interested", "dismissed"];

export type Job =
  // `stream` is absent on messages enqueued before Kleinanzeigen was added (WG-Gesucht only).
  | { kind: "search"; runId: string; stream?: string; page: number; url: string }
  | { kind: "detail"; runId: string; listingId: number };
