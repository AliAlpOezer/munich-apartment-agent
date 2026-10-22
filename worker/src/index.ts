import { handleApi } from "./api";
import { loadSettings } from "./config";
import { handleJob, startRun, type Deps } from "./pipeline";
import type { Job } from "./types";

function deps(env: Env): Deps {
  return {
    db: env.DB,
    jobs: env.JOBS as Queue<Job>,
    fetcher: (input, init) => fetch(input, init),
    settings: loadSettings(env as unknown as Record<string, unknown>),
    now: () => new Date(),
  };
}

export default {
  async fetch(req, env) {
    if (new URL(req.url).pathname.startsWith("/api/")) {
      try {
        return await handleApi(req, env, deps(env));
      } catch (e) {
        console.error("api error", e);
        return Response.json({ error: "Internal error." }, { status: 500 });
      }
    }
    return env.ASSETS.fetch(req);
  },

  async scheduled(_controller, env) {
    await startRun(deps(env), "cron");
  },

  async queue(batch, env) {
    const d = deps(env);
    for (const msg of batch.messages) {
      const outcome = await handleJob(msg.body, msg.attempts, d);
      if (outcome.ack) msg.ack();
      else msg.retry({ delaySeconds: outcome.retryAfterSeconds });
    }
  },
} satisfies ExportedHandler<Env, Job>;
