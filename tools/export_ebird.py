#!/usr/bin/env python3
"""
Export the birds BirdNET-Go heard (garden/CCTV audio) as an eBird "Record Format" CSV you can upload at
https://ebird.org/import/upload.form (choose "eBird Record Format (Extended)" or "eBird Record Format").

Run it on a computer that can reach BirdNET-Go (your home network). Nothing is sent anywhere else.
Only the Python standard library is needed.

  python tools/export_ebird.py --from 2026-09-01 --to 2026-10-27 \
      --origin http://homeassistant.local:8080 \
      --lat -37.25 --lon 175.0 --name "My garden" --state AUK

  # via the Cloudflare tunnel instead (service token in the environment):
  CF_ACCESS_CLIENT_ID=... CF_ACCESS_CLIENT_SECRET=... python tools/export_ebird.py --origin https://birdnet-api.tandarra.net ...

How it maps to eBird: one Stationary checklist per day. Start time = first hour with a detection, duration = until the end of
the last hour with one, "all observations reported" = N, count = X (a call count isn't a head count), and each species gets a
comment with the number of detections. Species heard fewer than --min-count times that day are left out (default 3).

The file has NO header row (eBird requires that) and no double quotes. Check it in a text editor before uploading.
eBird expects you to have verified the identification yourself, so review the species list (and BirdNET-Go's own review
tool) before you upload. Automated IDs you haven't checked shouldn't go in.
"""
import argparse, csv, datetime as dt, json, os, sys, urllib.request

# eBird Record Format column order (Appendix A): common name, genus, species, count, comments, location name, lat, lon,
# date MM/DD/YYYY, start time, state, country, protocol, observers, duration, all-obs, distance, area, checklist comments.


def fetch(origin, day):
    h = {"User-Agent": "export_ebird"}
    if os.environ.get("CF_ACCESS_CLIENT_ID"):
        h["CF-Access-Client-Id"] = os.environ["CF_ACCESS_CLIENT_ID"]
        h["CF-Access-Client-Secret"] = os.environ.get("CF_ACCESS_CLIENT_SECRET", "")
    with urllib.request.urlopen(urllib.request.Request(f"{origin}/api/v2/analytics/species/daily?date={day}", headers=h), timeout=60) as r:
        return json.loads(r.read())


def clean(s):
    return str(s).replace('"', "").replace(",", ";").replace("\n", " ").replace("\r", " ").strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", required=True, help="first day YYYY-MM-DD")
    ap.add_argument("--to", dest="end", default=dt.date.today().isoformat(), help="last day YYYY-MM-DD (default today)")
    ap.add_argument("--origin", default="http://localhost:8080", help="BirdNET-Go address")
    ap.add_argument("--name", required=True, help="location name, as in your eBird hotspot/personal location")
    ap.add_argument("--lat", required=True); ap.add_argument("--lon", required=True)
    ap.add_argument("--state", default="AUK", help="eBird region code after the country, e.g. AUK for Auckland")
    ap.add_argument("--country", default="NZ")
    ap.add_argument("--min-count", type=int, default=3, help="skip species with fewer detections than this per day")
    ap.add_argument("--out", default="ebird-upload.csv")
    a = ap.parse_args()
    origin = a.origin.rstrip("/")
    d, end = dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end)
    rows, days, species = [], 0, set()
    while d <= end:
        try:
            data = fetch(origin, d.isoformat())
        except Exception as e:
            print(f"{d}: {e}", file=sys.stderr); d += dt.timedelta(days=1); continue
        keep = []
        for o in data or []:
            sci, com = o.get("scientific_name"), o.get("common_name")
            h = o.get("hourly_counts") or []
            n = sum(h) if h else (o.get("count") or 0)
            if sci and n >= a.min_count:
                hrs = [i for i, v in enumerate(h) if v] or [0]
                keep.append((com or sci, sci, n, hrs[0], hrs[-1]))
        if keep:
            first = min(k[3] for k in keep); last = max(k[4] for k in keep)
            start, dur = f"{first:02d}:00", (last - first + 1) * 60
            for com, sci, n, _, _ in sorted(keep):
                g, _, s = sci.partition(" ")
                rows.append([com, g, s, "X", f"BirdNET-Go: {n} detections", a.name, a.lat, a.lon, d.strftime("%m/%d/%Y"),
                             start, a.state, a.country, "Stationary", 1, dur, "N", "", "",
                             "Audio detections from outdoor camera microphone (BirdNET-Go)"])
                species.add(sci)
            days += 1
        d += dt.timedelta(days=1)
    with open(a.out, "w", newline="", encoding="utf-8") as f:
        csv.writer(f, quoting=csv.QUOTE_NONE, escapechar="\\", lineterminator="\r\n").writerows([[clean(x) for x in r] for r in rows])
    print(f"{a.out}: {len(rows)} records, {len(species)} species, {days} checklists")


if __name__ == "__main__":
    main()
