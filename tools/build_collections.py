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

Usage: python tools/build_collections.py [--cache DIR]
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
    a = ap.parse_args()
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


if __name__ == "__main__":
    main()
