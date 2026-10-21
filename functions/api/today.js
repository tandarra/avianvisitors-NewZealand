// Cloudflare Pages Function: GET /api/today
// Returns the birds BirdNET-Go heard in the last N hours (default 24), merged from
// today's and yesterday's hourly counts. Only species names and counts leave the house.
//
// Env (Pages > Settings > Variables):
//   BIRDNET_ORIGIN        e.g. https://birdnet-api.tandarra.net   (tunnel, path-restricted)
//   CF_ACCESS_CLIENT_ID   optional Cloudflare Access service token for that hostname
//   CF_ACCESS_CLIENT_SECRET
//   TIMEZONE              default Pacific/Auckland

const DEFAULT_ORIGIN = "https://birdnet-api.tandarra.net";

function parts(date, tz) {
  const f = new Intl.DateTimeFormat("en-CA", {
    timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", hourCycle: "h23",
  });
  const p = Object.fromEntries(f.formatToParts(date).map((x) => [x.type, x.value]));
  return { day: `${p.year}-${p.month}-${p.day}`, hour: parseInt(p.hour, 10) };
}

function prevDay(day) {
  const [y, m, d] = day.split("-").map(Number);
  const t = new Date(Date.UTC(y, m - 1, d) - 86400000);
  return t.toISOString().slice(0, 10);
}

const slug = (s) => s.toLowerCase().replace(/[^a-z]+/g, "-").replace(/^-|-$/g, "");

async function daily(origin, day, headers) {
  const r = await fetch(`${origin}/api/v2/analytics/species/daily?date=${day}`, {
    headers, cf: { cacheTtl: 60, cacheEverything: true },
  });
  if (!r.ok) throw new Error(`BirdNET-Go ${r.status}`);
  return r.json();
}

export async function onRequestGet({ request, env, waitUntil }) {
  const url = new URL(request.url);
  const hours = Math.max(1, Math.min(24, parseInt(url.searchParams.get("hours") || "24", 10) || 24));
  const cache = caches.default;
  const key = new Request(`${url.origin}/api/today?hours=${hours}`);
  const hit = await cache.match(key);
  if (hit) return hit;

  const tz = env.TIMEZONE || "Pacific/Auckland";
  const origin = (env.BIRDNET_ORIGIN || DEFAULT_ORIGIN).replace(/\/$/, "");
  const headers = { "User-Agent": "birds.tandarra.net" };
  if (env.CF_ACCESS_CLIENT_ID) {
    headers["CF-Access-Client-Id"] = env.CF_ACCESS_CLIENT_ID;
    headers["CF-Access-Client-Secret"] = env.CF_ACCESS_CLIENT_SECRET || "";
  }

  const now = parts(new Date(), tz);
  const back = hours - (now.hour + 1);
  const byName = new Map();
  const add = (rows, from, to, isToday) => {
    for (const o of rows || []) {
      if (!o.scientific_name) continue;
      const h = o.hourly_counts || [];
      let n = 0;
      for (let k = from; k <= to && k < h.length; k++) n += h[k] || 0;
      if (!h.length && from === 0 && isToday) n = o.count || 0;
      if (n <= 0) continue;
      const s = byName.get(o.scientific_name) || {
        sci: o.scientific_name, com: o.common_name || o.scientific_name, slug: slug(o.scientific_name), count: 0, last: null,
      };
      s.count += n;
      if (isToday && o.latest_heard) s.last = o.latest_heard.slice(0, 5);
      else if (!s.last && o.latest_heard) s.last = o.latest_heard.slice(0, 5);
      byName.set(o.scientific_name, s);
    }
  };

  let body, status = 200;
  try {
    const jobs = [daily(origin, now.day, headers)];
    if (back > 0) jobs.push(daily(origin, prevDay(now.day), headers));
    const [today, yday] = await Promise.all(jobs);
    add(today, 0, now.hour, true);
    if (back > 0) add(yday, 24 - back, 23, false);
    const species = [...byName.values()].sort((a, b) => b.count - a.count);
    body = {
      updated: new Date().toISOString(), tz, hours,
      calls: species.reduce((a, s) => a + s.count, 0), species,
    };
  } catch (e) {
    status = 502;
    body = { error: "The listening station is offline right now.", species: [] };
  }

  const res = new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": status === 200 ? "public, max-age=60, s-maxage=120" : "no-store",
      "Access-Control-Allow-Origin": "*",
    },
  });
  if (status === 200) waitUntil(cache.put(key, res.clone()));
  return res;
}
