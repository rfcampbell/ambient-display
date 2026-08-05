"""Compose a slide onto a 128x128 RGB frame.

Pure: (slide, theme, offset, brightness) -> Image, so the web preview and the
panel cannot disagree about what is on screen.
"""

from dataclasses import dataclass, field

from PIL import Image, ImageDraw

from . import mapdraw
from . import theme as theme_mod

ELLIPSIS = "…"


@dataclass
class Block:
    lines: list = field(default_factory=list)
    font: object = None
    lh: int = 1
    color: tuple = (0, 0, 0)
    top_ink: float = 0.0
    height: float = 0.0
    tracking: float = 0.0
    rule: bool = False
    custom: object = None       # callable(image, x, y, width)


# --- text fitting -----------------------------------------------------------

def _split_long_word(word, font, max_w):
    parts, rest = [], word
    while font.getlength(rest) > max_w and len(rest) > 1:
        cut = len(rest) - 1
        while cut > 1 and font.getlength(rest[:cut] + "-") > max_w:
            cut -= 1
        if cut <= 1:
            break
        parts.append(rest[:cut] + "-")
        rest = rest[cut:]
    parts.append(rest)
    return parts


def wrap(text, font, max_w):
    """Wrap, balancing raggedness rather than filling greedily: minimises the
    sum of squared slack over every line but the last."""
    words = []
    for word in (text or "").split():
        if font.getlength(word) > max_w:
            words.extend(_split_long_word(word, font, max_w))
        else:
            words.append(word)
    n = len(words)
    if n == 0:
        return []

    widths = [font.getlength(w) for w in words]
    space = font.getlength(" ")
    inf = float("inf")
    cost = [inf] * (n + 1)
    brk = [n] * (n + 1)
    cost[n] = 0.0
    for i in range(n - 1, -1, -1):
        width = 0.0
        for j in range(i, n):
            width = widths[j] if j == i else width + space + widths[j]
            if width > max_w and j > i:
                break
            slack = max_w - width
            penalty = 0.0 if j == n - 1 else slack * slack
            if cost[j + 1] + penalty < cost[i]:
                cost[i] = cost[j + 1] + penalty
                brk[i] = j + 1

    lines, i = [], 0
    while i < n:
        j = brk[i]
        lines.append(" ".join(words[i:j]))
        i = j
    return lines


def _truncate(lines, font, max_w, max_lines):
    if len(lines) <= max_lines:
        return lines
    kept = lines[:max_lines]
    last = kept[-1]
    while last and font.getlength(last + ELLIPSIS) > max_w:
        last = last[:-1].rstrip()
    kept[-1] = last.rstrip(",;:.- ") + ELLIPSIS
    return kept


def _first_fitting(candidates, font, max_w, max_lines):
    for text in candidates or ():
        lines = wrap(text, font, max_w)
        if lines and len(lines) <= max_lines:
            return lines
    return None


def _needs_break(text, font, max_w):
    return any(font.getlength(w) > max_w for w in (text or "").split())


def _autofit(variants, font_of, sizes, max_w, max_lines, min_size=0):
    """Largest size at which the most specific variant still fits.

    Walks variants most-specific first and takes the first that fits at a
    size worth calling a headline; only if none do does it fall back to
    whatever fits at all. Hyphen-breaking is avoided unless nothing else works.
    """
    best = None
    for allow_break in (False, True):
        for text in variants or ():
            for size in sizes:
                font = font_of(size)
                if not allow_break and _needs_break(text, font, max_w):
                    continue
                lines = wrap(text, font, max_w)
                if len(lines) <= max_lines:
                    if size >= min_size:
                        return lines, font
                    if best is None:
                        best = (lines, font)
                    break
        if best:
            return best
    if not variants:
        return None, None
    font = font_of(sizes[-1])
    return _truncate(wrap(variants[-1], font, max_w), font, max_w, max_lines), font


