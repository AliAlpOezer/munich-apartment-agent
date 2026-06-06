"""Human-in-the-loop feedback.

Telegram message reactions (👍 / 👎) on the listing notifications are the cheapest signal the user
can give. They are parsed from the Bot API `getUpdates` payload, mapped back to the listing that was
reacted to, and folded into the wiki `preferences` page so the search intent learns over time.

The parsing and aggregation here are pure (no I/O) so they are fully unit-tested; the live polling
and persistence live in `notify/telegram.py` and `db/supabase_client.py`.
"""

from __future__ import annotations

from pydantic import BaseModel

_POSITIVE = {"👍", "❤", "❤️", "🔥", "👌", "🥰"}
_NEGATIVE = {"👎", "💩", "🤮"}


class Reaction(BaseModel):
    update_id: int
    message_id: int
    emoji: str
    sentiment: int   # +1 like, -1 dislike


def parse_reactions(updates: list[dict]) -> list[Reaction]:
    """Extract like/dislike reactions from Telegram getUpdates results.

    Looks at `message_reaction` updates and their newest reaction emoji; unknown emojis are skipped.
    """
    out: list[Reaction] = []
    for u in updates:
        mr = u.get("message_reaction")
        if not mr:
            continue
        emojis = [r.get("emoji") for r in mr.get("new_reaction", []) if r.get("type") == "emoji"]
        for emoji in emojis:
            if emoji in _POSITIVE:
                sentiment = 1
            elif emoji in _NEGATIVE:
                sentiment = -1
            else:
                continue
            out.append(Reaction(
                update_id=u["update_id"], message_id=mr["message_id"],
                emoji=emoji, sentiment=sentiment,
            ))
    return out


class PreferenceSignal(BaseModel):
    """Aggregated reactions, by district — the learned slice of the search intent."""

    liked: dict[str, int] = {}      # district -> net positive score (>0)
    disliked: dict[str, int] = {}   # district -> net score (<0)
    total_reactions: int = 0

    @property
    def is_empty(self) -> bool:
        return self.total_reactions == 0


def summarize_by_district(pairs: list[tuple[str, int]]) -> PreferenceSignal:
    """Aggregate (district, sentiment) pairs into net per-district like/dislike scores."""
    net: dict[str, int] = {}
    for district, sentiment in pairs:
        key = district or "Unknown"
        net[key] = net.get(key, 0) + sentiment
    liked = {d: n for d, n in net.items() if n > 0}
    disliked = {d: n for d, n in net.items() if n < 0}
    return PreferenceSignal(liked=liked, disliked=disliked, total_reactions=len(pairs))


def sync_feedback(
    *,
    fetch_updates,    # (offset:int) -> list[dict]  Telegram getUpdates results
    resolve_listing,  # (message_id:int) -> (source, external_id) | None
    save_feedback,    # (source, external_id, Reaction) -> None
    offset_get,       # () -> int
    offset_set,       # (int) -> None
) -> int:
    """Pull new Telegram updates, persist reactions mapped to their listing, advance the offset.

    All I/O is injected so the control flow (offset handling, mapping, idempotency) is unit-tested
    without Telegram or a database. Returns the number of feedback rows saved.
    """
    offset = offset_get()
    updates = fetch_updates(offset)
    if not updates:
        return 0
    saved = 0
    for reaction in parse_reactions(updates):
        listing = resolve_listing(reaction.message_id)
        if listing is not None:
            save_feedback(listing[0], listing[1], reaction)
            saved += 1
    # advance past every update seen (incl. non-reactions) so getUpdates won't re-deliver them
    offset_set(max(u["update_id"] for u in updates) + 1)
    return saved
