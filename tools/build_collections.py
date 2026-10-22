#!/usr/bin/env python3
"""
birds/collections.json: which species the community Avian Visitors sets have illustrated, so the atlas can
track world completion across everyone's work without copying their images.

For each set it does a *blobless* git clone (file list + history, no image data), finds
illustrations/<scientific-name>[-2].png, and works out who painted each image first: identical files
(same git content hash) in several sets are credited to the set that added them earliest, so forks
are only credited for the birds they added. Old scientific names are mapped to the current eBird
taxonomy with RENAMES. Images are shown on the atlas straight from the source repo (raw.githubusercontent)
only for sets with an open licence; the rest are counted and linked, not displayed.

The set list follows the community "Japanese Woodblock" bundles in Avian Visitors' catalogue
(avian/frontend/assets/bundle-catalog/catalog/bundles-v1.json in Twarner491/AvianVisitors).

Also writes COLLECTIONS.md: an index of countries and the illustration sets that cover them.

Sets come from SEED below (checked by hand), plus any Japanese Woodblock community pack in the official
catalogue (avianvisitors.com/catalog/bundles-v1.json), plus tools/extra_sets.json. Runs daily on GitHub
(.github/workflows/update-collections.yml); --forks also lists unlisted forks with new illustrations.

Usage: python tools/build_collections.py [--cache DIR] [--forks]
       python tools/build_collections.py --index-only      (just rebuild COLLECTIONS.md from the current data)
"""
import argparse, collections, datetime, json, os, re, subprocess, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPSTREAM = ("Twarner491/AvianVisitors", "avian-visitors")
CATALOG_URLS = ["https://avianvisitors.com/catalog/bundles-v1.json",
                "https://avianvisitors.com/api/bundles/catalog/discovery-v1.json"]
CATALOG_IN_REPO = "avian/frontend/assets/bundle-catalog/catalog/bundles-v1.json"

# Sets checked by hand (licence and coverage confirmed). Anything else in the official catalogue with the
# Japanese Woodblock style is added automatically; extra sets you approve go in tools/extra_sets.json.
# license None = no licence file: counted and linked, images not displayed.
SEED = [
    dict(id="wna", repo="Twarner491/AvianVisitors", branch="avian-visitors", region="Western North America",
         creator="Teddy Warner (Avian Visitors)", license="CC BY-NC-SA 4.0", covers=["US", "CA"]),
    dict(id="vic", repo="TheWillni/AusVicVisitors", branch="main", region="Victoria, Australia",
         creator="TheWillni", license=None, covers=["AU"]),
    dict(id="act", repo="opurtell/AvianVisitorsACT", branch="main", region="Canberra / ACT, Australia",
         creator="opurtell", license="CC BY-NC-SA 4.0", covers=["AU"]),
    dict(id="eng", repo="lloydalexporter/AvianAssets_GB-ENG", branch="main", region="England, UK",
         creator="lloydalexporter", license=None, covers=["GB"]),
    dict(id="dby", repo="jonnywright/AvianAssets", branch="main", region="Derbyshire, UK",
         creator="jonnywright", license=None, covers=["GB"]),
    dict(id="ibe", repo="RoqueAlonso/AvianVisitors", branch="iberia-illustrations",
         region="Iberian Peninsula (Madrid, Castilla-La Mancha)", creator="RoqueAlonso", license="CC BY-NC-SA 4.0", covers=["ES"]),
    dict(id="nld", repo="peterdeboer-nl/AvianVisitors", branch="avian-visitors", region="Netherlands",
         creator="peterdeboer-nl", license="CC BY-NC-SA 4.0", covers=["NL"]),
    dict(id="deu", repo="bassrelic/AvianVisitors-German-Fork", branch="add_german_species", region="Germany",
         creator="bassrelic", license="CC BY-NC-SA 4.0", covers=["DE"]),
    dict(id="fla", repo="SupraBitKid/AvianVisitors", branch="avian-visitors", region="Florida, US",
         creator="SupraBitKid", license="CC BY-NC-SA 4.0", covers=["US"]),
    dict(id="che", repo="theskyisthelimit/AvianVisitors", branch="europe-illustrations", region="Switzerland",
         creator="theskyisthelimit", license="CC BY-NC-SA 4.0", covers=["CH"]),
]
HOME = {"region": "New Zealand", "creator": "Tandarra (this repo)", "repo": "tandarra/avianvisitors-NewZealand",
        "url": "https://github.com/tandarra/avianvisitors-NewZealand", "license": "CC BY-NC-SA 4.0", "covers": ["NZ"]}
