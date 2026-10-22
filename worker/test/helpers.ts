import { env } from "cloudflare:workers";
import type { Fetcher } from "../src/bike";
import { loadSettings } from "../src/config";
import type { Deps } from "../src/pipeline";
import type { Job } from "../src/types";
import searchPage from "./fixtures/search-page.html?raw";

export const settings = loadSettings(env as unknown as Record<string, unknown>);

export interface FakeQueue {
  queue: Queue<Job>;
  sent: { body: Job; delaySeconds?: number }[];
}

export function fakeQueue(): FakeQueue {
  const sent: FakeQueue["sent"] = [];
  const queue = {
    async send(body: Job, opts?: { delaySeconds?: number }) {
      sent.push({ body, delaySeconds: opts?.delaySeconds });
    },
    async sendBatch(msgs: Iterable<{ body: Job; delaySeconds?: number }>) {
      for (const m of msgs) sent.push({ body: m.body, delaySeconds: m.delaySeconds });
    },
  } as unknown as Queue<Job>;
  return { queue, sent };
}

export type Route = (url: string, init?: RequestInit) => Response | Promise<Response>;

/** A fetcher that answers by the longest matching URL prefix and records every request. */
export function fakeFetcher(routes: Record<string, Route>): Fetcher & { calls: string[] } {
  const calls: string[] = [];
  const fn = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    calls.push(url);
    const key = Object.keys(routes)
      .filter((prefix) => url.startsWith(prefix))
      .sort((a, b) => b.length - a.length)[0];
    if (!key) throw new Error(`unexpected fetch ${url}`);
    return routes[key](url, init);
  };
  return Object.assign(fn, { calls });
}

/** Valhalla matrix answer: every source gets `minutes` (or a per-source function) to every target. */
export function valhallaRoute(minutesFor: (i: number) => number): Route {
  return async (_url, init) => {
    const body = JSON.parse(String(init?.body));
    const rows = body.sources.map((_: unknown, i: number) =>
      body.targets.map((_t: unknown, j: number) => ({
        from_index: i, to_index: j, time: minutesFor(i) * 60 + j * 30, distance: minutesFor(i) / 3,
      })),
    );
    return Response.json({ sources_to_targets: rows });
  };
}

export const html = (body: string, status = 200) =>
  new Response(body, { status, headers: { "content-type": "text/html; charset=utf-8" } });

export function deps(fetcher: Fetcher, q: FakeQueue, now = new Date("2026-10-22T12:00:00Z")): Deps {
  return { db: env.DB, jobs: q.queue, fetcher, settings, now: () => now };
}

export { searchPage };
