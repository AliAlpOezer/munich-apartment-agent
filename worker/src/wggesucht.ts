// WG-Gesucht adapter: search URL, search-page parsing, detail-page cost parsing.
// Selectors come from live pages captured 2026-10-22; a layout change should only touch this file.
//
// Search card anatomy (a.wgg-list-card[data-id]):
//   aria-label                       -> title
//   href                             -> detail URL, listing type from its path
//   .price-row .card-main-text       -> listed rent ("650 €")
//   .ad-subtitle[title]              -> "3er WG · Garching b. München · Maier-Leibnitz-Straße"
//   .size-value                      -> "13 m²"
//   .middle-row                      -> availability ("01.11.2026" or "01.11.2026 - 31.03.2027")
//   class campaign_click             -> sponsored placement, not a search result (skipped)
// Coordinates are not on the card: the page's map config carries `markers: [{lat, lng, offer_id}]`.

import type { Criteria } from "./config";
import { haversineKm } from "./bike";
import { cleanText, decodeEntities, parseGermanDates, parseGermanNumber, rewrite } from "./html";
import type { ListingType, ScrapedListing } from "./types";

export const SOURCE = "wg_gesucht";
const ORIGIN = "https://www.wg-gesucht.de";
const MUNICH_CITY_ID = 90;
const SEARCH_PATH = `/wg-zimmer-und-1-zimmer-wohnungen-und-wohnungen-und-haeuser-in-Muenchen.${MUNICH_CITY_ID}.0+1+2+3.1.0.html`;
// A real monthly rent is never a couple of euros; listers sometimes type placeholders like "2 €".
const MIN_PLAUSIBLE_RENT_EUR = 50;

