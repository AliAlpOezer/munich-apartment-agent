// Kleinanzeigen adapter: one search stream per category, card scanning, detail facts.
// Markup from live pages captured 2026-10-23; a layout change should only touch this file.
//
// Pages are 300-750 KB against a 10 ms CPU budget, and HTMLRewriter cost about 7x a string scan on
// them (34.6 vs 4.8 ms locally, 2026-10-23). So the page is decoded once (natively; decoding only its
// second half via a JS byte search measured slower on Cloudflare), the main result list is cut out
// by its ids, and each card is scanned with small patterns. Regexes run only over the windows they
// need. Card texts are classified by shape, not by their Tailwind classes:
//   article[data-adid][data-href]   -> id, detail URL
//   <span>85375 Neufahrn</span>     -> place (zip + district); "(7 km)" is the distance to the centre
//   <h3>                            -> title
//   <p>9 m² · 3 Zi. · …</p>         -> facts line; "Gesuch · …" marks a wanted ad (skipped)
//   <p>470 €</p>                    -> listed price; a struck-through <p> after it is the old price
// Cards carry no coordinates and no dates: the detail page has og:latitude/longitude and
// "Verfügbar ab". Ads from other places follow the results in #srchrslt-adtable-altads (skipped).

import { haversineKm } from "./bike";
import type { Criteria } from "./config";
import { cleanText, MIN_PLAUSIBLE_RENT_EUR, parseGermanDates, parseGermanNumber, stripTags } from "./html";
import { ListingGone, mentionsSwap, searchArea, type DetailFacts, type SearchPage, type Source } from "./sources";
import type { ListingType, ScrapedListing } from "./types";

const ORIGIN = "https://www.kleinanzeigen.de";
// "Garching b München - Kr. München" from /s-ort-empfehlungen.json?query=Garching; the centre is
// what the search page reports (lat/lon in its tracking data), and radii are measured from it.
const LOCATION = { id: 6303, slug: "garching-b-muenchen", lat: 48.2488, lng: 11.6511 };

interface Category {
  key: string;
  id: number;
  path: string;
  label: string;
  listingType: ListingType;
  /** The listed price is the Kaltmiete (flats and houses); in "Auf Zeit & WG" its basis varies. */
  priceIsCold: boolean;
}

const CATEGORIES: readonly Category[] = [
  { key: "wohnung", id: 203, path: "s-wohnung-mieten", label: "Wohnung", listingType: "flat", priceIsCold: true },
  { key: "wg", id: 199, path: "s-auf-zeit-wg", label: "WG / auf Zeit", listingType: "wg_room", priceIsCold: false },
  { key: "haus", id: 205, path: "s-haus-mieten", label: "Haus", listingType: "house", priceIsCold: true },
];

const SOURCE_ID = "kleinanzeigen";

// In "Auf Zeit & WG" the area is the room's or the whole flat's, as the lister likes ("9 m² · 3 Zi."
// vs "200 m² · 10 Zi." on the same page, 2026-10-23). With several rooms and more than this, it is
// the flat's: shown in the label, not used as the room size.
const MAX_ROOM_SQM = 40;

function roomSize(cat: Category | undefined, area: number | null, rooms: number | null): number | null {
  const flatArea = cat?.key === "wg" && area !== null && area > MAX_ROOM_SQM && rooms !== null && rooms > 1;
  return flatArea ? null : area;
}

/** The derived radius around the anchors, widened by the site centre's offset from them, so the
 *  site's circle contains ours. Whole km, as the site takes it. */
export function searchRadiusKm(c: Criteria): number {
  const area = searchArea(c);
  return Math.ceil(area.radiusM / 1000 + haversineKm(area.lat, area.lng, LOCATION.lat, LOCATION.lng));
}

/** Page 0 of one category. The price cap is safe server-side: the listed price is never above warm. */
export function buildSearchUrl(c: Criteria, cat: Category): string {
  const price = `preis::${Math.floor(c.maxWarmRentEur)}`;
  return `${ORIGIN}/${cat.path}/${LOCATION.slug}/${price}/c${cat.id}l${LOCATION.id}r${searchRadiusKm(c)}`;
}

/** Same search, any page: the path without its "seite:N/" segment. */
const searchKey = (path: string) => path.replace(/\/seite:\d+(?=\/)/, "");

