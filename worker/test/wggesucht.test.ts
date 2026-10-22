import { describe, expect, it } from "vitest";
import { haversineKm } from "../src/bike";
import {
  buildSearchUrl, classifyCostLabel, extractJsonArray, parseDetailCosts, parseSearchPage, searchArea,
} from "../src/wggesucht";
import detailPage from "./fixtures/detail.html?raw";
import emptyPage from "./fixtures/search-empty.html?raw";
import { searchPage, settings } from "./helpers";

describe("parseSearchPage (live layout, 2026-10-22)", () => {
  it("parses every organic card and skips sponsored placements", async () => {
    const page = await parseSearchPage(searchPage);
    expect(page.listings.map((l) => l.externalId)).toEqual([
      "7335451", "4061496", "3770524", "14265492", "14269724", "13293325",
    ]);
    expect(page.markerCount).toBe(6);
    expect(page.zeroResults).toBe(false);
  });

  it("extracts card facts and joins coordinates from the map markers", async () => {
    const { listings } = await parseSearchPage(searchPage);
    expect(listings.find((l) => l.externalId === "14265492")).toEqual({
      externalId: "14265492",
      url: "https://www.wg-gesucht.de/wg-zimmer-in-Muenchen-Dietersheim.14265492.html",
      title: "2 freie WG Zimmer direkt an der TUM Garching",
      listingType: "wg_room",
      kindLabel: "3er WG",
      place: "Dietersheim Dietersheim",
      street: "Amselweg",
      lat: 48.282421,
      lng: 11.672301,
      priceListed: 600,
      sizeSqm: 13,
      availableFrom: "2026-10-23",
      availableTo: null,
    });
    const freimann = listings.find((l) => l.externalId === "7335451")!;
    expect(freimann.title).toBe("Möbliertes WG - Zimmer in Einfamilienhaus für Studenten und Praktikanten");
    expect(freimann.place).toBe("München Schwabing-Freimann");
    expect(freimann.street).toBe("Wallnerstr.");
  });

  it("finds the next result page with entities decoded", async () => {
    const { pageUrls } = await parseSearchPage(searchPage);
    expect([...pageUrls.keys()]).toEqual([1]);
    const url = pageUrls.get(1)!;
    expect(url).toContain(".0+1+2+3.1.1.html?");
    expect(url).toContain("&radDis=11000");
    expect(url).not.toContain("&amp;");
  });

  it("recognises an explicit zero-result page", async () => {
    const page = await parseSearchPage(emptyPage);
    expect(page.listings).toEqual([]);
    expect(page.zeroResults).toBe(true);
  });

  it("parses nothing when the card markup changes, while markers remain", async () => {
    const page = await parseSearchPage(searchPage.replaceAll("wgg-list-card", "wgg-tile"));
    expect(page.listings).toEqual([]);
    expect(page.markerCount).toBe(6);
    expect(page.zeroResults).toBe(false);
  });
});

describe("extractJsonArray", () => {
  it("matches brackets through nested arrays and strings", () => {
    const src = 'var x = { markers: [{"a":[1,2],"s":"]\\"["},{"b":3}], other: [9] };';
    expect(extractJsonArray(src, "markers:")).toEqual([{ a: [1, 2], s: ']"[' }, { b: 3 }]);
    expect(extractJsonArray(src, "missing:")).toBeNull();
    expect(extractJsonArray("markers: [ {broken ]", "markers:")).toBeNull();
  });
});

describe("parseDetailCosts", () => {
  it("reads Gesamtmiete and Miete from the live detail layout, ignoring Kaution", async () => {
    expect(await parseDetailCosts(detailPage)).toEqual({ warm: 650, cold: 600 });
  });

  it("derives warm rent from Kaltmiete plus extras when no total is given", async () => {
    const html = `
      <div class="row"><div><span class="section_panel_detail">Kaltmiete:</span></div>
        <div><span class="section_panel_value">540&euro;</span></div></div>
      <div class="row"><div><span class="section_panel_detail">Nebenkosten:</span></div>
        <div><span class="section_panel_value">80&euro;</span></div></div>
      <div class="row"><div><span class="section_panel_detail">Heizkosten:</span></div>
        <div><span class="section_panel_value">30&euro;</span></div></div>
      <div class="row"><div><span class="section_panel_detail">Kaution:</span></div>
        <div><span class="section_panel_value">1.620&euro;</span></div></div>`;
    expect(await parseDetailCosts(html)).toEqual({ warm: 650, cold: 540 });
  });

  it("treats placeholder rents as unknown and returns nulls without cost rows", async () => {
    const placeholder = `<span class="key_fact_detail">Gesamtmiete</span><b class="key_fact_value">2&euro;</b>`;
    expect(await parseDetailCosts(placeholder)).toEqual({ warm: null, cold: null });
    expect(await parseDetailCosts("<html><body>Anzeige nicht gefunden</body></html>")).toEqual({ warm: null, cold: null });
  });

  it("does not let a label without a value shift the pairing", async () => {
    const html = `
      <span class="section_panel_detail">SCHUFA-Auskunft:</span>
      <span class="section_panel_detail">Miete:</span><span class="section_panel_value">500&euro;</span>`;
    expect(await parseDetailCosts(html)).toEqual({ warm: null, cold: 500 });
  });

  it("classifies labels, most specific first", () => {
    expect(classifyCostLabel("Gesamtmiete")).toBe("warm");
    expect(classifyCostLabel("Kaltmiete:")).toBe("cold");
    expect(classifyCostLabel("Miete:")).toBe("cold");
    expect(classifyCostLabel("Sonstige Kosten:")).toBe("extra");
    expect(classifyCostLabel("Kaution:")).toBeNull();
    expect(classifyCostLabel("Ablösevereinbarung:")).toBeNull();
    expect(classifyCostLabel("frei ab:")).toBeNull();
  });
});

describe("search area", () => {
  it("is a guaranteed superset of the reachable area around every anchor", () => {
    const c = settings.criteria;
    const area = searchArea(c);
    const reachKm = (c.bikeSpeedKmh * c.maxBikeMinutes) / 60;
    for (const a of c.anchors) {
      expect(haversineKm(area.lat, area.lng, a.lat, a.lng) + reachKm).toBeLessThanOrEqual(area.radiusM / 1000);
    }
    expect(area.radiusM).toBe(11300); // 22 km/h x 30 min + 0.28 km anchor spread, rounded up
  });

  it("builds the page-0 URL with the rent cap and radius", () => {
    const url = new URL(buildSearchUrl(settings.criteria));
    expect(url.hostname).toBe("www.wg-gesucht.de");
    expect(url.pathname).toContain("-in-Muenchen.90.0+1+2+3.1.0.html");
    expect(url.searchParams.get("rMax")).toBe("650");
    expect(url.searchParams.get("radDis")).toBe("11300");
    expect(url.searchParams.getAll("categories[3]")).toEqual(["3"]);
  });
});
