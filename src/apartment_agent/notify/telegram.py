"""Telegram Bot API notifier (no SDK — a couple of plain HTTPS calls)."""

from __future__ import annotations

import html
import logging

from apartment_agent.models import Listing

log = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/sendMessage"
_TG_LIMIT = 4096


def _fmt_price(listing: Listing) -> str:
    warm = f"{listing.price_warm:.0f}€ warm" if listing.price_warm is not None else None
    cold = f"{listing.price_cold:.0f}€ kalt" if listing.price_cold is not None else None
    return " / ".join(p for p in (warm, cold) if p) or "?€"


def format_listing(listing: Listing) -> str:
    """One listing as a Telegram-HTML block."""
    title = html.escape(listing.title or "(no title)")
    bits: list[str] = [_fmt_price(listing)]
    if listing.size_sqm is not None:
        bits.append(f"{listing.size_sqm:.0f} m²")
    if listing.listing_type:
        bits.append(listing.listing_type.value)
    where = " · ".join(x for x in (listing.district, listing.city) if x)
    avail = f"ab {listing.available_from.isoformat()}" if listing.available_from else "ab sofort"
    fit = f" · fit {listing.fit_score}/100" if listing.fit_score is not None else ""

    lines = [f'🏠 <a href="{html.escape(listing.url)}">{title}</a>',
             f"   {' · '.join(bits)}{fit}"]
    if where:
        lines.append(f"   📍 {html.escape(where)} · {avail}")
    if listing.summary:
        lines.append(f"   💬 {html.escape(listing.summary)}")
    return "\n".join(lines)


def format_digest(listings: list[Listing]) -> list[str]:
    """Render listings into one or more messages, each within Telegram's size limit."""
    header = f"🔔 {len(listings)} new Munich listing(s)\n\n"
    blocks = [format_listing(x) for x in listings]
    messages, current = [], header
    for block in blocks:
        if len(current) + len(block) + 2 > _TG_LIMIT:
            messages.append(current.rstrip())
            current = ""
        current += block + "\n\n"
    if current.strip():
        messages.append(current.rstrip())
    return messages


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, text: str) -> None:
        import httpx  # lazy

        resp = httpx.post(
            _API.format(token=self.bot_token),
            json={
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        resp.raise_for_status()

    def send_digest(self, listings: list[Listing]) -> int:
        sent = 0
        for message in format_digest(listings):
            self.send(message)
            sent += 1
        return sent