function parsePageUrls(html: string, pageUrl: string): Map<number, string> {
  const key = searchKey(new URL(pageUrl).pathname);
  const out = new Map<number, string>();
  for (const [, path, n] of html.matchAll(/href="(\/s-[^"?#]*\/seite:(\d+)\/[^"?#]*)"/g)) {
    const index = Number(n) - 1; // "seite:2" is the second page, index 1
    if (index >= 1 && searchKey(path) === key && !out.has(index)) out.set(index, `${ORIGIN}${path}`);
  }
  return out;
}

const PRICE_RE = /^(?:\d[\d.]*(?:,\d+)?\s*€(?:\s*VB)?|VB|Zu verschenken)$/;
const FACT_RE = /^(?:Gesuch|\d[\d.]*(?:,\d+)?\s*m²|\d+(?:,\d+)?\s*Zi\.)$/;

/** "9 m² · 3 Zi. · Online-Besichtigung": short segments, at least one of them a known fact. */
function isFactsLine(text: string): boolean {
  const parts = text.split("·").map((s) => s.trim());
  return parts.every((s) => s.length > 0 && s.length <= 40) && parts.some((s) => FACT_RE.test(s));
}

function parseCard(card: string, cat: Category): ScrapedListing | null {
  const id = /^<article\b[^>]*\bdata-adid="(\d+)"/.exec(card)?.[1];
  const href = /^<article\b[^>]*\bdata-href="(\/s-anzeige\/[^"]+)"/.exec(card)?.[1];
  if (!id || !href) return null;
  const body = card.replace(/<script\b[\s\S]*?<\/script>|<svg\b[\s\S]*?<\/svg>/g, "");
  const paragraphs = [...body.matchAll(/<p\b([^>]*)>([\s\S]*?)<\/p>/g)].map(([, attrs, inner]) => ({
    struck: /line-through/.test(attrs), text: cleanText(stripTags(inner)),
  }));
  const facts = paragraphs.find((p) => isFactsLine(p.text))?.text ?? "";
  if (/^Gesuch\b/.test(facts)) return null; // someone looking for a place, not an offer

  const spans = [...body.matchAll(/<span\b[^>]*>([^<]*)<\/span>/g)].map(([, t]) => cleanText(t));
  const title = cleanText(stripTags(/<h3\b[^>]*>([\s\S]*?)<\/h3>/.exec(body)?.[1] ?? "")) || null;
  const priceText = paragraphs.find((p) => !p.struck && PRICE_RE.test(p.text))?.text ?? null;
  const price = parseGermanNumber(priceText);
  const rooms = /(\d+(?:,\d+)?)\s*Zi\./.exec(facts)?.[1] ?? null;
  const area = parseGermanNumber(/(\d[\d.]*(?:,\d+)?)\s*m²/.exec(facts)?.[1]);
  const size = roomSize(cat, area, parseGermanNumber(rooms));
  return {
    externalId: id,
    url: `${ORIGIN}${href}`,
    title,
    listingType: cat.listingType === "flat" && rooms === "1" ? "studio" : cat.listingType,
    kindLabel: [cat.label, rooms && `${rooms} Zi.`, area !== size && `${area} m² flat`].filter(Boolean).join(", "),
    place: spans.find((t) => /^\d{5}\s+\S/.test(t)) ?? null,
    street: null,
    lat: null,
    lng: null,
    priceListed: price !== null && price >= MIN_PLAUSIBLE_RENT_EUR ? price : null,
    sizeSqm: size,
    availableFrom: null,
    availableTo: null,
    swap: mentionsSwap(title),
  };
}

/** The text of the element whose opening tag carries `idAttr`, found with a native indexOf. */
function elementText(html: string, idAttr: string): string {
  const at = html.indexOf(idAttr);
  return at < 0 ? "" : cleanText(/^[^>]*>([^<]*)</.exec(html.slice(at, at + 2_000))?.[1] ?? "");
}

export function parseSearchPage(html: string, pageUrl: string, cat: Category): SearchPage {
  const zeroResults = /keine Ergebnisse/i.test(elementText(html, 'id="srp-breadcrumb-summary"'));
  const start = html.indexOf('id="srchrslt-adtable"');
  if (start < 0) return { listings: [], pageUrls: new Map(), zeroResults, emptyHint: "no result list" };
  const altads = html.indexOf('id="srchrslt-adtable-altads"', start);
  const results = html.slice(start, altads < 0 ? undefined : altads);
  // Pagination sits between the main list's last card and the end of <main>.
  const pagerAt = start + Math.max(0, results.lastIndexOf("</article>"));
  const mainEnd = html.indexOf("</main>", pagerAt);
  const pager = html.slice(pagerAt, mainEnd < 0 ? pagerAt + 100_000 : mainEnd);

  const seen = new Set<string>();
  const listings: ScrapedListing[] = [];
  const cards = results.split("<article ").slice(1);
  for (const part of cards) {
    const end = part.indexOf("</article>");
    const listing = parseCard(`<article ${end < 0 ? part : part.slice(0, end)}`, cat);
    if (listing && !seen.has(listing.externalId)) {
      seen.add(listing.externalId);
      listings.push(listing);
    }
  }
  return {
    listings,
    pageUrls: parsePageUrls(pager, pageUrl),
    zeroResults,
    emptyHint: `${cards.length} cards in the result list`,
  };
}

