// Cloudflare Worker entry (Workers + static assets). Same routes as the Pages Functions.
import { onRequestGet as today } from "./functions/api/today.js";
import { bestClip, json, audio } from "./lib/birdnet.js";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (request.method === "GET") {
      if (url.pathname === "/api/today") return today({ request, env, waitUntil: (p) => ctx.waitUntil(p) });
      if (url.pathname === "/api/clip") {
        const sci = url.searchParams.get("sci") || "";
        if (!/^[A-Z][a-z]+ [a-z-]+$/.test(sci)) return json({ error: "bad species" }, 400);
        try { const c = await bestClip(env, sci); return c ? json(c) : json({ error: "no clip" }, 404); }
        catch { return json({ error: "station offline" }, 502); }
      }
      const m = url.pathname.match(/^\/api\/audio\/(\d+)$/);
      if (m) { try { return await audio(env, request, m[1]); } catch { return new Response("station offline", { status: 502 }); } }
    }
    return env.ASSETS.fetch(request);
  },
};