export function isSourceUrl(url: string): boolean {
  try {
    const u = new URL(url);
    return u.protocol === "https:" && u.hostname === "www.wg-gesucht.de";
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

/** Page-0 search: all four categories, rent capped server-side, radius around the anchors.
 *  Param format mirrors the site's own pagination links. Size and dates are filtered locally. */
export function buildSearchUrl(c: Criteria): string {
  const area = searchArea(c);
  const params = [
    "categories%5B0%5D=0", "categories%5B1%5D=1", "categories%5B2%5D=2", "categories%5B3%5D=3",
    "rent_types%5B0%5D=2", "rent_types%5B1%5D=1", "rent_types%5B2%5D=3",
    `city_id=${MUNICH_CITY_ID}`, "sort_column=0", "sort_order=0", "noDeact=1",
    `rMax=${Math.floor(c.maxWarmRentEur)}`,
    `radAdd=${encodeURIComponent("Garching bei München")}`,
    `radLat=${area.lat.toFixed(6)}`, `radLng=${area.lng.toFixed(6)}`, `radDis=${area.radiusM}`,
  ];
  return `${ORIGIN}${SEARCH_PATH}?${params.join("&")}`;
}

export interface SearchPage {
  listings: ScrapedListing[];
  markerCount: number;
  /** Further result pages linked from this one, by page index (1-based beyond page 0). */
  pageUrls: Map<number, string>;
  /** The page explicitly says the search has no results. */
  zeroResults: boolean;
}

function listingTypeFromHref(href: string): ListingType {
  if (href.includes("/wg-zimmer-in-")) return "wg_room";
  if (href.includes("/1-zimmer-wohnungen-in-")) return "studio";
  if (href.includes("/haeuser-in-")) return "house";
  if (href.includes("/wohnungen-in-")) return "flat";
  return "unknown";
}

/** The JSON array that follows `key` in an inline script, by bracket matching. */
export function extractJsonArray(html: string, key: string): unknown[] | null {
  const at = html.indexOf(key);
  if (at < 0) return null;
  const start = html.indexOf("[", at + key.length);
  if (start < 0) return null;
  let depth = 0;
  let inString = false;
  for (let i = start; i < html.length; i++) {
    const ch = html[i];
    if (inString) {
      if (ch === "\\") i++;
      else if (ch === '"') inString = false;
    } else if (ch === '"') inString = true;
    else if (ch === "[") depth++;
    else if (ch === "]" && --depth === 0) {
      try {
        const parsed = JSON.parse(html.slice(start, i + 1));
        return Array.isArray(parsed) ? parsed : null;
      } catch {
        return null;
      }
    }
  }
  return null;
}

function parseMarkers(html: string): Map<string, { lat: number; lng: number }> {
  const out = new Map<string, { lat: number; lng: number }>();
  for (const m of extractJsonArray(html, "markers:") ?? []) {
    const { offer_id, lat, lng } = (m ?? {}) as { offer_id?: unknown; lat?: unknown; lng?: unknown };
    if (offer_id != null && typeof lat === "number" && typeof lng === "number") {
      out.set(String(offer_id), { lat, lng });
    }
  }
  return out;
}

function parsePageUrls(html: string): Map<number, string> {
  const out = new Map<number, string>();
  const re = /href="(https:\/\/www\.wg-gesucht\.de\/wg-zimmer-und-1-zimmer-wohnungen-und-wohnungen-und-haeuser-in-[^".]+\.\d+\.0\+1\+2\+3\.1\.(\d+)\.html\?[^"]*)"/g;
  for (const [, href, page] of html.matchAll(re)) {
    const url = decodeEntities(href);
    const n = Number(page);
    if (n >= 1 && url.includes("radLat=") && !out.has(n)) out.set(n, url);
  }
  return out;
}

interface CardDraft {
  id: string;
  href: string;
  title: string;
  sponsored: boolean;
  subtitle: string;
  priceEls: number;
  priceText: string;
  sizeText: string;
  middleText: string;
}

export async function parseSearchPage(html: string): Promise<SearchPage> {
  const drafts: CardDraft[] = [];
  let cur: CardDraft | null = null;
  const inCard = (fn: (c: CardDraft, text: string) => void) => ({
    text(t: Text) {
      if (cur) fn(cur, t.text);
    },
  });

  await rewrite(
    html,
    new HTMLRewriter()
      .on("a.wgg-list-card[data-id]", {
        element(el) {
          const draft: CardDraft = {
            id: el.getAttribute("data-id") ?? "",
            href: el.getAttribute("href") ?? "",
            title: el.getAttribute("aria-label") ?? "",
            sponsored: /\bcampaign_click\b/.test(el.getAttribute("class") ?? ""),
            subtitle: "", priceEls: 0, priceText: "", sizeText: "", middleText: "",
          };
          cur = draft;
          el.onEndTag(() => {
            drafts.push(draft);
            cur = null;
          });
        },
      })
      .on("a.wgg-list-card .price-row .card-main-text", {
        element() {
          if (cur) cur.priceEls++;
        },
        text(t) {
          if (cur && cur.priceEls === 1) cur.priceText += t.text;
        },
      })
      .on("a.wgg-list-card .ad-subtitle", {
        element(el) {
          if (cur) cur.subtitle = el.getAttribute("title") ?? "";
        },
      })
      .on("a.wgg-list-card .size-value", inCard((c, t) => (c.sizeText += t)))
      .on("a.wgg-list-card .middle-row", inCard((c, t) => (c.middleText += t))),
  );

  const markers = parseMarkers(html);
  const seen = new Set<string>();
  const listings: ScrapedListing[] = [];
  for (const d of drafts) {
    if (d.sponsored || !/^\d+$/.test(d.id) || seen.has(d.id)) continue;
    seen.add(d.id);
    const href = decodeEntities(d.href);
    const [kind, place, street] = cleanText(d.subtitle).split("·").map((s) => s.trim() || null);
    const price = parseGermanNumber(cleanText(d.priceText));
    const dates = parseGermanDates(cleanText(d.middleText));
    const pos = markers.get(d.id);
    listings.push({
      externalId: d.id,
      url: href.startsWith("http") ? href : `${ORIGIN}${href}`,
      title: cleanText(d.title) || null,
      listingType: listingTypeFromHref(href),
      kindLabel: kind ?? null,
      place: place ?? null,
      street: street ?? null,
      lat: pos?.lat ?? null,
      lng: pos?.lng ?? null,
      priceListed: price !== null && price >= MIN_PLAUSIBLE_RENT_EUR ? price : null,
      sizeSqm: parseGermanNumber(cleanText(d.sizeText)),
      availableFrom: dates[0] ?? null,
      availableTo: dates[1] ?? null,
    });
  }

  return {
    listings,
    markerCount: markers.size,
    pageUrls: parsePageUrls(html),
    zeroResults: /\b0 Angebote\b/.test(html),
  };
}

// --- detail page costs -------------------------------------------------------------------------
// Costs are label/value pairs: key facts (span.key_fact_detail + .key_fact_value) and the "Kosten"
// panel (span.section_panel_detail + span.section_panel_value). Each value pairs with the closest
// preceding unpaired label, so labels without values (other panels) never shift the pairing.

type CostKind = "warm" | "cold" | "extra";
const COST_KEYS: [string, CostKind][] = [
  ["gesamtmiete", "warm"],
  ["warmmiete", "warm"],
  ["kaltmiete", "cold"],
  ["nebenkosten", "extra"],
  ["heizkosten", "extra"],
  ["sonstige", "extra"],
  ["miete", "cold"], // generic base rent: must stay last
];

export function classifyCostLabel(label: string): CostKind | null {
  const l = label.toLowerCase();
  if (l.includes("kaution") || l.includes("ablös") || l.includes("ablos")) return null;
  return COST_KEYS.find(([sub]) => l.includes(sub))?.[1] ?? null;
}

interface Token {
  role: "label" | "value";
  text: string;
}

function pairTokens(tokens: Token[]): [string, number][] {
  const pairs: [string, number][] = [];
  let label: string | null = null;
  for (const t of tokens) {
    if (t.role === "label") label = cleanText(t.text);
    else if (label !== null) {
      const n = parseGermanNumber(cleanText(t.text));
      if (n !== null) pairs.push([label, n]);
      label = null;
    }
  }
  return pairs;
}

export interface DetailCosts {
  warm: number | null;
  cold: number | null;
}

export async function parseDetailCosts(html: string | Response): Promise<DetailCosts> {
  const families: Record<"fact" | "panel", Token[]> = { fact: [], panel: [] };
  const capture = (family: "fact" | "panel", role: Token["role"]) => ({
    element() {
      families[family].push({ role, text: "" });
    },
    text(t: Text) {
      const list = families[family];
      list[list.length - 1].text += t.text;
    },
  });

  await rewrite(
    html,
    new HTMLRewriter()
      .on("span.key_fact_detail", capture("fact", "label"))
      .on(".key_fact_value", capture("fact", "value"))
      .on("span.section_panel_detail", capture("panel", "label"))
      .on("span.section_panel_value", capture("panel", "value")),
  );

  let warm: number | null = null;
  let cold: number | null = null;
  let extras = 0;
  let seenExtra = false;
  for (const [label, value] of [...pairTokens(families.fact), ...pairTokens(families.panel)]) {
    const kind = classifyCostLabel(label);
    if ((kind === "warm" || kind === "cold") && value < MIN_PLAUSIBLE_RENT_EUR) continue;
    if (kind === "warm") warm ??= value;
    else if (kind === "cold") cold ??= value;
    else if (kind === "extra") {
      extras += value;
      seenExtra = true;
    }
  }
  if (warm === null && cold !== null && seenExtra) warm = cold + extras;
  return { warm, cold };
}
