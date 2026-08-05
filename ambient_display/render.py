"""Compose a placard onto a 128x128 RGB frame.

Everything here is pure: (card, theme, offset, brightness) -> Image. That
keeps the web preview and the panel showing exactly the same pixels.
"""

from dataclasses import dataclass

from PIL import Image

from . import theme as theme_mod

ELLIPSIS = "…"


@dataclass
class Block:
    lines: list
    font: object
    lh: int
    color: tuple
    top_ink: float
    height: float
    tracking: float = 0.0
    rule: bool = False


# --- text fitting -----------------------------------------------------------

def _split_long_word(word, font, max_w):
    """Hyphen-break a word that can't fit on a line by itself."""
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
    """Wrap to lines, balancing raggedness rather than filling greedily.

    Minimises the sum of squared slack over every line but the last, which is
    what keeps a two-line headline from reading as one long line plus a stub.
    """
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
    """Clip a wrapped block to max_lines, ending in an ellipsis."""
    if len(lines) <= max_lines:
        return lines
    kept = lines[:max_lines]
    last = kept[-1]
    while last and font.getlength(last + ELLIPSIS) > max_w:
        last = last[:-1].rstrip()
    kept[-1] = last.rstrip(",;:.- ") + ELLIPSIS
    return kept


def _first_fitting(candidates, font, max_w, max_lines):
    """First candidate string that wraps within max_lines; else None."""
    for text in candidates:
        lines = wrap(text, font, max_w)
        if lines and len(lines) <= max_lines:
            return lines
    return None


def _block(lines, font, leading, color, tracking=0.0):
    if not lines:
        return None
    lh = max(1, int(round(font.size * leading)))
    top = font.getbbox(lines[0])[1]
    bottom = font.getbbox(lines[-1])[3]
    return Block(
        lines=lines,
        font=font,
        lh=lh,
        color=color,
        top_ink=top,
        height=(len(lines) - 1) * lh + (bottom - top),
        tracking=tracking,
    )


# --- layout -----------------------------------------------------------------

def _gap_for(name, t):
    return t.get(f"gap_{name}", 0)


def _stack_height(blocks, gaps, squeeze=1.0):
    total = sum(b.height for b in blocks)
    total += sum(g * squeeze for g in gaps[1:])
    return total


