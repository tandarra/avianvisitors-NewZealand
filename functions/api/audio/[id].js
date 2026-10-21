// GET /api/audio/:id -> the detection's audio clip (proxied, cached at the edge)
import { audio } from "../../../lib/birdnet.js";
export async function onRequestGet({ request, env, params }) {
  try { return await audio(env, request, String(params.id)); }
  catch (e) { return new Response("station offline", { status: 502 }); }
}
