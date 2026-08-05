"""Turn an ambient/nowplaying contract into placard-shaped cards.

A card is what the panel can actually hold: a headline, an optional
scientific name, a place short enough to read, and a habitat remark.
"""

import re
from dataclasses import dataclass, field

# Sentinel "species" the mixer uses for non-taxon recordings. Not a real
# binomial, so we don't set it in italics under the headline.
DEFAULT_SUBTITLE_BLOCKLIST = ("Sonus naturalis",)

# Words that mark a sentence as being about habitat rather than about the
# call, the weather, or the gear. Xeno-canto remarks come in en / es / pt.
HABITAT_WORDS = (
    "habitat", "hábitat", "forest", "floresta", "bosque", "selva", "mata",
    "woodland", "vegetation", "vegetação", "vegetación", "canopy", "dossel",
    "understor", "sub-bosque", "riparian", "ripária", "gallery", "galeria",
    "marsh", "swamp", "pântano", "brejo", "bog", "fen", "pond", "lagoa",
    "laguna", "lake", "lago", "stream", "creek", "igarapé", "river", "río",
    "rio", "waterfall", "cachoeira", "grass", "campo", "cerrado", "caatinga",
    "várzea", "restinga", "scrub", "shrub", "arbust", "bamboo", "bambu",
    "pasture", "pastagem", "plantation", "garden", "jardim", "orchard",
    "clearing", "clareira", "edge", "borda", "trail", "trilha", "roadside",
    "secondary", "secundária", "secundaria", "primary", "primária",
    "mangrove", "manguezal", "dune", "duna", "hillside", "encosta",
    "altitude", "elevation", "reserve", "reserva", "park", "parque",
    "ambiente", "ambient",
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_PARENS = re.compile(r"\s*\([^)]*\)")
_WS = re.compile(r"\s+")
_DIGIT = re.compile(r"\d")
# "remarks:x; perch-height:25m; habitat:Amazônia - Campinarana; ..." -- the
# structured note format a lot of xeno-canto recordists use.
_FIELD = re.compile(r"(?:^|;)\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ \-]{1,30}?)\s*:\s*([^;]*)")
_HABITAT_KEYS = ("habitat", "hábitat", "biotope", "biótopo", "vegetation",
                 "vegetação", "vegetación", "ambiente")


@dataclass
class Card:
    key: str
    bus: str
    title: str
    title_italic: bool = False
    subtitle: str = ""
    place_variants: list = field(default_factory=list)
    remark: str = ""


def _clean(text):
    return _WS.sub(" ", (text or "").replace("\r", " ")).strip()


def _sentences(text):
    return [s for s in (_clean(p) for p in _SENTENCE_SPLIT.split(text or "")) if s]


def _tidy(text):
    """Sentence-case a fragment and give it a full stop."""
    text = _WS.sub(" ", _PARENS.sub("", text or "")).strip(" ,;:-–")
    if not text:
        return ""
    if text[0].islower():
        text = text[0].upper() + text[1:]
    return text if text[-1] in ".!?" else text + "."


def _structured_fields(text):
    """Parse a `key:value;` note block, or {} if this isn't one."""
    pairs = _FIELD.findall(text)
    if len(pairs) < 2 and not re.match(r"^\s*(habitat|hábitat)\s*:", text, re.I):
        return {}
    return {k.strip().lower(): v.strip() for k, v in pairs if v.strip()}


def _comma_prefixes(sentence):
    """Progressively shorter comma-clause prefixes, longest first.

    Recordists tend to open with the habitat and then drift into readings --
    "Cerrado, mata seca, ceu limpo, sem vento, temperatura 14 graus C, ...".
    A clause carrying a number is a measurement, so that's where we stop.
    """
    clauses = [c.strip() for c in sentence.split(",")]
    keep = []
    for clause in clauses:
        if _DIGIT.search(clause):
            break
        keep.append(clause)
    return [", ".join(keep[:n]) for n in range(len(keep), 0, -1)]


def habitat_remark(remark):
    """Pull the habitat-ish part out of a free-text recordist note.

    Returns candidates best-first; the renderer takes the first that fits.
    """
    remark = _clean(remark)
    if not remark:
        return []

    # A structured note is either useful (it names a habitat field) or it's
    # gear and weather readings -- in which case the placard is better blank.
    fields = _structured_fields(remark)
    if fields:
        for key in _HABITAT_KEYS:
            if fields.get(key):
                value = _tidy(fields[key])
                return [value] + [_tidy(p) for p in _comma_prefixes(fields[key])
                                  if _tidy(p) != value]
        return []

    sentences = _sentences(remark)
    if not sentences:
        return []

    habitat = [s for s in sentences if any(w in s.lower() for w in HABITAT_WORDS)]
    # Shortest habitat sentence first: on a 128px panel, brevity is the point.
    habitat.sort(key=len)
    ordered = habitat + [s for s in sentences if s not in habitat][:1]

    out = []
    for sentence in ordered:
        for candidate in [sentence] + _comma_prefixes(sentence):
            value = _tidy(candidate)
            if value and value not in out:
                out.append(value)
    return out


def place_variants(entry):
    """Place strings from most to least detailed. The renderer picks the
    first that fits the space, so a long field degrades instead of clipping."""
    place = _clean(entry.get("place"))
    locality = _clean(entry.get("locality"))
    country = _clean(entry.get("country"))

    variants = []

    def add(value):
        value = _clean(value).strip(" ,.")
        if value and value not in variants:
            variants.append(value)

    add(place)
    add(_PARENS.sub("", place))

    if locality:
        # Locality reads coarse-to-fine left to right on xeno-canto, so the
        # tail segments are the region — what a placard would name.
        parts = [p.strip() for p in re.split(r"[,;]", _PARENS.sub("", locality)) if p.strip()]
        for take in (2, 1):
            if len(parts) >= take:
                tail = ", ".join(parts[-take:])
                add(f"{tail}, {country}" if country else tail)
    add(country)
    return variants


def _looks_like_binomial(name):
    parts = (name or "").split()
    return len(parts) == 2 and parts[0][:1].isupper() and parts[1][:1].islower()


def build(contract, state=None, known_only=True, subtitle_blocklist=DEFAULT_SUBTITLE_BLOCKLIST):
    """Contract payload (and optional ambient/state) -> list of Cards.

    Only buses that are actually sounding get a placard.
    """
    if isinstance(contract, dict):
        buses = contract.get("buses") or []
    elif isinstance(contract, list):
        buses = contract
    else:
        buses = []

    sounding = {}
    if isinstance(state, dict):
        for name, info in (state.get("buses") or {}).items():
            if isinstance(info, dict):
                sounding[name] = bool(info.get("sounding", True)) and info.get("enabled", True)

    blocked = {s.lower() for s in (subtitle_blocklist or ())}
    cards = []
    for entry in buses:
        if not isinstance(entry, dict):
            continue
        bus = _clean(entry.get("bus")) or "—"

        # ambient/state is authoritative about what's audible; the contract's
        # level is the fallback when we aren't tracking state.
        if bus in sounding:
            if not sounding[bus]:
                continue
        elif float(entry.get("level") or 0) <= 0:
            continue

        known = bool(entry.get("known"))
        if known_only and not known:
            continue

        name = _clean(entry.get("name"))
        species = _clean(entry.get("species"))
        if not known:
            # Library sound effects carry filenames, not names --
            # "WATRFlow-LR Thailand-Water, Flow, River, Birds Calm, Daytime".
            # The bus is the only honest thing to put on a placard.
            cards.append(Card(key=f"{bus}:{entry.get('file') or name}",
                              bus="", title=bus.title()))
            continue

        if not name and not species:
            continue

        title = name or species
        subtitle = ""
        if species and species.lower() != title.lower() and species.lower() not in blocked:
            subtitle = species

        card = Card(
            key=f"{bus}:{entry.get('recording_id') or entry.get('file') or title}",
            bus=bus,
            title=title,
            # A bare binomial as the headline is set in italics, as it would be
            # in print. A common name is not.
            title_italic=_looks_like_binomial(title) and title == species,
            subtitle=subtitle,
            place_variants=place_variants(entry),
            remark=entry.get("remark") or "",
        )
        cards.append(card)
    return cards


def idle_card():
    """Shown when nothing is sounding or the mixer hasn't spoken yet."""
    return Card(key="__idle__", bus="", title="listening", title_italic=True)