// --- detail page -----------------------------------------------------------------------------
// Attributes are <li class="addetailslist--detail">Label<span class="addetailslist--detail--value">
// Value</span></li> in #viewad-details. The ad-targeting JSON earlier in the page is not used: it
// disagreed with the visible list on a live page (Wohnflaeche 160 vs 9 m² shown).

const MONTHS = ["januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september",
  "oktober", "november", "dezember"];

/** "November 2026" -> "2026-11-01", "01.11.2026" -> "2026-11-01", anything else -> null. */
export function parseAvailableFrom(text: string): string | null {
  const exact = parseGermanDates(text)[0];
  if (exact) return exact;
  const m = /([a-zä]+)\s+(\d{4})/i.exec(text);
  const month = m ? MONTHS.indexOf(m[1].toLowerCase()) : -1;
  return m && month >= 0 ? `${m[2]}-${String(month + 1).padStart(2, "0")}-01` : null;
}

function detailAttributes(html: string): Map<string, string> {
  const start = html.indexOf('id="viewad-details"');
  const out = new Map<string, string>();
  if (start < 0) return out;
  const re = /<li class="addetailslist--detail">([\s\S]*?)<span class="addetailslist--detail--value"\s*>([\s\S]*?)<\/span>/g;
  for (const [, label, value] of html.slice(start, start + 20_000).matchAll(re)) {
    out.set(cleanText(stripTags(label)).toLowerCase(), cleanText(stripTags(value)));
  }
  return out;
}

const plausibleRent = (n: number | null) => (n !== null && n >= MIN_PLAUSIBLE_RENT_EUR ? n : null);

export function parseDetail(html: string, url: string): DetailFacts {
  if (!html.includes('id="viewad-title"')) throw new Error("not a listing page (no #viewad-title)");
  const meta = (prop: string) => Number(new RegExp(`property="og:${prop}" content="(-?[\\d.]+)"`).exec(html)?.[1]);
  const lat = meta("latitude");
  const lng = meta("longitude");
  const attrs = detailAttributes(html);
  const money = (label: string) => plausibleRent(parseGermanNumber(attrs.get(label)));

  const catId = Number(/\/\d+-(\d+)-\d+$/.exec(new URL(url).pathname)?.[1]);
  const cat = CATEGORIES.find((c) => c.id === catId);
  const listed = plausibleRent(parseGermanNumber(/id="viewad-price"[^>]*>([^<]*)</.exec(html)?.[1]));
  const cold = money("kaltmiete") ?? (cat?.priceIsCold ? listed : null);
  const extras = ["nebenkosten", "heizkosten"].map((l) => parseGermanNumber(attrs.get(l)));
  const extra = extras.some((n) => n !== null) ? extras.reduce<number>((s, n) => s + (n ?? 0), 0) : null;
  const warm = money("warmmiete") ?? (cold !== null && extra !== null ? cold + extra : null);
  const swapAttr = attrs.get("tauschangebot");

  return {
    warm,
    cold,
    position: Number.isFinite(lat) && Number.isFinite(lng) && (lat !== 0 || lng !== 0) ? { lat, lng } : null,
    availableFrom: parseAvailableFrom(attrs.get("verfügbar ab") ?? ""),
    sizeSqm: roomSize(cat, parseGermanNumber(attrs.get("wohnfläche")), parseGermanNumber(attrs.get("zimmer"))),
    swap: swapAttr !== undefined && !/kein/i.test(swapAttr),
  };
}

export const kleinanzeigen: Source = {
  id: SOURCE_ID,
  label: "Kleinanzeigen",
  origin: ORIGIN,
  detailOnly: { position: true, availability: true },
  streams: (c) => CATEGORIES.map((cat) => ({ stream: `${SOURCE_ID}:${cat.key}`, url: buildSearchUrl(c, cat) })),
  async parseSearchPage(res, url) {
    const cat = CATEGORIES.find((c) => new URL(url).pathname.includes(`/c${c.id}l`));
    if (!cat) throw new Error(`no known category in ${url}`);
    return parseSearchPage(await res.text(), url, cat);
  },
  async parseDetail(res, url) {
    // A deleted ad redirects away from its /s-anzeige/ page.
    if (res.redirected && !new URL(res.url).pathname.startsWith("/s-anzeige/")) throw new ListingGone(url);
    return parseDetail(await res.text(), url);
  },
};
