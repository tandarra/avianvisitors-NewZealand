#!/usr/bin/env python3
"""
Trim the empty cream paper around master paintings (birds/raw/*.png): crop to the bird plus a margin.
The paper colour is read from each image's own edges, so it works whatever shade Gemini painted.
Already-trimmed images are left alone (re-running is safe).

Gemini's "PNG" files are usually JPEG data. Those are cropped losslessly with jpegtran (no
re-compression, so no quality loss and smaller files); real PNGs are re-saved as PNG.

Usage: python tools/trim_masters.py [folder ...]      (default: birds/raw)
"""
import shutil, subprocess, sys, tempfile
from pathlib import Path

import numpy as np
from PIL import Image

MARGIN = 0.04      # margin kept around the bird, as a share of the longer side
THRESH = 34        # colour distance from the paper that counts as "painting"
MIN_FILL = 0.004   # a row/column needs this share of painted pixels (ignores paper grain and specks)


def trim(path):
    im = Image.open(path)
    rgb = np.asarray(im.convert("RGB")).astype(np.int16)
    h, w, _ = rgb.shape
    edge = np.concatenate([rgb[:6].reshape(-1, 3), rgb[-6:].reshape(-1, 3),
                           rgb[:, :6].reshape(-1, 3), rgb[:, -6:].reshape(-1, 3)])
    paper = np.median(edge, axis=0)
    ink = np.abs(rgb - paper).sum(axis=2) > THRESH
    rows = np.where(ink.mean(axis=1) > MIN_FILL)[0]
    cols = np.where(ink.mean(axis=0) > MIN_FILL)[0]
    if not len(rows) or not len(cols):
        return None
    m = int(max(h, w) * MARGIN)
    box = (max(cols[0] - m, 0), max(rows[0] - m, 0), min(cols[-1] + 1 + m, w), min(rows[-1] + 1 + m, h))
    if box[2] - box[0] >= w - 4 and box[3] - box[1] >= h - 4:
        return None                              # nothing worth trimming
    if im.format == "JPEG" and shutil.which("jpegtran"):
        # lossless: jpegtran snaps the top-left corner to the 8/16 px block grid, so the margin may grow a few px
        cw, ch = box[2] - box[0], box[3] - box[1]
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            pass
        subprocess.run(["jpegtran", "-crop", f"{cw}x{ch}+{box[0]}+{box[1]}", "-copy", "none", "-optimize",
                        "-outfile", tmp.name, str(path)], check=True)
        shutil.move(tmp.name, path)
    else:
        im.crop(box).save(path, optimize=True)
    return box, (w, h)


def main(folders):
    n = 0
    for folder in folders or ["birds/raw"]:
        for p in sorted(Path(folder).glob("*.png")):
            r = trim(p)
            if r:
                n += 1
                (x0, y0, x1, y1), (w, h) = r
                print(f"  {p.name}: {w}x{h} -> {x1 - x0}x{y1 - y0}")
    print(f"Trimmed {n} image(s).")


if __name__ == "__main__":
    main(sys.argv[1:])
