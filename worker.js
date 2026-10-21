// Cloudflare Worker entry (Workers + static assets). Serves the site from the repo
// and answers /api/today with the same handler the Pages Function uses.
import { onRequestGet } from "./functions/api/today.js";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/api/today" && request.method === "GET") {
      return onRequestGet({ request, env, waitUntil: (p) => ctx.waitUntil(p) });
    }
    return env.ASSETS.fetch(request);
  },
};
