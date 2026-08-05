"""Typography: font resolution and the tweakable theme dict.

The theme is a flat dict so it can be overridden from config.json or from
query parameters in the web preview. Colours are hex strings; sizes are px.
"""

import os
from functools import lru_cache

from PIL import ImageFont

# Font families we know how to find. Each style maps to candidate paths tried
# in order. Missing styles fall back to "regular".
FAMILIES = {
    # Sans with a tall x-height and open apertures. At 128px serif stems and
    # bracketed serifs land on half a pixel and break up; these don't.
    "Inter": {
        "thin": ["/usr/share/fonts/opentype/inter/Inter-Thin.otf"],
        "extralight": ["/usr/share/fonts/opentype/inter/Inter-ExtraLight.otf"],
        "light": ["/usr/share/fonts/opentype/inter/Inter-Light.otf"],
        "regular": ["/usr/share/fonts/opentype/inter/Inter-Regular.otf"],
        "medium": ["/usr/share/fonts/opentype/inter/Inter-Medium.otf"],
        "semibold": ["/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"],
        "bold": ["/usr/share/fonts/opentype/inter/Inter-Bold.otf"],
        "extrabold": ["/usr/share/fonts/opentype/inter/Inter-ExtraBold.otf"],
        "black": ["/usr/share/fonts/opentype/inter/Inter-Black.otf"],
    },
    "IBM Plex Sans": {
        "thin": ["/usr/share/fonts/truetype/ibm-plex/IBMPlexSans-Thin.ttf"],
        "extralight": ["/usr/share/fonts/truetype/ibm-plex/IBMPlexSans-ExtraLight.ttf"],
        "light": ["/usr/share/fonts/truetype/ibm-plex/IBMPlexSans-Light.ttf"],
        "regular": ["/usr/share/fonts/truetype/ibm-plex/IBMPlexSans-Regular.ttf"],
        "text": ["/usr/share/fonts/truetype/ibm-plex/IBMPlexSans-Text.ttf"],
        "medium": ["/usr/share/fonts/truetype/ibm-plex/IBMPlexSans-Medium.ttf"],
        "semibold": ["/usr/share/fonts/truetype/ibm-plex/IBMPlexSans-SemiBold.ttf"],
        "bold": ["/usr/share/fonts/truetype/ibm-plex/IBMPlexSans-Bold.ttf"],
    },
    "Noto Serif": {
        "regular": ["/usr/share/fonts/truetype/noto/NotoSerif-Regular.ttf"],
        "italic": ["/usr/share/fonts/truetype/noto/NotoSerif-Italic.ttf"],
        "bold": ["/usr/share/fonts/truetype/noto/NotoSerif-Bold.ttf"],
        "bold_italic": ["/usr/share/fonts/truetype/noto/NotoSerif-BoldItalic.ttf"],
    },
    "Noto Serif Display": {
        "regular": ["/usr/share/fonts/truetype/noto/NotoSerifDisplay-Regular.ttf"],
        "italic": ["/usr/share/fonts/truetype/noto/NotoSerifDisplay-Italic.ttf"],
        "bold": ["/usr/share/fonts/truetype/noto/NotoSerifDisplay-Bold.ttf"],
    },
    "Roboto Slab": {
        "regular": ["/usr/share/fonts/truetype/roboto-slab/RobotoSlab-Regular.ttf"],
        "light": ["/usr/share/fonts/truetype/roboto-slab/RobotoSlab-Light.ttf"],
        "bold": ["/usr/share/fonts/truetype/roboto-slab/RobotoSlab-Bold.ttf"],
    },
    "DejaVu Serif": {
        "regular": ["/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"],
        "bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"],
    },
    "Liberation Serif": {
        "regular": ["/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"],
        "italic": ["/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf"],
        "bold": ["/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"],
    },
    "Noto Sans": {
        "regular": ["/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"],
        "italic": ["/usr/share/fonts/truetype/noto/NotoSans-Italic.ttf"],
        "bold": ["/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"],
    },
}

# Extra places to look for a bundled font, so you can drop a .ttf next to the
# project and name it in the theme without installing it system-wide.
FONT_DIRS = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts"),
    os.path.expanduser("~/.local/share/fonts"),
    os.path.expanduser("~/.fonts"),
]

