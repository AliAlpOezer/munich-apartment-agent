import { kleinanzeigen } from "./kleinanzeigen";
import type { Source } from "./sources";
import { wgGesucht } from "./wggesucht";

export const SOURCES: Readonly<Record<string, Source>> = {
  [wgGesucht.id]: wgGesucht,
  [kleinanzeigen.id]: kleinanzeigen,
};

export function sourceById(id: string): Source | null {
  return Object.hasOwn(SOURCES, id) ? SOURCES[id] : null;
}

/** Search messages enqueued before streams existed carry no stream: they were WG-Gesucht's. */
export const LEGACY_STREAM = wgGesucht.id;

/** A stream is "<source id>" or "<source id>:<category>". */
export function sourceOfStream(stream: string): Source | null {
  return sourceById(stream.split(":")[0]);
}