def _layout(card, t, width, height):
    """Build the blocks to draw, shedding detail until the stack fits."""
    cap = t["max_channel"]
    max_w = width - 2 * t["margin_x"]
    avail = height - 2 * t["margin_y"]
    family = t["family"]

    def font(role, size):
        return theme_mod.load(family, t[role], size)

    # Headline: biggest size that wraps into the allowed number of lines
    # without having to hyphen-break a word. Breaking a name across a hyphen
    # on a placard looks like a mistake; one size smaller does not.
    head_style = "sci_font" if card.title_italic else "head_font"
    sizes = t["head_sizes"] or [16]
    head_lines = head_font = None
    for allow_break in (False, True):
        for size in sizes:
            f = font(head_style, size)
            if not allow_break and any(f.getlength(w) > max_w for w in card.title.split()):
                continue
            lines = wrap(card.title, f, max_w)
            if head_font is None or len(lines) <= t["head_max_lines"]:
                head_font, head_lines = f, lines
            if len(lines) <= t["head_max_lines"]:
                break
        if head_lines is not None and len(head_lines) <= t["head_max_lines"]:
            break
    if head_font is None:
        head_font = font(head_style, sizes[-1])
        head_lines = wrap(card.title, head_font, max_w)
    head_lines = _truncate(head_lines, head_font, max_w, t["head_max_lines"])

    sci_font = font("sci_font", t["sci_size"])
    place_font = font("place_font", t["place_size"])
    remark_font = font("remark_font", t["remark_size"])
    bus_font = font("bus_font", t["bus_size"])

    # Named blocks, top to bottom, each with the gap that precedes it. A gap
    # belonging to a block that isn't drawn rolls forward onto the next one,
    # so a card with no scientific name doesn't crowd its rule.
    named = []
    pending = [0]

    def add(name, block, gap):
        if block is None:
            pending[0] += gap
            return
        named.append((name, block, (pending[0] + gap) if named else 0))
        pending[0] = 0

    if t["show_bus"] and card.bus:
        add("bus", _block([card.bus.upper()], bus_font, 1.0,
                          theme_mod.ink(t["ink_bus"], cap), t["bus_tracking"]), 0)

    add("head", _block(head_lines, head_font, t["head_leading"],
                       theme_mod.ink(t["ink_head"], cap)), _gap_for("bus_head", t))

    sci_block = None
    if card.subtitle:
        lines = _truncate(wrap(card.subtitle, sci_font, max_w),
                          sci_font, max_w, t["sci_max_lines"])
        sci_block = _block(lines, sci_font, t["sci_leading"],
                           theme_mod.ink(t["ink_sci"], cap))
    add("sci", sci_block, _gap_for("head_sci", t))

    place_lines = _first_fitting(card.place_variants, place_font, max_w,
                                 t["place_max_lines"])
    if place_lines is None and card.place_variants:
        place_lines = _truncate(wrap(card.place_variants[-1], place_font, max_w),
                                place_font, max_w, t["place_max_lines"])

    # Worked out before the rule, so a note that yields no habitat text (all
    # gear and weather) doesn't leave the rule sitting there on its own.
    from .cards import habitat_remark
    candidates = habitat_remark(card.remark)
    remark_lines = _first_fitting(candidates, remark_font, max_w,
                                  t["remark_max_lines"])
    if remark_lines is None and candidates and t.get("remark_truncate", True):
        remark_lines = _truncate(wrap(candidates[0], remark_font, max_w),
                                 remark_font, max_w, t["remark_max_lines"])

    rule = None
    if t["show_rule"] and (place_lines or remark_lines):
        rule = Block(lines=[], font=None, lh=1,
                     color=theme_mod.ink(t["ink_rule"], cap),
                     top_ink=0, height=1, rule=True)
    add("rule", rule, _gap_for("sci_rule", t))

    add("place",
        _block(place_lines, place_font, t["place_leading"],
               theme_mod.ink(t["ink_place"], cap)) if place_lines else None,
        _gap_for("rule_place", t))
    add("remark",
        _block(remark_lines, remark_font, t["remark_leading"],
               theme_mod.ink(t["ink_remark"], cap)) if remark_lines else None,
        _gap_for("place_remark", t))

    # Shed detail, least important first, until the stack fits. Gaps tighten
    # to 65% before any content is dropped.
    def fits(items, squeeze):
        return _stack_height([b for _, b, _ in items],
                             [g for _, _, g in items], squeeze) <= avail

    squeeze = 1.0
    while True:
        if fits(named, 1.0):
            squeeze = 1.0
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

    return named, squeeze, max_w, avail


def _shed(named, max_w):
    """Drop one increment of the least important surviving content."""
    index = {name: i for i, (name, _, _) in enumerate(named)}

    for name in ("remark", "place"):
        if name in index:
            block = named[index[name]][1]
            if len(block.lines) > 1:
                # Re-truncate rather than just dropping the line, so the text
                # ends on an ellipsis instead of mid-thought.
                trimmed = _truncate(block.lines, block.font, max_w,
                                    len(block.lines) - 1)
                named[index[name]] = (name, _block(
                    trimmed, block.font,
                    block.lh / block.font.size, block.color), named[index[name]][2])
                return True
    for name in ("remark", "rule", "sci", "place", "bus"):
        if name in index:
            i = index[name]
            gap = named.pop(i)[2]
            if i < len(named):  # the dropped block's gap rolls forward
                nm, blk, own = named[i]
                named[i] = (nm, blk, own + gap)
            if named:  # the new first block carries no leading gap
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


def render_card(card, t, size=(128, 128), offset=(0.0, 0.0), brightness=1.0):
    """Draw one placard. `offset` is the burn-in shift, in (fractional) px."""
    from PIL import ImageDraw

    width, height = size
    image = Image.new("RGB", size, (0, 0, 0))
    if brightness <= 0.0:
        return image

    named, squeeze, max_w, avail = _layout(card, t, width, height)
    if not named:
        return image

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
        if block.rule:
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
    """Scale every channel. Used for night fade and the global brightness
    trim -- the panel's own contrast register is left alone."""
    factor = max(0.0, min(1.0, factor))
    lut = [int(round(i * factor)) for i in range(256)]
    return image.point(lut * 3)


def blend(a, b, alpha):
    if alpha <= 0.0:
        return a
    if alpha >= 1.0:
        return b
    return Image.blend(a, b, alpha)