def _block(lines, font, leading, color, tracking=0.0):
    if not lines:
        return None
    lh = max(1, int(round(font.size * leading)))
    top = font.getbbox(lines[0])[1]
    bottom = font.getbbox(lines[-1])[3]
    return Block(lines=lines, font=font, lh=lh, color=color, top_ink=top,
                 height=(len(lines) - 1) * lh + (bottom - top), tracking=tracking)


# --- slide -> blocks --------------------------------------------------------

def _stack_height(blocks, gaps, squeeze=1.0):
    return sum(b.height for b in blocks) + sum(g * squeeze for g in gaps[1:])


def _blocks_for(slide, t, width, height):
    cap = t["max_channel"]
    max_w = width - 2 * t["margin_x"]
    ink = lambda key: theme_mod.ink(t[key], cap)                    # noqa: E731
    font = lambda role, size: theme_mod.load(t["family"], t[role], size)  # noqa: E731

    named = []
    pending = [0]

    def add(name, block, gap):
        if block is None:
            pending[0] += gap
            return
        named.append((name, block, (pending[0] + gap) if named else 0))
        pending[0] = 0

    if t["show_label"] and slide.label:
        add("label", _block([slide.label.upper()], font("label_font", t["label_size"]),
                            1.0, ink("ink_label"), t["label_tracking"]), 0)

    if slide.kind == "map":
        coast, dot = ink("ink_coast"), ink("ink_dot")
        halo = ink("ink_rule")
        lat, lon = slide.lat, slide.lon

        def draw_map(image, x, y, w):
            mapdraw.draw(image, (x, y, w, t["map_height"]), lat, lon,
                         coast, dot, halo)

        add("map", Block(height=t["map_height"], custom=draw_map),
            t["gap_label_map"])
        add("foot", _foot(slide.foot, t, font, ink, max_w), t["gap_map_foot"])
        return named, max_w

    if slide.kind == "habitat":
        lines, body_font = _autofit(slide.body,
                                    lambda s: font("body_font", s),
                                    t["body_sizes"], max_w, t["body_max_lines"])
        add("body", _block(lines, body_font, t["body_leading"], ink("ink_body"))
            if lines else None, t["gap_label_body"])
        add("foot", _foot(slide.foot, t, font, ink, max_w), t["gap_body_foot"])
        return named, max_w

    # kind == "name"
    lines, head_font = _autofit(slide.head, lambda s: font("head_font", s),
                                t["head_sizes"], max_w, t["head_max_lines"],
                                min_size=t.get("head_min_size", 0))
    add("head", _block(lines, head_font, t["head_leading"], ink("ink_head"))
        if lines else None, t["gap_label_head"])

    sub_block = None
    if slide.sub:
        sub_font = font("sub_font", t["sub_size"])
        sub_block = _block(_truncate(wrap(slide.sub, sub_font, max_w),
                                     sub_font, max_w, t["sub_max_lines"]),
                           sub_font, t["sub_leading"], ink("ink_sub"))
    add("sub", sub_block, t["gap_head_sub"])

    place_font = font("place_font", t["place_size"])
    place_lines = _first_fitting(slide.place, place_font, max_w, t["place_max_lines"])
    if place_lines is None and slide.place:
        place_lines = _truncate(wrap(slide.place[-1], place_font, max_w),
                                place_font, max_w, t["place_max_lines"])

    foot_block = _foot(slide.foot, t, font, ink, max_w)

    # On a name slide the rule sits under the headline as a title rule, so it
    # earns its place even when nothing follows it -- that hairline plus the
    # letterspaced label is what still reads as a placard.
    rule = None
    if t["show_rule"] and lines:
        rule = Block(height=1, rule=True, color=ink("ink_rule"))
    add("rule", rule, t["gap_sub_rule"])

    add("place", _block(place_lines, place_font, t["place_leading"], ink("ink_place"))
        if place_lines else None, t["gap_rule_place"])
    add("foot", foot_block, t["gap_place_foot"])
    return named, max_w


def _foot(text, t, font, ink, max_w):
    if not text:
        return None
    foot_font = font("foot_font", t["foot_size"])
    lines = _truncate(wrap(text, foot_font, max_w), foot_font, max_w, 1)
    return _block(lines, foot_font, 1.15, ink("ink_foot"))