EXTRA = ROOT / "tools" / "extra_sets.json"     # {"sets": [...same fields as SEED...], "ignore": ["owner/repo", ...]}

# file names using older scientific names -> current eBird name
RENAMES = {
    "accipiter-cirrocephalus": "Tachyspiza cirrocephala", "accipiter-cooperii": "Astur cooperii",
    "accipiter-fasciatus": "Tachyspiza fasciata", "accipiter-gentilis": "Astur gentilis",
    "accipiter-novaehollandiae": "Tachyspiza novaehollandiae", "bubulcus-ibis": "Ardea ibis",
    "cacomantis-pallidus": "Heteroscenes pallidus", "calyptorhynchus-funereus": "Zanda funerea",
    "charadrius-bicinctus": "Anarhynchus bicinctus", "charadrius-dubius": "Thinornis dubius",
    "charadrius-leschenaultii": "Anarhynchus leschenaultii", "charadrius-veredus": "Anarhynchus veredus",
    "chrysococcyx-basalis": "Chalcites basalis", "chrysococcyx-lucidus": "Chalcites lucidus",
    "chrysococcyx-osculans": "Chalcites osculans", "coccothraustes-vespertinus": "Hesperiphona vespertina",
    "corvus-monedula": "Coloeus monedula", "dryobates-villosus": "Leuconotopicus villosus",
    "elseyornis-melanops": "Thinornis melanops", "glossopsitta-concinna": "Trichoglossus concinnus",
    "haliaeetus-leucogaster": "Icthyophaga leucogaster", "ixobrychus-dubius": "Botaurus dubius",
    "ixobrychus-exilis": "Botaurus exilis", "ixobrychus-flavicollis": "Botaurus flavicollis",
    "leiothlypis-lucidae": "Leiothlypis luciae", "lophochroa-leadbeateri": "Cacatua leadbeateri",
    "mirafra-cantillans": "Mirafra javanica", "oreothlypis-ruficapilla": "Leiothlypis ruficapilla",
    "parvipsitta-porphyrocephala": "Psitteuteles porphyrocephalus", "parvipsitta-pusilla": "Psitteuteles pusillus",
    "phalacrocorax-auritus": "Nannopterum auritum", "psephotus-varius": "Psephotellus varius",
    "regulus-calendula": "Corthylio calendula", "streptopelia-chinensis": "Spilopelia chinensis",
}
PAT = re.compile(r"^(.*?/)?illustrations/([a-z]+(?:-[a-z]+)+?)(-[2-9])?\.(png|webp|jpe?g)$")
slug = lambda s: re.sub(r"[^a-z]+", "-", s.lower()).strip("-")


def git(d, *a):
    return subprocess.run(["git", "-C", str(d), *a], capture_output=True, text=True, check=True).stdout


def clone(cache, sid, repo, branch):
    """Blobless clone (file list + history, no image data). branch None = the repo's default branch."""
    d = cache / sid
    if d.exists():
        b = branch or git(d, "rev-parse", "--abbrev-ref", "HEAD").strip()
        git(d, "fetch", "-q", "--filter=blob:none", "origin", b)
        git(d, "update-ref", "HEAD", "FETCH_HEAD")
    else:
        cmd = ["git", "clone", "-q", "--filter=blob:none", "--no-checkout", "--single-branch"]
        subprocess.run(cmd + (["-b", branch] if branch else []) + [f"https://github.com/{repo}.git", str(d)], check=True)
    return d, branch or git(d, "rev-parse", "--abbrev-ref", "HEAD").strip()


def detect_license(d):
    """Best guess at an image licence from the repo's LICENSE file (None if there isn't an open one)."""
    names = [n for n in git(d, "ls-tree", "--name-only", "HEAD").split() if re.match(r"(?i)licen[cs]e", n)]
    if not names:
        return None
    try:
        t = git(d, "show", f"HEAD:{names[0]}")
    except subprocess.CalledProcessError:
        return None
    if "NonCommercial-ShareAlike" in t or ("Creative Commons" in t and "NonCommercial" in t and "ShareAlike" in t) \
            or "BirdNET-Pi are licensed under a Creative Commons" in t:       # forks of Avian Visitors
        return "CC BY-NC-SA 4.0"
    if "Attribution-NonCommercial" in t: return "CC BY-NC 4.0"
    if "Attribution-ShareAlike" in t: return "CC BY-SA 4.0"
    if "CC0" in t or "Public Domain Dedication" in t: return "CC0"
    if "Attribution 4.0" in t: return "CC BY 4.0"
    if t.lstrip().startswith("MIT") or "Permission is hereby granted, free of charge" in t: return "MIT"
    return None


