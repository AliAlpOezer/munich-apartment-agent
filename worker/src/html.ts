// HTMLRewriter hands over raw source text: entities are not decoded and text arrives in chunks.

const NAMED: Record<string, string> = {
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
  apos: "'",
  nbsp: " ",
  euro: "€",
  sup2: "²",
  middot: "·",
  auml: "ä",
  ouml: "ö",
  uuml: "ü",
  Auml: "Ä",
  Ouml: "Ö",
  Uuml: "Ü",
  szlig: "ß",
};

export function decodeEntities(s: string): string {
  return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z0-9]+);/gi, (whole, ref: string) => {
    if (ref[0] === "#") {
      const code = ref[1] === "x" || ref[1] === "X" ? parseInt(ref.slice(2), 16) : parseInt(ref.slice(1), 10);
      return Number.isFinite(code) ? String.fromCodePoint(code) : whole;
    }
    return NAMED[ref] ?? whole;
  });
}

/** Decode entities and collapse all whitespace (including nbsp) to single spaces. */
export function cleanText(s: string): string {
  return decodeEntities(s).replace(/[\s ]+/g, " ").trim();
}

/** German-formatted number: "1.250" -> 1250, "21,5" -> 21.5, "n.a." -> null. */
export function parseGermanNumber(text: string | null | undefined): number | null {
  if (!text) return null;
  const m = /\d[\d.]*(?:,\d+)?/.exec(text);
  if (!m) return null;
  const n = Number(m[0].replace(/\./g, "").replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

/** All "dd.mm.yyyy" dates in `text`, as ISO "yyyy-mm-dd". */
export function parseGermanDates(text: string): string[] {
  return [...text.matchAll(/(\d{2})\.(\d{2})\.(\d{4})/g)].map(([, d, m, y]) => `${y}-${m}-${d}`);
}

/** Run an HTMLRewriter over a string to completion. */
export async function rewrite(html: string, rewriter: HTMLRewriter): Promise<void> {
  await rewriter.transform(new Response(html)).arrayBuffer();
}
