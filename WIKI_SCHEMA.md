# Wiki Schema

This document governs the agent's **knowledge wiki** — the synthesized, interlinked layer it
maintains on top of the raw listing data. It is the contract between the deterministic code and the
LLM, modelled on Karpathy's *LLM Wiki* pattern (raw sources → wiki → schema; Ingest / Query / Lint).

The wiki is **not** the database. The `listings` table is the immutable raw source of truth; the wiki
is a smaller, human-readable, evolving *understanding* of the Munich rental search, suitable for a
person to browse and for a frontend to render.

## Three layers

1. **Raw sources** — the scraped listings (`listings` table + each row's `raw` jsonb). Read, never
   edited by the wiki.
2. **The wiki** — markdown pages under `WIKI_DIR` (default `./wiki`), interlinked with `[[slug]]`
   wiki-links. Runtime output: **gitignored** so it persists across `git reset --hard` redeploys and
   never leaks tracked into the repo.
3. **The schema** — this file. It defines the page taxonomy, section contract, and linking rules.

## Page taxonomy

| Slug pattern        | Page                | Built by        | Holds                                                            |
|---------------------|---------------------|-----------------|-----------------------------------------------------------------|
| `market-overview`   | Market overview     | ingest          | City-wide synthesis: counts, rent ranges, where the budget fits |
| `district-<slug>`   | One district        | ingest          | Per-district stats, recent matches, a "market read" synthesis   |
| `preferences`       | Search preferences  | ingest (config) | The current search intent, rendered from `FilterConfig`         |
| `lint-report`       | Health report       | lint            | Contradictions, stale/orphan pages, gaps, broken links          |

## Section contract

Every generated page is a mix of **deterministic** sections (rebuilt from data each run — the LLM must
never author numbers) and at most one **LLM** section (prose synthesis). Sections are delimited by
HTML-comment markers so they can be regenerated in place without disturbing the rest:

```
<!-- BEGIN auto:stats -->   …deterministic, code-owned…   <!-- END auto:stats -->
<!-- BEGIN llm:synthesis --> …prose, LLM-owned…           <!-- END llm:synthesis -->
```

- `auto:*` sections are **regenerated wholesale** every ingest from the current data. Never hand-edit.
- `llm:synthesis` is the only model-authored region. On ingest the prior synthesis is read back in as
  context, so the model *revises* rather than starts over. If no LLM is configured the prior text is
  preserved untouched.

## Linking rules

- Link with `[[slug]]` (e.g. `[[district-schwabing]]`, `[[market-overview]]`). A link to a
  non-existent slug is a **gap** for the linter to flag, not an error.
- `auto:links` on each page is regenerated from real neighbours, so cross-references stay valid.

## Operations

- **Ingest** — after each scheduled run, fold the run's new listings into the affected district pages
  and the market overview. Cheap-tier LLM writes only the synthesis prose; stats are computed in code.
- **Query** — the frontend (and you) read the wiki, not the raw rows. Synthesized once, read many.
- **Lint** — a periodic health check: stale pages, orphans, gaps, broken links, and (optionally, on
  the hard tier) prose/data contradictions. What lint finds becomes the next ingest's work.

## Division of labour

The human curates intent (filters, reactions) and decides what it all means. The code owns the
deterministic truth (stats, listing lists, links). The LLM owns synthesis and contradiction-spotting —
the maintenance no human keeps up with by hand.
