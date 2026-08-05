"""One sounding recording, reduced to what a 128px placard can hold.

The headline is whichever field is actually the most specific thing known
about the record. For a bird that's the common name. For a soundscape it is
not the species -- "Sonus naturalis" is the mixer's way of saying "no taxon",
and "Soundscape" means "not a species" -- so the place carries the card.
"""

import re
from dataclasses import dataclass, field

# Species values that mean "this is not a taxon".
SENTINEL_SPECIES = ("sonus naturalis",)
# Names that describe a recording rather than name a thing.
GENERIC_NAMES = ("soundscape", "ambience", "atmosphere", "unknown")
# Vocalisation types that say nothing; better no footnote than "uncertain".
VAGUE_KINDS = ("uncertain", "unknown", "other", "?", "n/a", "na")

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
_PARENS = re.compile(r"\s*\(([^)]*)\)")
_WS = re.compile(r"\s+")
_DIGIT = re.compile(r"\d")
_FIELD = re.compile(r"(?:^|;)\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ \-]{1,30}?)\s*:\s*([^;]*)")
_HABITAT_KEYS = ("habitat", "hábitat", "biotope", "biótopo", "vegetation",
                 "vegetação", "vegetación", "ambiente")


@dataclass
class Record:
    key: str
    bus: str
    file: str = ""
    label: str = ""              # the small-caps line above the headline
    headline: list = field(default_factory=list)   # variants, most specific first
    subhead: str = ""            # scientific name, when the headline isn't one
    place: list = field(default_factory=list)
    remark: list = field(default_factory=list)
    when: str = ""               # "6:00 AM · 2007"
    kind: str = ""               # song / call
    recordist: str = ""
    country: str = ""
    lat: float = None
    lon: float = None
    is_soundscape: bool = False


def _clean(text):
    return _WS.sub(" ", (text or "").replace("\r", " ")).strip()


def _sentences(text):
    return [s for s in (_clean(p) for p in _SENTENCE_SPLIT.split(text or "")) if s]


def _tidy(text):
    text = _WS.sub(" ", _PARENS.sub("", text or "")).strip(" ,;:-–")
    if not text:
        return ""
    if text[0].islower():
        text = text[0].upper() + text[1:]
    return text if text[-1] in ".!?" else text + "."


# -- remark ------------------------------------------------------------------

def _structured_fields(text):
    pairs = _FIELD.findall(text)
    if len(pairs) < 2 and not re.match(r"^\s*(habitat|hábitat)\s*:", text, re.I):
        return {}
    return {k.strip().lower(): v.strip() for k, v in pairs if v.strip()}


def _comma_prefixes(sentence):
    """Shorter comma-clause prefixes, longest first, stopping at the first
    clause carrying a number -- that's where habitat turns into readings."""
    keep = []
    for clause in (c.strip() for c in sentence.split(",")):
        if _DIGIT.search(clause):
            break
        keep.append(clause)
    return [", ".join(keep[:n]) for n in range(len(keep), 0, -1)]


def placard_remark(entry):
    """Habitat candidates, best first, preferring the mixer's edited fragment.

    translate.py writes `remark_placard`: one English sentence with the gear
    and the thermometer already taken out, and null wherever nothing evocative
    survived that edit. When it's there it beats anything we can mine locally,
    because it was edited with the whole note in view. When it isn't, fall back
    to mining -- from the translation if there is one, since English is better
    raw material for the habitat-keyword search than the original Portuguese.
    """
    fragment = _clean(entry.get("remark_placard"))
    if fragment:
        return [_tidy(fragment)]
    return habitat_remark(entry.get("remark_en") or entry.get("remark"))


def habitat_remark(remark):
    """Habitat-ish candidates, best first."""
    remark = _clean(remark)
    if not remark:
        return []

    fields = _structured_fields(remark)
    if fields:
        for key in _HABITAT_KEYS:
            if fields.get(key):
                value = _tidy(fields[key])
                trimmed = [_tidy(p) for p in _comma_prefixes(fields[key])]
                return list(dict.fromkeys([v for v in trimmed if v] + [value]))
        return []

    sentences = _sentences(remark)
    if not sentences:
        return []
    habitat = sorted((s for s in sentences
                      if any(w in s.lower() for w in HABITAT_WORDS)), key=len)
    ordered = habitat + [s for s in sentences if s not in habitat][:1]

    out = []
    for sentence in ordered:
        # Trimmed prefixes come first. Given room, the untrimmed sentence
        # would otherwise win and drag the thermometer back onto the placard.
        for candidate in _comma_prefixes(sentence) + [sentence]:
            value = _tidy(candidate)
            if value and value not in out:
                out.append(value)
    return out


# -- place -------------------------------------------------------------------

