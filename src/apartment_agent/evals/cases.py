"""Golden set for fit-score evals.

A small, hand-labelled set of listings with the fit-score band a sane model should land in. Bands
are deliberately wide — they catch gross misranking (a great match scored 10, a poor one scored 95)
and regressions when swapping free models, not fine-grained calibration.
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from apartment_agent.models import Listing, ListingType


class EvalCase(BaseModel):
    name: str
    listing: Listing
    lo: int           # inclusive expected fit-score lower bound
    hi: int           # inclusive expected fit-score upper bound


def _l(ext_id: str, **kw) -> Listing:
    base = dict(
        source="wg_gesucht", external_id=ext_id, url=f"https://www.wg-gesucht.de/{ext_id}",
        listing_type=ListingType.WG_ROOM, city="München",
    )
    base.update(kw)
    return Listing(**base)


GOLDEN: list[EvalCase] = [
    EvalCase(
        name="ideal-central-cheap",
        listing=_l("g1", title="Helles Zimmer in Schwabing", price_warm=520.0, size_sqm=22.0,
                   district="Schwabing", available_from=date(2026, 10, 1)),
        lo=70, hi=100,
    ),
    EvalCase(
        name="good-commutable-suburb",
        listing=_l("g2", title="WG-Zimmer in Garching nahe U-Bahn", price_warm=600.0, size_sqm=18.0,
                   district="Garching", available_from=date(2026, 9, 25)),
        lo=55, hi=95,
    ),
    EvalCase(
        name="borderline-pricey-but-big",
        listing=_l("g3", title="Große Wohnung", price_warm=695.0, size_sqm=40.0,
                   listing_type=ListingType.APARTMENT, district="Sendling",
                   available_from=date(2026, 11, 1)),
        lo=35, hi=85,
    ),
    EvalCase(
        name="poor-tiny-and-at-cap",
        listing=_l("g4", title="Kleines Zimmer", price_warm=700.0, size_sqm=12.0,
                   district="Haar", available_from=date(2026, 12, 1)),
        lo=0, hi=55,
    ),
]
