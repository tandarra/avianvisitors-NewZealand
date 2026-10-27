#!/usr/bin/env python3
"""
Small JPEG paintings for the Garmin watch app (birds/watch/<slug>.jpg).

Watches can only load JPEG/PNG images (no WebP), so each species on a country's eBird list gets a
240 px perched painting on the cream paper ground. Same choice of painting as the atlas: a set marked
"prefer" first, then our own cut-out, then the first licensed community set (read from the blobless
clones in .collections-cache, so run tools/build_collections.py first). Only new or changed images
are written; birds/watch/index.json records where each one came from.

Usage: python tools/build_watch_thumbs.py [--country NZ] [--size 240]
"""
import argparse, io, json, subprocess
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PAPER = (239, 230, 210)          # #EFE6D2, the collage paper colour


def slug(s):
    import re
    return re.sub(r"[^a-z]+", "-", s.lower()).strip("-")


def source_for(sl, painted, col, prefer_ids, pose=""):
    """(label, loader) for the painting the atlas would show, or None. pose "" = perched, "-2" = in flight."""
    poses = col["img"].get(sl, {})
    p = poses.get(pose)
    if p and col["sources"][p[0]]["id"] in prefer_ids and col["sources"][p[0]]["license"]:
        return community(col, p)
    own = ROOT / "birds" / f"{sl}{pose}.webp"
    if sl in painted and own.exists():
        return f"own:{own.stat().st_size}", lambda: own.read_bytes()
    if p and col["sources"][p[0]]["license"]:
        return community(col, p)
    return None


def community(col, p):
    i, orig, dirp, ext = p
    s = col["sources"][i]
    path = f"{dirp}illustrations/{orig}.{ext}"
    cache = ROOT / ".collections-cache" / s["id"]
    def load():
        return subprocess.run(["git", "-C", str(cache), "show", f"HEAD:{path}"], capture_output=True, check=True).stdout
    return f"{s['id']}:{path}", load


def render(data, size):
    im = Image.open(io.BytesIO(data)).convert("RGBA")
    bbox = im.getchannel("A").point(lambda a: 255 if a > 24 else 0).getbbox()
    if bbox:
        im = im.crop(bbox)
    box = int(size * 0.9)
    im.thumbnail((box, box), Image.LANCZOS)
    out = Image.new("RGB", (size, size), PAPER)
    out.paste(im, ((size - im.width) // 2, (size - im.height) // 2), im)
    b = io.BytesIO()
    out.save(b, "JPEG", quality=84, optimize=True, progressive=False)
    return b.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--country", default="NZ")
    ap.add_argument("--size", type=int, default=240)
    a = ap.parse_args()
    world = json.loads((ROOT / "birds" / "world.json").read_text(encoding="utf-8"))
    col = json.loads((ROOT / "birds" / "collections.json").read_text(encoding="utf-8"))
    painted = set(json.loads((ROOT / "birds" / "painted.json").read_text(encoding="utf-8")))
    prefer_ids = {s["id"] for s in col["sources"] if s.get("prefer")}
    country = next(c for c in world["countries"] if c["code"] == a.country)
    out_dir = ROOT / "birds" / "watch"; out_dir.mkdir(exist_ok=True)
    idx_path = out_dir / "index.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {}
    made = kept = none = failed = 0
    for i in country["sp"]:
        base = slug(world["species"][i][0])
        for pose in ("", "-2"):                      # perched, then in flight (-2)
            sl = base + pose
            src = source_for(base, painted, col, prefer_ids, pose)
            if not src:
                none += 1; continue
            label, load = src
            f = out_dir / f"{sl}.jpg"
            if idx.get(sl) == label and f.exists():
                kept += 1; continue
            try:
                f.write_bytes(render(load(), a.size)); idx[sl] = label; made += 1
            except Exception as e:
                print(f"  {sl}: {e}"); failed += 1
    idx_path.write_text(json.dumps(dict(sorted(idx.items())), indent=0), encoding="utf-8")
    print(f"watch thumbs ({a.country}): {made} new/updated, {kept} unchanged, {none} not painted yet, {failed} failed")


if __name__ == "__main__":
    main()
