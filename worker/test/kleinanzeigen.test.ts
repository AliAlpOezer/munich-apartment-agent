import { describe, expect, it } from "vitest";
import { haversineKm } from "../src/bike";
import {
  buildSearchUrl, kleinanzeigen, parseAvailableFrom, parseDetail, parseSearchPage, searchRadiusKm,
} from "../src/kleinanzeigen";
import { ListingGone, mentionsSwap } from "../src/sources";
import detailFlat from "./fixtures/ka-detail-flat.html?raw";
import detailShort from "./fixtures/ka-detail-short.html?raw";
import detailSwap from "./fixtures/ka-detail-swap.html?raw";
import emptyPage from "./fixtures/ka-search-empty.html?raw";
import searchPage from "./fixtures/ka-search.html?raw";
import { html, settings } from "./helpers";

const ORIGIN = "https://www.kleinanzeigen.de";
// The URL the fixture was captured from (radius 15 km at the time).
const PAGE_URL = `${ORIGIN}/s-auf-zeit-wg/garching-b-muenchen/preis::650/c199l6303r15`;
const WG = { key: "wg", id: 199, path: "s-auf-zeit-wg", label: "WG / auf Zeit", listingType: "wg_room", priceIsCold: false } as const;
const detailUrl = (id: string, cat: number) => `${ORIGIN}/s-anzeige/slug/${id}-${cat}-6620`;

describe("parseSearchPage (live layout, 2026-10-23)", () => {
  const page = parseSearchPage(searchPage, PAGE_URL, WG);

  it("keeps offers in the result list, skipping wanted ads, repeats and ads from other places", () => {
    expect(page.listings.map((l) => l.externalId)).toEqual([
      "3496292417", "3546382872", "3545322242", "3546651796", "3536207850", "3335842751",
    ]);
    expect(page.zeroResults).toBe(false);
  });

  it("classifies card texts by shape", () => {
    expect(page.listings[1]).toEqual({
      externalId: "3546382872",
      url: `${ORIGIN}/s-anzeige/wg-zimmer-oberschleissheim-3-zimmer-ab-01-11-ab-605-warm/3546382872-199-5517`,
      title: "WG-Zimmer Oberschleißheim – 3 Zimmer ab 01.11. – ab 605 € warm",
      listingType: "wg_room",
      kindLabel: "WG / auf Zeit, 3 Zi., 55 m² flat",
      place: "85764 Oberschleißheim",
      street: null,
      lat: null,
      lng: null,
      priceListed: 605,
      sizeSqm: null, // 55 m² with 3 rooms in "Auf Zeit & WG" is the flat, not the room
      availableFrom: null,
      availableTo: null,
      swap: false,
    });
  });

  it("reads the current price, not the struck-through one, and drops placeholder prices", () => {
    const byId = Object.fromEntries(page.listings.map((l) => [l.externalId, l]));
    expect(byId["3536207850"]).toMatchObject({ priceListed: 470, sizeSqm: 9, place: "80933 Feldmoching" });
    expect(byId["3545322242"]).toMatchObject({ priceListed: null, sizeSqm: 40 }); // "29 €" for a short stay
    expect(byId["3546651796"].sizeSqm).toBe(1);
  });

  it("flags swaps by their title", () => {
    expect(page.listings.filter((l) => l.swap).map((l) => l.externalId)).toEqual(["3335842751"]);
  });

  it("finds further pages of the same search only", () => {
    expect([...page.pageUrls]).toEqual([
      [1, `${ORIGIN}/s-auf-zeit-wg/garching-b-muenchen/preis::650/seite:2/c199l6303r15`],
      [2, `${ORIGIN}/s-auf-zeit-wg/garching-b-muenchen/preis::650/seite:3/c199l6303r15`],
      [3, `${ORIGIN}/s-auf-zeit-wg/garching-b-muenchen/preis::650/seite:4/c199l6303r15`],
    ]);
  });

  it("recognises an explicit zero-result page, even with ads from other places below it", () => {
    const empty = parseSearchPage(emptyPage, PAGE_URL, WG);
    expect(empty.listings).toEqual([]);
    expect(empty.zeroResults).toBe(true);
  });

  it("parses nothing when the card markup changes, and says so", () => {
    const changed = parseSearchPage(searchPage.replaceAll("<article ", "<div "), PAGE_URL, WG);
    expect(changed.listings).toEqual([]);
    expect(changed.zeroResults).toBe(false);
    expect(changed.emptyHint).toBe("0 cards in the result list");
    expect(parseSearchPage("<html></html>", PAGE_URL, WG).emptyHint).toBe("no result list");
  });
});

