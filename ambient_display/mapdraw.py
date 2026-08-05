"""The map slide: Natural Earth coastlines, equirectangular, one dot.

The GeoJSON is vendored (data/) and pre-clipped to South America, so this
never touches the network and never fetches a tile.
"""

import json
import os
from functools import lru_cache

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "data", "ne_110m_coastline_sa.json")


@lru_cache(maxsize=4)
def coastlines(path=DATA):
    """-> (list of [lon,lat] runs, clip bbox dict)."""
    with open(path, "r", encoding="utf-8") as handle:
        doc = json.load(handle)
    runs = []
    for feature in doc.get("features", []):
        geom = feature.get("geometry") or {}
        if geom.get("type") == "MultiLineString":
            runs.extend(geom["coordinates"])
        elif geom.get("type") == "LineString":
            runs.append(geom["coordinates"])
    return runs, doc.get("properties", {}).get("clip", {})


def projector(box, clip):
    """Equirectangular lon/lat -> px, aspect preserved and centred in `box`.

    At this scale a proper projection would buy nothing: the continent is
    69 degrees tall and the map is eighty pixels.
    """
    x, y, w, h = box
    west, east = clip["west"], clip["east"]
    south, north = clip["south"], clip["north"]
    dw, dh = east - west, north - south
    scale = min(w / dw, h / dh)
    mw, mh = dw * scale, dh * scale
    ox, oy = x + (w - mw) / 2.0, y + (h - mh) / 2.0

    def project(lon, lat):
        return (ox + (lon - west) * scale, oy + (north - lat) * scale)

    return project, (ox, oy, mw, mh)


def in_bounds(lat, lon, clip):
    return (clip["west"] <= lon <= clip["east"]
            and clip["south"] <= lat <= clip["north"])


def draw(image, box, lat, lon, coast_ink, dot_ink, halo_ink=None, path=DATA):
    """Draw the coastline into `box` and mark lat/lon. -> the dot's position."""
    from PIL import ImageDraw

    runs, clip = coastlines(path)
    project, _ = projector(box, clip)
    draw_ctx = ImageDraw.Draw(image)

    for run in runs:
        points = [project(lon_, lat_) for lon_, lat_ in run]
        if len(points) > 1:
            draw_ctx.line(points, fill=coast_ink, width=1, joint="curve")

    if lat is None or lon is None or not in_bounds(lat, lon, clip):
        return None

    px, py = project(lon, lat)
    # A ring one step down from the dot reads as "here" without becoming the
    # brightest thing on a panel whose whole point is restraint.
    if halo_ink:
        draw_ctx.ellipse([px - 3.5, py - 3.5, px + 3.5, py + 3.5],
                         outline=halo_ink, width=1)
    draw_ctx.ellipse([px - 1.5, py - 1.5, px + 1.5, py + 1.5], fill=dot_ink)
    return (px, py)
