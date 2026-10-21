// GET /api/clip?sci=Prosthemadera%20novaeseelandiae -> best clip for that species
import { bestClip, json } from "../../lib/birdnet.js";
export async function onRequestGet({ request, env }) {
  const sci = new URL(request.url).searchParams.get("sci") || "";
  if (!/^[A-Z][a-z]+ [a-z-]+$/.test(sci)) return json({ error: "bad species" }, 400);
  try {
    const c = await bestClip(env, sci);
    return c ? json(c) : json({ error: "no clip" }, 404);
  } catch (e) { return json({ error: "station offline" }, 502); }
}