describe("parseDetail", () => {
  it("reads rent, position, availability and size from a flat's attribute list", () => {
    expect(parseDetail(detailFlat, detailUrl("3536207850", 203))).toEqual({
      warm: 620, cold: 470, position: { lat: 48.217851359304106, lng: 11.562323670381877 },
      availableFrom: "2026-11-01", sizeSqm: 9, swap: false,
    });
  });

  it("treats the price as cold rent only where the category says so", () => {
    expect(parseDetail(detailSwap, detailUrl("3335842751", 203))).toMatchObject({ warm: null, cold: 515, sizeSqm: 33 });
    // Auf Zeit & WG: the price basis varies, and "29 €" is no monthly rent anyway.
    expect(parseDetail(detailShort, detailUrl("3545322242", 199))).toEqual({
      warm: null, cold: null, position: { lat: 48.31133139621653, lng: 11.663525303845162 },
      availableFrom: "2026-11-01", sizeSqm: 40, swap: false,
    });
  });

  it("does not take a shared flat's area for the room's in Auf Zeit & WG", () => {
    const page = detailShort
      .replace(/Zimmer<span([^>]*)>\s*1</, "Zimmer<span$1>3<")
      .replace(/(Wohnfläche<span[^>]*>\s*)40 m²/, (_, label) => `${label}60 m²`);
    expect(parseDetail(page, detailUrl("3545322242", 199)).sizeSqm).toBeNull(); // 60 m², 3 rooms
    expect(parseDetail(page, detailUrl("3545322242", 203)).sizeSqm).toBe(60); // a flat's area is its size
    expect(parseDetail(detailShort, detailUrl("3545322242", 199)).sizeSqm).toBe(40); // one room: its own
  });

  it("derives warm rent from extras and reads an explicit swap attribute", () => {
    const page = detailFlat
      .replace(/Warmmiete<span([^>]*)>\s*620 €/, "Heizkosten<span$1>40 €")
      .replace("Kein Tausch", "Tausch");
    expect(parseDetail(page, detailUrl("3536207850", 203))).toMatchObject({ warm: 660, cold: 470, swap: true });
  });

  it("refuses a page that is not a listing", () => {
    expect(() => parseDetail("<html>Startseite</html>", detailUrl("1", 203))).toThrow(/not a listing page/);
  });

  it("reports a deleted ad that redirects away as gone", async () => {
    const redirected = html("<html></html>");
    Object.defineProperties(redirected, { redirected: { value: true }, url: { value: `${ORIGIN}/s-wohnung-mieten/c203` } });
    await expect(kleinanzeigen.parseDetail(redirected, detailUrl("1", 203))).rejects.toBeInstanceOf(ListingGone);
  });

  it("parses month-year and exact availability dates", () => {
    expect(parseAvailableFrom("März 2027")).toBe("2027-03-01");
    expect(parseAvailableFrom("01.12.2026")).toBe("2026-12-01");
    expect(parseAvailableFrom("sofort")).toBeNull();
  });
});

describe("search URLs", () => {
  it("covers the derived search area from the site's own centre", () => {
    const c = settings.criteria;
    const r = searchRadiusKm(c);
    const centre = { lat: 48.2488, lng: 11.6511 };
    const bikeKm = (c.bikeSpeedKmh * c.maxBikeMinutes) / 60;
    const stopKm = (c.bikeSpeedKmh * c.maxBikeToStopMinutes) / 60;
    for (const a of c.anchors) expect(haversineKm(centre.lat, centre.lng, a.lat, a.lng) + bikeKm).toBeLessThanOrEqual(r);
    for (const s of c.transitStops) expect(haversineKm(centre.lat, centre.lng, s.lat, s.lng) + stopKm).toBeLessThanOrEqual(r);
    expect(r).toBe(17);
  });

  it("builds one stream per category with the rent cap and radius", () => {
    expect(kleinanzeigen.streams(settings.criteria)).toEqual([
      { stream: "kleinanzeigen:wohnung", url: `${ORIGIN}/s-wohnung-mieten/garching-b-muenchen/preis::650/c203l6303r17` },
      { stream: "kleinanzeigen:wg", url: `${ORIGIN}/s-auf-zeit-wg/garching-b-muenchen/preis::650/c199l6303r17` },
      { stream: "kleinanzeigen:haus", url: `${ORIGIN}/s-haus-mieten/garching-b-muenchen/preis::650/c205l6303r17` },
    ]);
    expect(buildSearchUrl(settings.criteria, WG)).toBe(`${ORIGIN}/s-auf-zeit-wg/garching-b-muenchen/preis::650/c199l6303r17`);
  });
});

describe("the Source wrapper", () => {
  it("parses a response exactly as the page text", async () => {
    expect(await kleinanzeigen.parseSearchPage(html(searchPage), PAGE_URL)).toEqual(parseSearchPage(searchPage, PAGE_URL, WG));
    expect((await kleinanzeigen.parseSearchPage(html(emptyPage), PAGE_URL)).zeroResults).toBe(true);
    for (const [page, url] of [[detailFlat, detailUrl("3536207850", 203)], [detailShort, detailUrl("3545322242", 199)]]) {
      expect(await kleinanzeigen.parseDetail(html(page), url)).toEqual(parseDetail(page, url));
    }
  });
});

describe("mentionsSwap", () => {
  it("catches swap wording but not its negation", () => {
    for (const t of ["Wohnungsswap - 1 Zimmer", "TAUSCHWOHNUNG Schöne 1-Zimmer", "Wohnungstausch Laim", "Tausche 2 gegen 3 Zimmer"]) {
      expect(mentionsSwap(t)).toBe(true);
    }
    for (const t of ["WG-Zimmer, kein Tausch", "Austauschstudentin sucht", "Zimmer ab sofort", null]) {
      expect(mentionsSwap(t)).toBe(false);
    }
  });
});