def place_variants(entry):
    """Place strings, most detailed first."""
    place = _clean(entry.get("place"))
    locality = _clean(entry.get("locality"))
    country = _clean(entry.get("country"))
    out = []

    def add(value):
        value = _clean(value).strip(" ,.")
        if value and value not in out:
            out.append(value)

    add(place)
    add(_PARENS.sub("", place))
    if locality:
        parts = [p.strip() for p in re.split(r"[,;]", _PARENS.sub("", locality))
                 if p.strip()]
        for take in (2, 1):
            if len(parts) >= take:
                tail = ", ".join(parts[-take:])
                add(f"{tail}, {country}" if country else tail)
    add(country)
    return out


def locality_variants(entry):
    """Headline candidates for a record whose subject is its place.

    Most specific first: the locality as given, then its acronym if it has
    one, then the leading segment, then the country. The renderer takes the
    first that fits at a size worth calling a headline.
    """
    locality = _clean(entry.get("locality")) or _clean(entry.get("place"))
    country = _clean(entry.get("country"))
    out = []

    def add(value):
        value = _clean(value).strip(" ,.")
        if value and value not in out:
            out.append(value)

    bare = _PARENS.sub("", locality).strip()
    segments = [s.strip() for s in re.split(r"[,;]", bare) if s.strip()]

    add(segments[0] if segments else bare)
    # Spanish and Portuguese place names bury the actual feature behind an
    # institutional prefix: "Centro de Investigación y Conservación de Río Los
    # Amigos" is really Río Los Amigos. Take the tail after the last connector.
    tail = re.split(r"\s+(?:de|del|da|do|das|dos)\s+", segments[0] if segments else bare)
    if len(tail) > 1 and len(tail[-1]) >= 4:
        add(tail[-1])
    # "... (CICRA)" -- the acronym, if it comes to that.
    for inner in _PARENS.findall(locality):
        if 2 <= len(inner) <= 12:
            add(inner)
    add(bare)
    add(country)
    return out


# -- when --------------------------------------------------------------------

def when_text(entry):
    """"6:00 AM · 2007" -- a moment and a year, both short."""
    date = _clean(entry.get("date"))
    time = _clean(entry.get("time"))
    bits = []

    match = re.match(r"^(\d{1,2}):(\d{2})", time or "")
    if match:
        hour, minute = int(match.group(1)), match.group(2)
        if 0 <= hour <= 23:
            suffix = "AM" if hour < 12 else "PM"
            display = hour % 12 or 12
            bits.append(f"{display}:{minute} {suffix}")

    year = re.match(r"^(\d{4})", date or "")
    if year:
        bits.append(year.group(1))
    return " · ".join(bits)


def _looks_like_binomial(name):
    parts = (name or "").split()
    return len(parts) == 2 and parts[0][:1].isupper() and parts[1][:1].islower()


def _kind_of(entry):
    kind = _clean(entry.get("type_en") or entry.get("type")).split(",")[0].strip()
    return "" if kind.lower() in VAGUE_KINDS else kind


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# -- build -------------------------------------------------------------------

def build(contract, state=None, known_only=True, place_label="country"):
    """Contract (+ optional ambient/state) -> Records for sounding buses."""
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

    out = []
    for entry in buses:
        if not isinstance(entry, dict):
            continue
        bus = _clean(entry.get("bus")) or "—"
        if bus in sounding:
            if not sounding[bus]:
                continue
        elif float(entry.get("level") or 0) <= 0:
            continue

        known = bool(entry.get("known"))
        name = _clean(entry.get("name"))
        species = _clean(entry.get("species"))
        country = _clean(entry.get("country"))
        file = _clean(entry.get("file"))

        if not known:
            if known_only:
                continue
            out.append(Record(key=f"{bus}:{file or name}", bus=bus, file=file,
                              label="", headline=[bus.title()]))
            continue
        if not name and not species:
            continue

        soundscape = (species.lower() in SENTINEL_SPECIES
                      or name.lower() in GENERIC_NAMES)

        if soundscape:
            # The place is the subject. The label carries the country, so the
            # headline is free to be the specific locality.
            headline = locality_variants(entry)
            label = country if place_label == "country" else "locality"
            subhead = ""
        else:
            headline = [name or species]
            label = bus
            subhead = species if species and species.lower() != (name or species).lower() else ""

        out.append(Record(
            key=f"{bus}:{entry.get('recording_id') or file or name}",
            bus=bus,
            file=file,
            label=(label or bus).upper(),
            headline=[h for h in headline if h] or [name or species],
            subhead=subhead,
            place=place_variants(entry),
            remark=placard_remark(entry),
            when=when_text(entry),
            kind=_kind_of(entry),
            recordist=_clean(entry.get("recordist")),
            country=country,
            lat=_float(entry.get("lat")),
            lon=_float(entry.get("lon")),
            is_soundscape=soundscape,
        ))
    return out


def idle_record():
    return Record(key="__idle__", bus="", label="", headline=["listening"])