def fetch_json(url, token=None):
    req = urllib.request.Request(url, headers={"User-Agent": "bird-atlas-collections",
                                               **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def catalogue(cache):
    """Community packs in the official Avian Visitors catalogue (live site first, upstream repo as fallback)."""
    data = None
    for url in CATALOG_URLS:
        try:
            data = fetch_json(url); print(f"catalogue: {url}"); break
        except Exception as e:
            print(f"catalogue: {url} unavailable ({e.__class__.__name__})")
    if data is None:
        d, _ = clone(cache, "wna", *UPSTREAM)
        data = json.loads(git(d, "show", f"HEAD:{CATALOG_IN_REPO}")); print("catalogue: upstream repo copy")
    packs = data.get("packs") or data.get("bundles") or []
    out = []
    for p in packs:
        style = (p.get("style") or {}).get("id", "")
        m = re.match(r"https://github\.com/([^/]+/[^/#?]+?)(?:\.git)?(?:/tree/([^#?]+?))?/?$", p.get("repository_url") or "")
        if not m or "woodblock" not in (style + p.get("id", "")):
            continue
        cov = p.get("coverage") or {}
        out.append(dict(repo=m.group(1), branch=m.group(2), region=cov.get("label") or p.get("name"),
                        creator=p.get("creator") or m.group(1).split("/")[0],
                        covers=sorted({c.split("-")[0] for c in cov.get("region_codes") or []})))
    return out


def all_sets(cache):
    """Seed sets + new catalogue sets + approved extras, minus ignored."""
    extra = json.loads(EXTRA.read_text(encoding="utf-8")) if EXTRA.exists() else {}
    ignore = {r.lower() for r in extra.get("ignore", [])}
    sets = [dict(s) for s in SEED] + [dict(s) for s in extra.get("sets", [])]
    known = {(s["repo"].lower(), (s.get("branch") or "").lower()) for s in sets}
    known_repo = {s["repo"].lower() for s in sets}
    for p in catalogue(cache):
        key = (p["repo"].lower(), (p["branch"] or "").lower())
        if key in known or p["repo"].lower() in ignore:
            continue
        if p["repo"].lower() in known_repo and not p["branch"]:
            continue
        p["id"] = slug(f"{p['creator']}-{p['region']}")[:40]
        p["new"] = True
        sets.append(p); known.add(key)
        print(f"NEW set from the catalogue: {p['region']} by {p['creator']} ({p['repo']})")
    return [s for s in sets if s["repo"].lower() not in ignore]


def scan_forks(sets, token, days=60, limit=60):
    """Forks of Avian Visitors that recently added illustrations and aren't listed yet: candidates to review."""
    known = {s["repo"].lower() for s in sets}
    extra = json.loads(EXTRA.read_text(encoding="utf-8")) if EXTRA.exists() else {}
    known |= {r.lower() for r in extra.get("ignore", [])}
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    api, out, checked = "https://api.github.com", [], 0
    forks = []
    for page in range(1, 6):
        batch = fetch_json(f"{api}/repos/{UPSTREAM[0]}/forks?sort=newest&per_page=100&page={page}", token)
        forks += batch
        if len(batch) < 100: break
    recent = [f for f in forks if f["full_name"].lower() not in known and
              datetime.datetime.fromisoformat(f["pushed_at"].replace("Z", "+00:00")) > cutoff]
    recent.sort(key=lambda f: f["pushed_at"], reverse=True)
    print(f"forks: {len(forks)} total, {len(recent)} pushed in the last {days} days and not yet listed")
    for f in recent:
        try:
            branches = [b["name"] for b in fetch_json(f"{api}/repos/{f['full_name']}/branches?per_page=20", token)]
        except Exception:
            continue
        best = None
        for b in sorted(branches, key=lambda b: b != f["default_branch"])[:4]:
            if checked >= limit: break
            checked += 1
            try:
                cmp = fetch_json(f"{api}/repos/{UPSTREAM[0]}/compare/{UPSTREAM[1]}...{f['owner']['login']}:{b}", token)
            except Exception:
                continue
            added = [x["filename"] for x in cmp.get("files", []) if x.get("status") == "added" and PAT.match(x["filename"])]
            sp = {PAT.match(x).group(2) for x in added}
            if len(sp) >= 10 and (not best or len(sp) > best[1]):
                best = (b, len(sp))
        if best:
            out.append({"repo": f["full_name"], "branch": best[0], "species_added": best[1], "pushed": f["pushed_at"][:10],
                        "url": f"https://github.com/{f['full_name']}/tree/{best[0]}"})
        if checked >= limit: break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(ROOT / ".collections-cache"))
    ap.add_argument("--index-only", action="store_true")
    ap.add_argument("--forks", action="store_true", help="also look for unlisted forks with new illustrations "
                                                          "(needs GITHUB_TOKEN); writes candidates.md")
    a = ap.parse_args()
    if a.index_only:
        return write_index()
    cache = Path(a.cache); cache.mkdir(parents=True, exist_ok=True)
    world = json.loads((ROOT / "birds" / "world.json").read_text(encoding="utf-8"))
    current = {slug(s[0]) for s in world["species"]}
    sets = all_sets(cache)

    files = []          # (added, set index, current slug, pose, original slug, dir, ext, content hash)
    usable = []
    for s in sets:
        try:
            d, branch = clone(cache, s["id"], s["repo"], s.get("branch"))
        except subprocess.CalledProcessError as e:
            print(f"{s['id']}: could not read {s['repo']} ({e}); skipped this run")
            continue
        s["branch"] = branch
        if "license" not in s:
            s["license"] = detect_license(d)
        i = len(usable); usable.append(s)
        added, t = {}, None
        for line in git(d, "log", "--diff-filter=A", "--format=C %ct", "--name-only", "--", "*illustrations/*").splitlines():
            if line.startswith("C "): t = int(line[2:])
            elif line.strip(): added[line.strip()] = t          # newest first, so the last write is the oldest
        n = 0
        for line in git(d, "ls-tree", "-r", "HEAD").splitlines():
            meta, path = line.split("\t", 1)
            m = PAT.match(path)
            if not m:
                continue
            orig = m.group(2)
            cur = slug(RENAMES[orig]) if orig in RENAMES else orig
            if cur not in current:
                continue
            files.append((added.get(path) or 9e18, i, cur, m.group(3) or "", orig, m.group(1) or "", m.group(4), meta.split()[2]))
            n += 1
        print(f"{s['id']}: {s['repo']}@{branch}: {n} illustrations, licence {s['license']}")

    # credit each distinct image to the set that added it first
    first = {}
    for f in sorted(files):
        first.setdefault(f[7], f)
    img = collections.defaultdict(dict)       # current slug -> pose -> [set, original slug, dir, ext]
    credit = collections.defaultdict(set)
    # display slot: sets marked "prefer" first, then the earliest painting of each pose
    for f in sorted(first.values(), key=lambda f: (not usable[f[1]].get("prefer"), f)):
        added, i, cur, pose, orig, dirp, ext, _ = f
        img[cur].setdefault(pose, [i, orig, dirp, ext])
        credit[i].add(cur)
    out = {
        "updated": datetime.datetime.now().isoformat(timespec="minutes"),
        "note": "Species illustrated by community Avian Visitors sets. Images stay in their repos; "
                "credit goes to the set that added each image first.",
        "sources": [{"id": s["id"], "repo": s["repo"], "branch": s["branch"], "region": s["region"], "creator": s["creator"],
                     "license": s["license"], "covers": s.get("covers", []),
                     **({"prefer": True} if s.get("prefer") else {}),
                     "url": f"https://github.com/{s['repo']}/tree/{s['branch']}", "species": len(credit[i])}
                    for i, s in enumerate(usable)],
        "img": {k: {p: v for p, v in poses.items()} for k, poses in sorted(img.items())},
    }
    path = ROOT / "birds" / "collections.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if {k: v for k, v in old.items() if k != "updated"} == {k: v for k, v in out.items() if k != "updated"}:
        print("\nNo changes in any set.")
    else:
        path.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
        print(f"\n{len(img)} species across {len(usable)} sets -> birds/collections.json")
        write_index()
    for s in out["sources"]:
        print(f"  {s['species']:4} original species  {s['region']}  ({s['creator']})")

    if a.forks:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        try:
            cands = scan_forks(sets, token)
        except Exception as e:                   # never let the fork check block the daily update
            print(f"fork scan failed: {e}"); cands = None
        if cands is None:
            return
        md = ROOT / "candidates.md"
        if cands:
            lines = ["Forks of Avian Visitors that recently added illustrations but aren't in the atlas yet. "
                     "Check the style matches (Japanese woodblock / kachō-e), then either add the set to "
                     "`tools/extra_sets.json` under `sets` (repo, branch, region, creator, covers) or under `ignore`.", "",
                     "| Repository | Branch | New species | Last push |", "|---|---|---|---|"]
            lines += [f"| [{c['repo']}]({c['url']}) | `{c['branch']}` | {c['species_added']} | {c['pushed']} |" for c in cands]
            md.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print(f"{len(cands)} candidate set(s) -> candidates.md")
        elif md.exists():
            md.unlink()


def write_index():
    """COLLECTIONS.md: countries with an illustration set, linked to the sets, with completion."""
    world = json.loads((ROOT / "birds" / "world.json").read_text(encoding="utf-8"))
    col = json.loads((ROOT / "birds" / "collections.json").read_text(encoding="utf-8"))
    painted = json.loads((ROOT / "birds" / "painted.json").read_text(encoding="utf-8"))
    slugs = [slug(s[0]) for s in world["species"]]
    poses = collections.defaultdict(set)                      # species -> poses illustrated by anyone
    for sl, files in painted.items():
        poses[sl] |= {"p" for f in files if f == f"{sl}.webp"} | {"f" for f in files if f == f"{sl}-2.webp"}
    for sl, ps in col["img"].items():
        poses[sl] |= {"p" if k == "" else "f" for k in ps}
    done = lambda sp: sum(1 for i in sp if len(poses[slugs[i]]) == 2)
    countries = {c["code"]: c for c in world["countries"]}
    sets = [dict(s, covers=s.get("covers") or []) for s in col["sources"]] + [dict(HOME, species=len(painted))]
    by_country = collections.defaultdict(list)
    for s in sets:
        for cc in s["covers"]:
            by_country[cc].append(s)
    lic = lambda s: s["license"] or "none stated"
    lines = ["# Illustration sets by country", "",
             "Kachō-e / Japanese woodblock bird illustrations in the [Avian Visitors](https://theodore.net/projects/AvianVisitors/) style, "
             "listed by country. Each set lives in its artist's own repository; follow the links for the images. "
             "\"Illustrated\" counts species with both poses painted by any set, against that country's eBird species list. "
             "Explore it all on the map: **[Bird Atlas](https://birds.tandarra.net/atlas.html)**.", "",
             "> **Official bundles:** to install a set on your own Avian Visitors station, or to share yours, use the "
             "official bundle library at **[avianvisitors.com/bundles](https://avianvisitors.com/bundles)**. "
             "This page is an index of the sets; the bundle library is where they are published.", "",
             "| Country | Illustrated | Illustration sets |", "|---|---|---|"]
    for cc in sorted(by_country, key=lambda c: countries[c]["name"]):
        c = countries[cc]; d = done(c["sp"]); n = len(c["sp"])
        links = "<br>".join(f"[{s['region']}]({s['url']}) by {s['creator']}" for s in by_country[cc])
        lines.append(f"| [{c['name']}](https://birds.tandarra.net/atlas.html#{cc}) | {d:,} / {n:,} ({d / n * 100:.0f}%) | {links} |")
    lines += ["", "## All sets", "", "| Set | Artist | Repository | Species first painted here | Licence |", "|---|---|---|---|---|"]
    for s in sorted(sets, key=lambda s: -s["species"]):
        lines.append(f"| {s['region']} | {s['creator']} | [{s['repo']}]({s['url']}) | {s['species']:,} | {lic(s)} |")
    total = sum(1 for sl in slugs if len(poses[sl]) == 2)
    lines += ["", f"**World:** {total:,} of {len(slugs):,} eBird species illustrated ({total / len(slugs) * 100:.1f}%), "
              f"updated {col['updated'][:10]}.", "",
              "Sets are those in the Avian Visitors \"Japanese Woodblock\" community bundle catalogue "
              "([avianvisitors.com/bundles](https://avianvisitors.com/bundles)). Each image is credited "
              "to the set that added it first, so forks are credited only for the birds they added. Sets without a licence "
              "file are counted and linked but their images are not reproduced here. Know of another set? Publish it at "
              "[avianvisitors.com/bundles](https://avianvisitors.com/bundles) and open an issue here.", ""]
    (ROOT / "COLLECTIONS.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote COLLECTIONS.md ({len(by_country)} countries, {len(sets)} sets)")


if __name__ == "__main__":
    main()
