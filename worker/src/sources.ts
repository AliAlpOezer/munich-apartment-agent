// The seam between the pipeline and a listing site. An adapter turns one site's pages into facts;
// everything that decides (filter, routing, stage) stays source-agnostic in the pipeline.

import { haversineKm, type Point } from "./bike";
import type { Criteria } from "./config";
import type { ScrapedListing } from "./types";

/** One result list a run walks page by page, e.g. one category of one site. */
export interface SearchStream {
  stream: string; // "<source id>" or "<source id>:<category>"; the source is the part before ":"
  url: string; // page 0
}

export interface SearchPage {
  listings: ScrapedListing[];
  /** Further result pages linked from this one, by page index (0-based). */
  pageUrls: Map<number, string>;
  /** The page explicitly says the search has no results. */
  zeroResults: boolean;
  /** Why zero parsed cards looks like a layout change rather than an empty search. */
  emptyHint: string;
}

/** What a detail page adds. Optional fields are left out by sources whose cards already carry them. */
export interface DetailFacts {
  warm: number | null;
  cold: number | null;
  position?: Point | null;
  availableFrom?: string | null;
  sizeSqm?: number | null;
  swap?: boolean;
}

export interface Source {
  id: string; // stored in listings.source
  label: string;
  origin: string; // https origin every fetched URL must be on
  /** Facts only the detail page has. A re-decision from the card takes them from the stored row. */
  detailOnly: { position: boolean; availability: boolean };
  streams(c: Criteria): SearchStream[];
  parseSearchPage(res: Response, url: string): Promise<SearchPage>;
  parseDetail(res: Response, url: string): Promise<DetailFacts>;
}

/** The detail page shows the listing was taken down (beyond an HTTP 404/410). */
export class ListingGone extends Error {
  constructor(url: string) {
    super(`listing gone: ${url}`);
  }
}

export function isOnOrigin(url: string, origin: string): boolean {
  try {
    const u = new URL(url);
    return u.protocol === "https:" && u.origin === origin;
  } catch {
    return false;
  }
}

/** Smallest circle around the anchors' centre that contains every point reachable in time, by
 *  bike to the anchors or by a short ride to a transit stop. A route is never shorter than the
 *  straight line, so this is a guaranteed superset. */
export function searchArea(c: Criteria): { lat: number; lng: number; radiusM: number } {
  const lat = c.anchors.reduce((s, a) => s + a.lat, 0) / c.anchors.length;
  const lng = c.anchors.reduce((s, a) => s + a.lng, 0) / c.anchors.length;
  const farthest = (places: Criteria["anchors"]) =>
    Math.max(0, ...places.map((p) => haversineKm(lat, lng, p.lat, p.lng)));
  const bikeKm = farthest(c.anchors) + (c.bikeSpeedKmh * c.maxBikeMinutes) / 60;
  const transitKm = c.transitStops.length
    ? farthest(c.transitStops) + (c.bikeSpeedKmh * c.maxBikeToStopMinutes) / 60
    : 0;
  return { lat, lng, radiusM: Math.ceil((Math.max(bikeKm, transitKm) * 1000) / 100) * 100 };
}

// "Wohnungsswap", "TAUSCHWOHNUNG", "Wohnungstausch", "Tausche 2 gegen 3 Zimmer"; not "kein Tausch".
const SWAP_RE = /wohnungs?tausch|tauschwohnung|wohnungsswap|\bswap\b|(?<!kein(?:en)?\s)\btausch(?:e|en)?\b/i;

/** A swap ad says so in its title; detail attributes, where a site has them, can add to this. */
export function mentionsSwap(text: string | null): boolean {
  return text !== null && SWAP_RE.test(text);
}
