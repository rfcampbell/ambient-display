"""One recording, told in three slides.

The placard stays on a single recording and turns pages inside it -- name
and place, then where that is, then what the habitat was -- rather than
cutting between buses. A minute and a half on each.
"""

from dataclasses import dataclass, field

from . import mapdraw


@dataclass
class Slide:
    key: str
    kind: str                                     # name | map | habitat
    label: str = ""
    head: list = field(default_factory=list)      # variants, most specific first
    sub: str = ""
    place: list = field(default_factory=list)
    body: list = field(default_factory=list)
    foot: str = ""
    lat: float = None
    lon: float = None


def _mappable(record):
    if record.lat is None or record.lon is None:
        return False
    try:
        _, clip = mapdraw.coastlines()
    except (OSError, ValueError):
        return False
    return mapdraw.in_bounds(record.lat, record.lon, clip)


def slides_for(record, with_map=True):
    """-> the pages for this record, in order."""
    has_map = with_map and _mappable(record)
    out = []

    # The place line is redundant on a soundscape: the headline is already the
    # locality and the label is already the country. The moment lives on the
    # map slide, where it pairs with the dot -- unless there is no map.
    out.append(Slide(
        key=record.key + "#name",
        kind="name",
        label=record.label,
        head=list(record.headline),
        sub=record.subhead,
        place=[] if record.is_soundscape else list(record.place),
        foot="" if has_map else record.when,
    ))

    if has_map:
        out.append(Slide(
            key=record.key + "#map",
            kind="map",
            label=(record.country or record.label or "").upper(),
            foot=record.when,
            lat=record.lat,
            lon=record.lon,
        ))

    if record.remark:
        # A recordist's name that has to be truncated is worse than no
        # credit at all; the vocalisation type is the better footnote anyway.
        credit = record.recordist if len(record.recordist) <= 22 else ""
        out.append(Slide(
            key=record.key + "#habitat",
            kind="habitat",
            label="HABITAT",
            body=list(record.remark),
            foot=record.kind or credit,
        ))

    return out
