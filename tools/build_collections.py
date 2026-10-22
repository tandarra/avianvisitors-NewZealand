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

Usage: python tools/build_collections.py [--cache DIR]
       python tools/build_collections.py --index-only      (just rebuild COLLECTIONS.md from the current data)
"""
import argparse, collections, datetime, json, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# id, repo, branch, region, creator, licence (None = no licence file: count and link, don't display)
SETS = [
    ("wna", "Twarner491/AvianVisitors", "avian-visitors", "Western North America", "Teddy Warner (Avian Visitors)", "CC BY-NC-SA 4.0"),
    ("vic", "TheWillni/AusVicVisitors", "main", "Victoria, Australia", "TheWillni", None),
    ("act", "opurtell/AvianVisitorsACT", "main", "Canberra / ACT, Australia", "opurtell", "CC BY-NC-SA 4.0"),
    ("eng", "lloydalexporter/AvianAssets_GB-ENG", "main", "England, UK", "lloydalexporter", None),
    ("dby", "jonnywright/AvianAssets", "main", "Derbyshire, UK", "jonnywright", None),
    ("ibe", "RoqueAlonso/AvianVisitors", "iberia-illustrations", "Iberian Peninsula (Madrid, Castilla-La Mancha)", "RoqueAlonso", "CC BY-NC-SA 4.0"),
    ("nld", "peterdeboer-nl/AvianVisitors", "avian-visitors", "Netherlands", "peterdeboer-nl", "CC BY-NC-SA 4.0"),
    ("deu", "bassrelic/AvianVisitors-German-Fork", "add_german_species", "Germany", "bassrelic", "CC BY-NC-SA 4.0"),
    ("fla", "SupraBitKid/AvianVisitors", "avian-visitors", "Florida, US", "SupraBitKid", "CC BY-NC-SA 4.0"),
    ("che", "theskyisthelimit/AvianVisitors", "europe-illustrations", "Switzerland", "theskyisthelimit", "CC BY-NC-SA 4.0"),
]

# eBird countries each set covers (for the COLLECTIONS.md index)
COVERS = {"wna": ["US", "CA"], "vic": ["AU"], "act": ["AU"], "eng": ["GB"], "dby": ["GB"], "ibe": ["ES"],
          "nld": ["NL"], "deu": ["DE"], "fla": ["US"], "che": ["CH"]}
HOME = {"region": "New Zealand", "creator": "Tandarra (this repo)", "repo": "tandarra/avianvisitors-NewZealand",
        "url": "https://github.com/tandarra/avianvisitors-NewZealand", "license": "CC BY-NC-SA 4.0", "covers": ["NZ"]}

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
    d = cache / sid
    if d.exists():
        git(d, "fetch", "-q", "--filter=blob:none", "origin", branch)
        git(d, "update-ref", "HEAD", "FETCH_HEAD")
    else:
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout", "--single-branch",
                        "-b", branch, f"https://github.com/{repo}.git", str(d)], check=True)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=str(ROOT / ".collections-cache"))
    ap.add_argument("--index-only", action="store_true")
    a = ap.parse_args()
    if a.index_only:
        return write_index()
    cache = Path(a.cache); cache.mkdir(parents=True, exist_ok=True)
    world = json.loads((ROOT / "birds" / "world.json").read_text(encoding="utf-8"))
    current = {slug(s[0]) for s in world["species"]}

    files = []          # (added, set index, current slug, pose, original slug, dir, ext, content hash)
    for i, (sid, repo, branch, *_rest) in enumerate(SETS):
        d = clone(cache, sid, repo, branch)
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
        print(f"{sid}: {repo}@{branch}: {n} illustrations")

    # credit each distinct image to the set that added it first
    first = {}
    for f in sorted(files):
        first.setdefault(f[7], f)
    img = collections.defaultdict(dict)       # current slug -> pose -> [set, original slug, dir, ext]
    credit = collections.defaultdict(set)
    for f in sorted(first.values()):          # earliest painting of each pose wins the display slot
        added, i, cur, pose, orig, dirp, ext, _ = f
        img[cur].setdefault(pose, [i, orig, dirp, ext])
        credit[i].add(cur)
    out = {
        "updated": datetime.datetime.now().isoformat(timespec="minutes"),
        "note": "Species illustrated by community Avian Visitors sets. Images stay in their repos; "
                "credit goes to the set that added each image first.",
        "sources": [{"id": s[0], "repo": s[1], "branch": s[2], "region": s[3], "creator": s[4], "license": s[5],
                     "url": f"https://github.com/{s[1]}/tree/{s[2]}", "species": len(credit[i])}
                    for i, s in enumerate(SETS)],
        "img": {k: {p: v for p, v in poses.items()} for k, poses in sorted(img.items())},
    }
    (ROOT / "birds" / "collections.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"\n{len(img)} species across {len(SETS)} sets -> birds/collections.json")
    for s in out["sources"]:
        print(f"  {s['species']:4} original species  {s['region']}  ({s['creator']})")
    write_index()


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
    sets = [dict(s, covers=COVERS.get(s["id"], [])) for s in col["sources"]] + [dict(HOME, species=len(painted))]
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
