// Shared helpers for the Pages Functions and the Worker entry.
export function origin(env) {
  return (env.BIRDNET_ORIGIN || "https://birdnet-api.tandarra.net").replace(/\/$/, "");
}
export function headers(env) {
  const h = { "User-Agent": "birds.tandarra.net" };
  if (env.CF_ACCESS_CLIENT_ID) {
    h["CF-Access-Client-Id"] = env.CF_ACCESS_CLIENT_ID;
    h["CF-Access-Client-Secret"] = env.CF_ACCESS_CLIENT_SECRET || "";
  }
  return h;
}
export const json = (body, status = 200, maxAge = 300) =>
  new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": status === 200 ? `public, max-age=${maxAge}` : "no-store",
    },
  });

/**
 * Best clip for a species: highest-confidence detection you've marked "correct" in
 * BirdNET-Go; if none (and VERIFIED_ONLY isn't "1"), the highest-confidence clip overall.
 * Only id/confidence/date/time/verified are returned — never sources or comments.
 */
export async function bestClip(env, sci) {
  const base = `${origin(env)}/api/v2/detections?species=${encodeURIComponent(sci)}&sortBy=confidence_desc&numResults=10`;
  const tries = [`${base}&verified=correct`];
  if (env.VERIFIED_ONLY !== "1") tries.push(base);
  for (const u of tries) {
    const r = await fetch(u, { headers: headers(env), cf: { cacheTtl: 300, cacheEverything: true } });
    if (!r.ok) continue;
    const d = await r.json();
    const hit = (d.data || []).find((x) => x.clipName && !x.spectrogramOnly && x.scientificName === sci);
    if (hit) {
      return {
        id: hit.id, confidence: hit.confidence, verified: hit.verified === "correct",
        date: hit.date, time: (hit.time || "").slice(0, 5), audio: `/api/audio/${hit.id}`,
      };
    }
  }
  return null;
}

export async function audio(env, request, id) {
  if (!/^\d+$/.test(id)) return new Response("bad id", { status: 400 });
  const h = headers(env);
  const range = request.headers.get("Range");
  if (range) h.Range = range;
  const r = await fetch(`${origin(env)}/api/v2/audio/${id}`, { headers: h, cf: { cacheTtl: 86400, cacheEverything: true } });
  if (!r.ok && r.status !== 206) return new Response("clip unavailable", { status: 404 });
  const out = new Headers();
  for (const k of ["Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"]) {
    const v = r.headers.get(k); if (v) out.set(k, v);
  }
  if (!out.get("Content-Type")) out.set("Content-Type", "audio/wav");
  out.set("Cache-Control", "public, max-age=86400");
  out.set("Content-Disposition", "inline");
  return new Response(r.body, { status: r.status, headers: out });
}
