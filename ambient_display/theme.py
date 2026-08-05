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
    # Family and per-role style. A role may also name a .ttf path directly.
    "family": "Noto Serif",
    "head_font": "regular",
    "sci_font": "italic",
    "place_font": "regular",
    "remark_font": "italic",
    "bus_font": "regular",

    # Frame. Keep margins >= burnin amplitude + 2 so nothing clips when shifted.
    "margin_x": 9,
    "margin_y": 7,
    "vertical_bias": 0.40,   # 0 = stack hugs top, 1 = hugs bottom

    # Headline autofits: largest of these that wraps into head_max_lines wins.
    "head_sizes": [22, 20, 18, 16, 14, 12],
    "head_max_lines": 3,
    "head_leading": 1.04,

    "sci_size": 10,
    "sci_leading": 1.12,
    "sci_max_lines": 2,

    "place_size": 10,
    "place_leading": 1.18,
    "place_max_lines": 2,

    "remark_size": 9,
    "remark_leading": 1.22,
    "remark_max_lines": 3,

    "bus_size": 7,
    "bus_tracking": 1.6,
    "show_bus": True,

    # Vertical gaps between blocks. Squeezed proportionally if the card is full.
    "gap_bus_head": 9,
    "gap_head_sci": 3,
    "gap_sci_rule": 7,
    "gap_rule_place": 7,
    "gap_place_remark": 4,

    "rule_width": 22,
    "show_rule": True,

    # Dim, warm ink on black. Nothing here should approach 255.
    #
    # The headline is 22px and the body is 9-10px, so size already carries the
    # hierarchy -- the small text doesn't need to be much darker to read as
    # secondary, and at this size it can't afford to be. The secondary tiers
    # sit close under the headline; the rule and the bus label stay quiet.
    "ink_head": "#b8ac90",
    "ink_sci": "#9c9280",
    "ink_rule": "#544c40",
    "ink_place": "#a89e88",
    "ink_remark": "#8e8574",
    "ink_bus": "#847a68",
    "max_channel": 200,
}

# Keys whose values are numbers, for coercing preview query overrides.
_INT_KEYS = {
    "margin_x", "margin_y", "head_max_lines", "sci_size", "sci_max_lines",
    "place_size", "place_max_lines", "remark_size", "remark_max_lines",
    "bus_size", "gap_bus_head", "gap_head_sci", "gap_sci_rule",
    "gap_rule_place", "gap_place_remark", "rule_width", "max_channel",
}
_FLOAT_KEYS = {
    "vertical_bias", "head_leading", "sci_leading", "place_leading",
    "remark_leading", "bus_tracking",
}
_BOOL_KEYS = {"show_bus", "show_rule"}


def merged(overrides=None):
    """Theme defaults with overrides applied."""
    t = dict(DEFAULTS)
    t["head_sizes"] = list(DEFAULTS["head_sizes"])
    if overrides:
        t.update(overrides)
    return t


def coerce(key, value):
    """Coerce a string (from a query param) to the type the theme key wants."""
    if key == "head_sizes":
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
