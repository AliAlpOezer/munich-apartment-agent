// Secrets are not in wrangler.jsonc, so `wrangler types` cannot see them.
interface Env {
  API_TOKEN?: string;
}
declare namespace Cloudflare {
  interface Env {
    API_TOKEN?: string;
  }
}
