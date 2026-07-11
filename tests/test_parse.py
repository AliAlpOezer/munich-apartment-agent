"""Tests for the WG-Gesucht parser (against a synthetic fixture) and its helpers."""

from __future__ import annotations

import pathlib
from datetime import date

from apartment_agent.models import ListingType
from apartment_agent.sources.wg_gesucht import (
    WgGesuchtAdapter,
    _parse_dates,
    _split_detail,
    _to_float,
    parse_detail_costs,
)

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "wg_sample.html"


# --- helpers ---
def test_to_float_german_formats():
    assert _to_float("650 €") == 650.0
    assert _to_float("1.200 €") == 1200.0
    assert _to_float("30,5 m²") == 30.5
    assert _to_float("ab sofort") is None
    assert _to_float(None) is None


def test_parse_dates():
    assert _parse_dates("01.11.2026") == (date(2026, 11, 1), None)
    assert _parse_dates("15.09.2026 - 31.12.2026") == (date(2026, 9, 15), date(2026, 12, 31))
    assert _parse_dates("ab sofort") == (None, None)
    assert _parse_dates("") == (None, None)


def test_split_detail():
    assert _split_detail("2er WG | München Schwabing | Amalienstraße") == (
        "München", "Schwabing", "Amalienstraße",
    )


# --- full parse ---
def test_parse_sample():
    listings = WgGesuchtAdapter().parse(FIXTURE.read_text(encoding="utf-8"))
    by_id = {x.external_id: x for x in listings}

    # the non-numeric "sponsored" card is skipped
    assert set(by_id) == {"1000001", "1000002", "1000003"}

    a = by_id["1000001"]
    assert a.listing_type is ListingType.WG_ROOM
    # the list card's single figure is kept as the ambiguous-basis `price_listed`,
    # not assumed to be Warmmiete (fetch_costs resolves warm/cold from the detail page)
    assert a.price_listed == 650.0 and a.price_warm is None and a.size_sqm == 18.0
    assert a.city == "München" and a.district == "Schwabing"
    assert a.address == "Amalienstraße"
    assert a.available_from == date(2026, 11, 1) and a.available_to is None
    assert a.url == "https://www.wg-gesucht.de/wg-zimmer-in-Muenchen-Schwabing.1000001.html"
    assert a.title == "Helles Zimmer in Schwabing"

    b = by_id["1000002"]
    assert b.listing_type is ListingType.APARTMENT
    assert b.price_listed == 700.0 and b.size_sqm == 30.5
    assert b.available_from == date(2026, 9, 15) and b.available_to == date(2026, 12, 31)

    c = by_id["1000003"]
    assert c.listing_type is ListingType.WG_ROOM
    assert c.price_listed == 1200.0 and c.size_sqm == 25.0
    assert c.available_from is None and c.available_to is None


# --- detail-page cost parsing ---
def test_parse_detail_costs_explicit_warm():
    html = """
    <table>
      <tr><td>Kaltmiete:</td><td>450 €</td></tr>
      <tr><td>Nebenkosten:</td><td>120 €</td></tr>
      <tr><td>GESAMTMIETE:</td><td>600 €</td></tr>
      <tr><td>Kaution:</td><td>900 €</td></tr>
    </table>
    """
    warm, cold = parse_detail_costs(html)
    assert warm == 600.0 and cold == 450.0  # explicit Gesamtmiete wins; Kaution ignored


def test_parse_detail_costs_derives_warm_from_extras():
    # no explicit Warmmiete -> warm = Kaltmiete + Nebenkosten + Heizkosten
    html = """
    <div class="row"><div>Miete</div><div>500 €</div></div>
    <div class="row"><div>Nebenkosten</div><div>80 €</div></div>
    <div class="row"><div>Heizkosten</div><div>40 €</div></div>
    """
    warm, cold = parse_detail_costs(html)
    assert cold == 500.0 and warm == 620.0


def test_parse_detail_costs_no_rows():
    assert parse_detail_costs("<html><body>no costs here</body></html>") == (None, None)


def test_parse_detail_costs_wg_gesucht_panels():
    """Real WG-Gesucht layout: value read from its own span, not the concatenated row blob.

    Regression guard for the bug where every price came out garbage (e.g. warm=6, cold=17.9)
    because the whole-row text scan grabbed the first number it found (a floor/size), and where
    Kaution and non-cost rows (frei ab / address) leaked into the price.
    """
    html = """
    <div class="section_footer_dark"><div class="row"><div class="col-xs-12">
      <div class="col-xs-6 text-center">
        <span class="key_fact_detail">Zimmergröße</span><b class="key_fact_value">12m²</b>
      </div>
      <div class="col-xs-6 text-center">
        <span class="key_fact_detail">Gesamtmiete</span><b class="key_fact_value">595€</b>
      </div>
    </div></div></div>
    <div class="panel section_panel"><div class="row"><div class="col-xs-12">
      <div class="row">
        <div class="col-xs-6"><span class="section_panel_detail">Miete:</span></div>
        <div class="col-xs-6"><span class="section_panel_value">450€</span></div>
      </div>
      <div class="row">
        <div class="col-xs-6"><span class="section_panel_detail">Nebenkosten:</span></div>
        <div class="col-xs-6"><span class="section_panel_value">145€</span></div>
      </div>
      <div class="row">
        <div class="col-xs-6"><span class="section_panel_detail">Kaution:</span></div>
        <div class="col-xs-6"><span class="section_panel_value">1000€</span></div>
      </div>
      <div class="row">
        <div class="col-xs-6"><span class="section_panel_detail">frei ab:</span></div>
        <div class="col-xs-6"><span class="section_panel_value">01.10.2026</span></div>
      </div>
    </div></div></div>
    """
    warm, cold = parse_detail_costs(html)
    assert warm == 595.0 and cold == 450.0  # Gesamtmiete wins; Kaution + frei-ab date ignored


def test_build_search_urls():
    from apartment_agent.models import FilterConfig

    urls = WgGesuchtAdapter().build_search_urls(FilterConfig())  # default: 657 cap, no radius
    assert len(urls) == 1
    u = urls[0]
    assert "0+1+2+3" in u                                   # all four categories
    assert "city_id=90" in u
    assert "rMax=657" in u and "rent_range=0%2C657" in u
    assert "min_rent=0" in u and "max_rent=657" in u and "rMin=0" in u
    assert "sort_column=3" in u                             # newest first
    assert "dFr=" in u                                      # available-from date filter present
    assert "radDis" not in u                                # no centre configured -> city-wide


def test_build_search_urls_with_radius():
    from apartment_agent.models import FilterConfig

    cfg = FilterConfig(
        search_center_label="Alte Heide, München, Deutschland, 80805",
        search_center_lat=48.1783353, search_center_lng=11.5978799, search_radius_m=5000,
    )
    assert cfg.has_radius
    u = WgGesuchtAdapter().build_search_urls(cfg)[0]
    assert "radDis=5000" in u
    assert "radLat=48.1783353" in u and "radLng=11.5978799" in u
    assert "radAdd=Alte+Heide" in u                          # label is URL-encoded (spaces -> +)
