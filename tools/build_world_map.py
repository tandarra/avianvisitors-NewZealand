#!/usr/bin/env python3
"""
Build birds/world_map.svg for the atlas page.

Source: world-atlas countries-50m.json (Natural Earth, public domain, packaged by
Mike Bostock under ISC). Download once with:  npm pack world-atlas@2.0.2
Usage:  python tools/build_world_map.py path/to/countries-50m.json
"""
import json, math, sys
from pathlib import Path

W = 1000                      # SVG width; height follows the projection
SKIP = {"010"}                # Antarctica
TOL = 1.1                    # drop points closer than this (px) to the previous one

# Victoria, Australia: west border at 141E, then roughly along the Murray to the Indi
# source and the straight line to Cape Howe; closed through open sea so the coastline
# comes from the Australia shape (used as an SVG clip).
VICTORIA = [(141.0, -33.9), (141.6, -34.15), (142.4, -34.7), (143.3, -35.05), (143.6, -35.4),
            (144.4, -35.75), (144.95, -35.95), (145.6, -35.9), (146.3, -36.0), (147.0, -36.1),
            (147.6, -35.95), (148.05, -36.35), (148.2, -36.8), (149.98, -37.5), (151.0, -38.5),
            (151.0, -40.5), (140.9, -40.5)]


def equal_earth(lon, lat):
    A1, A2, A3, A4 = 1.340264, -0.081106, 0.000893, 0.003796
    M = math.sqrt(3) / 2
    lam, phi = math.radians(lon), math.radians(lat)
    t = math.asin(M * math.sin(phi))
    t2, t6 = t * t, t ** 6
    x = 2 * math.sqrt(3) * lam * math.cos(t) / (3 * (A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2)))
    y = t * (A1 + A2 * t2 + t6 * (A3 + A4 * t2))
    return x, y


XMAX = equal_earth(180, 0)[0]
YMAX = equal_earth(0, 90)[1]
YMIN = equal_earth(0, -58)[1]          # crop the far south (no Antarctica)
S = W / (2 * XMAX)
H = round((YMAX - YMIN) * S)


def px(lon, lat):
    x, y = equal_earth(lon, lat)
    return (x + XMAX) * S, (YMAX - y) * S


def decode(topo):
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx; y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    return arcs


def ring(arcs, idx):
    pts = []
    for i in idx:
        a = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts.extend(a if not pts else a[1:])
    return pts


def unwrap(r):
    """Keep rings that cross the date line on one side; the overhang is clipped by the map edge."""
    if any(abs(a[0] - b[0]) > 180 for a, b in zip(r, r[1:])):
        east = sum(lon for lon, _ in r) / len(r) > 0
        r = [((lon + 360) if east and lon < 0 else (lon - 360) if not east and lon > 0 else lon, lat)
             for lon, lat in r]
    return r


def path_d(rings):
    out = []
    for r in map(unwrap, rings):
        last = None
        seg = []
        for lon, lat in r:
            p = px(lon, lat)
            if last is None or math.dist(p, last) >= TOL:
                seg.append(p); last = p
        if len(seg) < 4:
            continue
        out.append("M" + "L".join(f"{round(x, 1):g},{round(y, 1):g}" for x, y in seg) + "Z")
    return "".join(out)


def main(src):
    topo = json.loads(Path(src).read_text())
    arcs = decode(topo)
    paths = []
    for g in topo["objects"]["countries"]["geometries"]:
        cid = g.get("id")
        if cid in SKIP or g["type"] not in ("Polygon", "MultiPolygon"):
            continue
        polys = [g["arcs"]] if g["type"] == "Polygon" else g["arcs"]
        rings = [ring(arcs, r) for poly in polys for r in poly]
        d = path_d(rings)
        if d:
            name = g["properties"]["name"].replace("&", "&amp;")
            paths.append(f'<path id="c{cid}" data-name="{name}" d="{d}"/>')
    # graticule (every 30 degrees) for a mapmaker's feel
    grat = []
    for lon in range(-180, 181, 30):
        grat.append("M" + "L".join("%.1f,%.1f" % px(lon, lat) for lat in range(-58, 91, 2)))
    for lat in range(-30, 90, 30):
        grat.append("M" + "L".join("%.1f,%.1f" % px(lon, lat) for lon in range(-180, 181, 2)))
    outline = ("M" + "L".join("%.1f,%.1f" % px(-180, lat) for lat in range(-58, 91, 2))
               + "L" + "L".join("%.1f,%.1f" % px(180, lat) for lat in range(90, -59, -2)) + "Z")
    vic = "M" + "L".join("%.1f,%.1f" % px(lon, lat) for lon, lat in VICTORIA) + "Z"
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" id="map" role="img" '
           f'aria-label="World map">\n'
           f'<path class="sea" d="{outline}"/>\n<path class="grat" d="{"".join(grat)}"/>\n'
           f'<clipPath id="edge"><path d="{outline}"/></clipPath>\n'
           f'<g id="land" clip-path="url(#edge)">\n' + "\n".join(paths) + '\n</g>\n'
           f'<clipPath id="vicclip"><path d="{vic}"/></clipPath>\n</svg>\n')
    out = Path(__file__).resolve().parent.parent / "birds" / "world_map.svg"
    out.write_text(svg, encoding="utf-8")
    print(f"Wrote {out} ({len(svg) / 1024:.0f} KB, {len(paths)} countries, {W}x{H})")
    # handy for placing labels
    for name, (lon, lat) in {"NZ": (172.5, -41.5), "US": (-98, 39), "GB": (-2.5, 54),
                             "DE": (10.4, 51.1), "VIC": (144.5, -37.2)}.items():
        print(name, "%.1f,%.1f" % px(lon, lat))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "countries-50m.json")
