"""Unit tests for the hard filter — the core correctness piece, runs with no creds."""

from __future__ import annotations

from datetime import date

import pytest

from apartment_agent.models import FilterConfig, Listing, ListingType
from apartment_agent.nodes.filter import filter_listings, passes_filter


def make_listing(**overrides) -> Listing:
    """A baseline listing that passes the default filter; override fields per test."""
    base = dict(
        source="wg_gesucht",
        external_id="1",
        url="https://www.wg-gesucht.de/1",
        title="Nice room",
        price_warm=650.0,
        size_sqm=15.0,
        listing_type=ListingType.WG_ROOM,
        district="Schwabing, München",
        available_from=date(2026, 10, 1),
    )
    base.update(overrides)
    return Listing(**base)


@pytest.fixture
def cfg() -> FilterConfig:
    return FilterConfig()  # defaults: 700€ warm, 12m², move-in 2025-10-01


def test_baseline_passes(cfg):
    ok, reasons = passes_filter(make_listing(), cfg)
    assert ok, reasons


# --- Rent ---
def test_warm_rent_at_cap_passes(cfg):
    assert passes_filter(make_listing(price_warm=700.0), cfg)[0]


def test_warm_rent_over_cap_fails(cfg):
    ok, reasons = passes_filter(make_listing(price_warm=700.01), cfg)
    assert not ok and any("rent" in r for r in reasons)


def test_falls_back_to_cold_rent_when_warm_unknown(cfg):
    # warm unknown, cold within cap -> passes (permissive lower bound)
    assert passes_filter(make_listing(price_warm=None, price_cold=690.0), cfg)[0]
    # warm unknown, cold over cap -> fails
    assert not passes_filter(make_listing(price_warm=None, price_cold=900.0), cfg)[0]


def test_both_rents_unknown_kept(cfg):
    # missing rent is treated as a parse miss, not a rejection
    assert passes_filter(make_listing(price_warm=None, price_cold=None), cfg)[0]


# --- Size ---
def test_size_at_min_passes(cfg):
    assert passes_filter(make_listing(size_sqm=12.0), cfg)[0]


def test_size_below_min_fails(cfg):
    ok, reasons = passes_filter(make_listing(size_sqm=11.9), cfg)
    assert not ok and any("size" in r for r in reasons)


def test_unknown_size_kept(cfg):
    assert passes_filter(make_listing(size_sqm=None), cfg)[0]


# --- Availability (window around the 2026-10-01 move-in) ---
def test_available_on_move_in_passes(cfg):
    assert passes_filter(make_listing(available_from=date(2026, 10, 1)), cfg)[0]


def test_available_within_before_grace_passes(cfg):
    # default 14-day grace before move-in
    assert passes_filter(make_listing(available_from=date(2026, 9, 20)), cfg)[0]


def test_available_too_early_fails(cfg):
    ok, reasons = passes_filter(make_listing(available_from=date(2026, 6, 1)), cfg)
    assert not ok and any("available_from" in r for r in reasons)


def test_available_within_after_window_passes(cfg):
    assert passes_filter(make_listing(available_from=date(2026, 12, 1)), cfg)[0]


def test_available_too_far_future_fails(cfg):
    ok, reasons = passes_filter(make_listing(available_from=date(2027, 5, 1)), cfg)
    assert not ok and any("available_from" in r for r in reasons)


def test_undated_rejected(cfg):
    ok, reasons = passes_filter(make_listing(available_from=None), cfg)
    assert not ok and any("available-from" in r for r in reasons)


# --- Location ---
def test_commutable_suburb_passes(cfg):
    assert passes_filter(make_listing(district="Garching bei München"), cfg)[0]


def test_far_city_fails(cfg):
    ok, reasons = passes_filter(
        make_listing(district="Berlin Mitte", address="Berlin", city="Berlin"), cfg
    )
    assert not ok and any("location" in r for r in reasons)


def test_no_location_text_kept(cfg):
    assert passes_filter(make_listing(district=None, address=None, city=None), cfg)[0]


# --- Aggregate ---
def test_filter_listings_splits(cfg):
    good = make_listing(external_id="g")
    bad = make_listing(external_id="b", price_warm=1500.0)
    matched, rejected = filter_listings([good, bad], cfg)
    assert [m.external_id for m in matched] == ["g"]
    assert [r[0].external_id for r in rejected] == ["b"]
    assert rejected[0][1]  # has reasons
