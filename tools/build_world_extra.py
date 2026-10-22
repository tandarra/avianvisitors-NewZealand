#!/usr/bin/env python3
"""
birds/world-extra.json: outlines for eBird countries the 110m world map leaves out (small islands,
overseas territories Natural Earth folds into a parent country). Taken from world-atlas countries-10m.json.
Places with no land in the data become a point (drawn as a small ring on the map).
Usage: python tools/build_world_extra.py path/to/countries-10m.json path/to/countries-110m.json
"""
import json, sys
from pathlib import Path

# eBird code -> (parent ISO numeric in Natural Earth, lon range, lat range) for territories folded into a parent
SPLIT = {
    "GF": ("250", (-55, -51), (2, 6.5)),        # French Guiana      (France)
    "GP": ("250", (-62, -60.9), (15.8, 16.6)),  # Guadeloupe
    "MQ": ("250", (-61.3, -60.7), (14.3, 14.95)),  # Martinique
    "RE": ("250", (55, 56), (-21.5, -20.8)),    # Réunion
    "YT": ("250", (44.9, 45.4), (-13.1, -12.5)),  # Mayotte
    "CP": ("250", (-109.4, -109.0), (10.1, 10.5)),  # Clipperton
    "SJ": ("578", (-10, 40), (70.5, 81)),       # Svalbard & Jan Mayen (Norway)
    "BV": ("578", (3, 4), (-55, -54)),          # Bouvet Island
    "BQ": ("528", (-69, -62.5), (11.9, 18)),    # Caribbean Netherlands
    "CX": ("036", (105.4, 105.9), (-10.7, -10.3)),  # Christmas Island (Australia)
    "CC": ("036", (96.7, 97.1), (-12.3, -11.8)),  # Cocos (Keeling) Islands
    "AC": ("036", (122.8, 123.7), (-12.6, -12.1)),  # Ashmore and Cartier Islands
    "CS": ("036", (147, 158), (-24, -12)),      # Coral Sea Islands
    "TK": ("554", (-172.7, -171), (-9.6, -8.3)),  # Tokelau (New Zealand)
}
POINTS = {"CX": (105.69, -10.45), "CC": (96.85, -12.15), "AC": (123.0, -12.3), "CS": (152.0, -17.0), "CP": (-109.22, 10.3), "BV": (3.4, -54.4),
          "TK": (-171.8, -9.2), "XK": (20.9, 42.6)}
NAME_ALIASES = {"XK": "Kosovo"}


def decode(topo):
    sx, sy = topo["transform"]["scale"]; tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0; pts = []
        for dx, dy in arc:
            x += dx; y += dy; pts.append((round(x * sx + tx, 3), round(y * sy + ty, 3)))
        arcs.append(pts)
    return arcs


def ring(arcs, idx):
    pts = []
    for i in idx:
        a = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts.extend(a if not pts else a[1:])
    return pts


def polygons(g, arcs):
    polys = [g["arcs"]] if g["type"] == "Polygon" else g["arcs"] if g["type"] == "MultiPolygon" else []
    return [[ring(arcs, r) for r in poly] for poly in polys]


def thin(r, tol=.02):
    out = [r[0]]
    for p in r[1:-1]:
        if abs(p[0] - out[-1][0]) + abs(p[1] - out[-1][1]) >= tol:
            out.append(p)
    out.append(r[-1])
    return out if len(out) >= 4 else r


def main(p10, p110):
    t10, t110 = json.loads(Path(p10).read_text()), json.loads(Path(p110).read_text())
    have110 = {g.get("id") for g in t110["objects"]["countries"]["geometries"]}
    arcs = decode(t10)
    geoms = t10["objects"]["countries"]["geometries"]
    by_id = {g.get("id"): g for g in geoms}
    by_name = {g["properties"]["name"]: g for g in geoms}
    world = json.loads((Path(__file__).resolve().parent.parent / "birds" / "world.json").read_text(encoding="utf-8"))
    feats, report = [], []
    for c in world["countries"]:
        code, iso = c["code"], c["iso"]
        if iso and iso in have110:
            continue
        fid = iso or code
        polys = []
        if code in SPLIT:
            parent, (x0, x1), (y0, y1) = SPLIT[code]
            for poly in polygons(by_id[parent], arcs):
                xs = [p[0] for p in poly[0]]; ys = [p[1] for p in poly[0]]
                cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
                if x0 <= cx <= x1 and y0 <= cy <= y1:
                    polys.append(poly)
        else:
            g = by_id.get(iso) if iso else None
            g = g or by_name.get(NAME_ALIASES.get(code, c["name"]))
            if g:
                polys = polygons(g, arcs)
        if polys:
            geom = {"type": "MultiPolygon", "coordinates": [[thin(r) for r in poly] for poly in polys]}
            report.append(f"{code} shape ({len(polys)} parts)")
        elif code in POINTS:
            geom = {"type": "Point", "coordinates": list(POINTS[code])}
            report.append(f"{code} point")
        else:
            report.append(f"{code} NONE ({c['name']})")
            continue
        feats.append({"type": "Feature", "id": fid, "properties": {"name": c["name"], "code": code}, "geometry": geom})
    out = Path(__file__).resolve().parent.parent / "birds" / "world-extra.json"
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")), encoding="utf-8")
    print("\n".join(report)); print(f"Wrote {out} ({out.stat().st_size // 1024} KB, {len(feats)} places)")


if __name__ == "__main__":
    main(*sys.argv[1:3])