def _shed(named, max_w):
    """Drop one increment of the least important surviving content."""
    index = {name: i for i, (name, _, _) in enumerate(named)}
    for name in ("body", "place", "sub"):
        if name in index:
            block = named[index[name]][1]
            if len(block.lines) > 1:
                trimmed = _truncate(block.lines, block.font, max_w,
                                    len(block.lines) - 1)
                named[index[name]] = (name, _block(trimmed, block.font,
                                                   block.lh / block.font.size,
                                                   block.color),
                                      named[index[name]][2])
                return True
    for name in ("foot", "rule", "sub", "place", "body", "label"):
        if name in index:
            i = index[name]
            gap = named.pop(i)[2]
            if i < len(named):
                nm, blk, own = named[i]
                named[i] = (nm, blk, own + gap)
            if named:
                first = named[0]
                named[0] = (first[0], first[1], 0)
            return True
    head = index.get("head")
    if head is not None:
        block = named[head][1]
        if len(block.lines) > 1:
            trimmed = _truncate(block.lines, block.font, max_w, len(block.lines) - 1)
            named[head] = ("head", _block(trimmed, block.font,
                                          block.lh / block.font.size, block.color),
                           named[head][2])
            return True
    return False


# --- drawing ----------------------------------------------------------------

def _draw_line(draw, x, y, text, font, color, tracking):
    if tracking:
        for char in text:
            draw.text((x, y), char, font=font, fill=color, anchor="la")
            x += font.getlength(char) + tracking
    else:
        draw.text((x, y), text, font=font, fill=color, anchor="la")


def render_slide(slide, t, size=(128, 128), offset=(0.0, 0.0), brightness=1.0):
    """Draw one slide. `offset` is the burn-in shift, in (fractional) px."""
    width, height = size
    image = Image.new("RGB", size, (0, 0, 0))
    if brightness <= 0.0 or slide is None:
        return image

    named, max_w = _blocks_for(slide, t, width, height)
    if not named:
        return image
    avail = height - 2 * t["margin_y"]

    def fits(items, squeeze):
        return _stack_height([b for _, b, _ in items],
                             [g for _, _, g in items], squeeze) <= avail

    squeeze = 1.0
    while True:
        if fits(named, 1.0):
            break
        if fits(named, 0.65):
            lo, hi = 0.65, 1.0
            for _ in range(8):
                mid = (lo + hi) / 2
                if fits(named, mid):
                    lo = mid
                else:
                    hi = mid
            squeeze = lo
            break
        if not _shed(named, max_w):
            squeeze = 0.65
            break

    blocks = [b for _, b, _ in named]
    gaps = [g for _, _, g in named]
    total = _stack_height(blocks, gaps, squeeze)

    off_x, off_y = offset
    x = t["margin_x"] + off_x
    y = t["margin_y"] + (avail - total) * t["vertical_bias"] + off_y

    draw = ImageDraw.Draw(image)
    for i, (_, block, gap) in enumerate(named):
        if i:
            y += gap * squeeze
        if block.custom is not None:
            block.custom(image, x, y, max_w)
        elif block.rule:
            draw.line([(x, round(y)), (x + t["rule_width"] - 1, round(y))],
                      fill=block.color, width=1)
        else:
            top = y - block.top_ink
            for j, line in enumerate(block.lines):
                _draw_line(draw, x, top + j * block.lh, line,
                           block.font, block.color, block.tracking)
        y += block.height

    if brightness < 1.0:
        image = dim(image, brightness)
    return image


def dim(image, factor):
    """Scale every channel. Night fade and the global trim both come through
    here; the panel's own contrast register is left alone."""
    factor = max(0.0, min(1.0, factor))
    return image.point([int(round(i * factor)) for i in range(256)] * 3)


def blend(a, b, alpha):
    if alpha <= 0.0:
        return a
    if alpha >= 1.0:
        return b
    return Image.blend(a, b, alpha)
