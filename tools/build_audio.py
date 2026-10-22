#!/usr/bin/env python3
"""
Bird sounds and eBird codes for the atlas (runs daily on GitHub, see .github/workflows/update-collections.yml).

1. eBird species codes: downloads the public eBird taxonomy (no key needed) and adds each species' code to
   birds/world.json, so the atlas can link straight to ebird.org/species/<code>.
2. One recording per species from xeno-canto (needs a free API key in XC_KEY; skipped without one).
   Picks the best-rated song (else call) and writes birds/audio.json:
     {"a": {slug: [xeno-canto id, recordist, licence, type, country, seconds]}, "none": {slug: "date checked"}}
   Recordings stay on xeno-canto (credited, under the recordist's licence); the atlas plays them from there.
   Illustrated species are fetched first; a run stops after --max lookups (xeno-canto asks for gentle use),
   so the first full pass takes a few days. Species with no recording are re-checked after 60 days.

Usage: python tools/build_audio.py [--max 2500]
"""
import argparse, csv, datetime, io, json, os, re, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAXONOMY = "https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=csv"
XC = "https://xeno-canto.org/api/3/recordings"
UA = {"User-Agent": "bird-atlas (github.com/tandarra/avianvisitors-NewZealand)"}


def slug(name):
    return re.sub(r"[^a-z]+", "-", name.lower()).strip("-")


def get(url, tries=3):
    for n in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404) or n == tries - 1:
                raise
        except Exception:
            if n == tries - 1:
                raise
        time.sleep(5 * (n + 1))


def add_codes():
    path = ROOT / "birds" / "world.json"
    world = json.loads(path.read_text(encoding="utf-8"))
    rows = csv.DictReader(io.StringIO(get(TAXONOMY).decode("utf-8")))
    by_sci = {r["SCIENTIFIC_NAME"].lower(): r["SPECIES_CODE"] for r in rows}
    changed = 0
    for sp in world["species"]:
        code = by_sci.get(sp[0].lower())
        if code and (len(sp) < 3 or sp[2] != code):
            del sp[2:]; sp.append(code); changed += 1
    missing = sum(1 for sp in world["species"] if len(sp) < 3)
    if changed:
        path.write_text(json.dumps(world, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"eBird codes: {changed} added/updated, {missing} species without a code")


LIC = [("by-nc-sa", "CC BY-NC-SA"), ("by-nc-nd", "CC BY-NC-ND"), ("by-nc", "CC BY-NC"), ("by-sa", "CC BY-SA"),
       ("by-nd", "CC BY-ND"), ("by", "CC BY"), ("zero", "CC0"), ("publicdomain", "CC0")]


def lic_short(url):
    u = (url or "").lower()
    ver = re.search(r"/(\d\.\d)/", u)
    for k, name in LIC:
        if f"/{k}/" in u:
            return name + (f" {ver.group(1)}" if ver and name != "CC0" else "")
    return url or "?"


def seconds(t):
    try:
        parts = [int(x) for x in str(t).split(":")]
        return sum(v * 60 ** i for i, v in enumerate(reversed(parts)))
    except ValueError:
        return 0


def best(recs):
    """Prefer: quality A > B > C, song > call, 8-60 s long, then xeno-canto's own order."""
    def score(r):
        q = {"A": 0, "B": 1, "C": 2}.get(r.get("q"), 3)
        t = (r.get("type") or "").lower()
        kind = 0 if "song" in t else 1 if "call" in t else 2
        s = seconds(r.get("length"))
        fit = 0 if 8 <= s <= 60 else 1
        return (q, kind, fit)
    recs = [r for r in recs if r.get("file") and not r.get("also") == "?"]
    return min(recs, key=score) if recs else None


def add_audio(key, limit):
    path = ROOT / "birds" / "audio.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    have, none = data.get("a", {}), data.get("none", {})
    world = json.loads((ROOT / "birds" / "world.json").read_text(encoding="utf-8"))
    painted = set(json.loads((ROOT / "birds" / "painted.json").read_text(encoding="utf-8")))
    col = json.loads((ROOT / "birds" / "collections.json").read_text(encoding="utf-8"))
    illustrated = painted | set(col["img"])
    wide = {}
    for c in world["countries"]:
        for i in c["sp"]:
            wide[i] = wide.get(i, 0) + 1
    today = datetime.date.today()
    recheck = (today - datetime.timedelta(days=60)).isoformat()
    todo = [(slug(sp[0]) not in illustrated, -wide.get(i, 0), sp[0]) for i, sp in enumerate(world["species"])
            if slug(sp[0]) not in have and none.get(slug(sp[0]), "") < recheck]
    todo.sort()
    print(f"xeno-canto: {len(have)} species have a recording, {len(todo)} to look up, doing up to {limit}")
    done = found = 0
    for _, _, sci in todo[:limit]:
        q = urllib.parse.quote(f'sp:"{sci}"')
        try:
            res = json.loads(get(f"{XC}?query={q}&key={urllib.parse.quote(key)}&per_page=100"))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                print(f"xeno-canto refused the key ({e.code}); stopping"); break
            print(f"  {sci}: HTTP {e.code}"); continue
        except Exception as e:
            print(f"  {sci}: {e.__class__.__name__}"); continue
        r = best(res.get("recordings") or [])
        s = slug(sci)
        if r:
            have[s] = [r["id"], r.get("rec", ""), lic_short(r.get("lic")), (r.get("type") or "").split(",")[0].strip(),
                       r.get("cnt", ""), seconds(r.get("length"))]
            none.pop(s, None); found += 1
        else:
            none[s] = today.isoformat()
        done += 1
        if done % 200 == 0:
            print(f"  {done} looked up, {found} found")
        time.sleep(1.0)
    out = {"updated": data.get("updated", ""), "source": "xeno-canto.org (each recording under its recordist's licence)",
           "a": dict(sorted(have.items())), "none": dict(sorted(none.items()))}
    if done:
        out["updated"] = datetime.datetime.now().isoformat(timespec="minutes")
        path.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print(f"xeno-canto: looked up {done}, found {found}; {len(have)} species with a recording")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=2500, help="xeno-canto lookups this run")
    a = ap.parse_args()
    try:
        add_codes()
    except Exception as e:
        print(f"eBird taxonomy unavailable: {e}")
    key = os.environ.get("XC_KEY", "").strip()
    if key:
        add_audio(key, a.max)
    else:
        print("XC_KEY not set: skipping recordings (add a free xeno-canto API key as a repository secret)")


if __name__ == "__main__":
    main()