DEFAULTS = {
    # Family and per-role weight. A role may also name a font file directly.
    # There are no italics anywhere: at 9-11px a sloped sans is mush, so
    # weight does the work instead.
    "family": "Inter",
    "head_font": "semibold",
    "sub_font": "medium",
    "place_font": "regular",
    "body_font": "regular",
    "foot_font": "regular",
    "label_font": "semibold",

    # Frame. Keep margins >= burnin amplitude + 2 so nothing clips when shifted.
    "margin_x": 9,
    "margin_y": 7,
    "vertical_bias": 0.40,   # 0 = stack hugs top, 1 = hugs bottom

    # Headline autofits: largest of these that wraps into head_max_lines wins.
    "head_sizes": [24, 22, 20, 18, 16, 14, 12],
    "head_max_lines": 3,
    "head_leading": 1.06,
    # A more specific headline wins only while it still sets this big; below
    # it, a shorter, blunter variant is the better placard.
    "head_min_size": 16,

    "sub_size": 11,
    "sub_leading": 1.14,
    "sub_max_lines": 2,

    "place_size": 11,
    "place_leading": 1.18,
    "place_max_lines": 2,

    # The habitat slide gives the remark the whole card, so it can be big.
    "body_sizes": [15, 14, 13, 12, 11, 10],
    "body_max_lines": 6,
    "body_leading": 1.22,

    "foot_size": 9,

    # The letterspaced small-caps label and the hairline rule are what carry
    # the placard character now that the type is a sans.
    "label_size": 8,
    "label_tracking": 1.7,
    "show_label": True,
    "rule_width": 22,
    "show_rule": True,

    "map_height": 78,

    # Vertical gaps between blocks. Squeezed proportionally if a card is full.
    "gap_label_head": 9,
    "gap_head_sub": 3,
    "gap_sub_rule": 7,
    "gap_rule_place": 7,
    "gap_place_foot": 5,
    "gap_label_body": 9,
    "gap_body_foot": 7,
    "gap_label_map": 5,
    "gap_map_foot": 5,

    # Dim, warm ink on black. Nothing here should approach 255 -- the cap
    # leaves deliberate headroom, because this is judged on a monitor and the
    # OLED will read brighter in a dark room.
    "ink_head": "#ccc0a4",
    "ink_sub": "#b0a68e",
    "ink_place": "#bcb29a",
    "ink_body": "#b6ac94",
    "ink_foot": "#948b78",
    "ink_label": "#9a9080",
    "ink_rule": "#6a6152",
    "ink_coast": "#7d7464",
    "ink_dot": "#d8cbac",
    "max_channel": 225,
}

# Keys whose values are numbers, for coercing preview query overrides.
_INT_KEYS = {
    "margin_x", "margin_y", "head_max_lines", "sub_size", "sub_max_lines",
    "place_size", "place_max_lines", "body_max_lines", "foot_size",
    "label_size", "rule_width", "map_height", "max_channel", "head_min_size",
    "gap_label_head", "gap_head_sub", "gap_sub_rule", "gap_rule_place",
    "gap_place_foot", "gap_label_body", "gap_body_foot", "gap_label_map",
    "gap_map_foot",
}
_FLOAT_KEYS = {
    "vertical_bias", "head_leading", "sub_leading", "place_leading",
    "body_leading", "label_tracking",
}
_BOOL_KEYS = {"show_label", "show_rule"}
_LIST_KEYS = {"head_sizes", "body_sizes"}


def merged(overrides=None):
    """Theme defaults with overrides applied."""
    t = dict(DEFAULTS)
    for key in _LIST_KEYS:
        t[key] = list(DEFAULTS[key])
    if overrides:
        t.update(overrides)
    return t


def coerce(key, value):
    """Coerce a string (from a query param) to the type the theme key wants."""
    if key in _LIST_KEYS:
        return [int(v) for v in str(value).replace(",", " ").split()]
    if key in _INT_KEYS:
        return int(float(value))
    if key in _FLOAT_KEYS:
        return float(value)
    if key in _BOOL_KEYS:
        return str(value).lower() not in ("0", "false", "no", "off", "")
    return value


def parse_overrides(items):
    """Turn a mapping of theme-key -> string into typed overrides, ignoring
    keys the theme doesn't know about."""
    out = {}
    for key, value in items:
        if key in DEFAULTS:
            try:
                out[key] = coerce(key, value)
            except (TypeError, ValueError):
                pass
    return out


def _resolve_path(family, style):
    styles = FAMILIES.get(family, {})
    for candidate in styles.get(style, []) + styles.get("regular", []):
        if os.path.exists(candidate):
            return candidate
    # Unknown family: try to find "<Family>-<Style>.ttf" in the extra dirs.
    stem = family.replace(" ", "")
    for directory in FONT_DIRS:
        for name in (f"{stem}-{style.title()}.ttf", f"{stem}-Regular.ttf", f"{stem}.ttf"):
            path = os.path.join(directory, name)
            if os.path.exists(path):
                return path
    for fallback in FAMILIES["DejaVu Serif"]["regular"]:
        if os.path.exists(fallback):
            return fallback
    raise FileNotFoundError(f"no font file for {family} {style}")


@lru_cache(maxsize=256)
def load(family, style, size):
    """Load a TrueType face. `style` may also be a path to a .ttf."""
    path = style if style.endswith((".ttf", ".otf")) else _resolve_path(family, style)
    return ImageFont.truetype(path, size)


def available_families():
    """Families whose regular face is actually present on this machine."""
    out = []
    for name, styles in FAMILIES.items():
        if any(os.path.exists(p) for p in styles.get("regular", [])):
            out.append(name)
    return out


def ink(hex_color, cap=190, scale=1.0):
    """Hex string -> RGB tuple, channel-capped then scaled.

    Capping per channel (rather than turning the panel's global brightness
    down) is the burn-in lever: the pixels themselves are never driven hard.
    """
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return tuple(max(0, min(cap, int(round(c * scale)))) for c in rgb)
