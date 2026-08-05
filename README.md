# ambient-display

The placard beside the aquariums. It subscribes to the ambient-mixer's MQTT
feed on robix and tells you what is currently sounding: what it is, where
that is on a map, and what the habitat was.

Dim warm type on black, in a walnut frame. Nothing on it ever snaps.

```
   B R A Z I L              B R A Z I L              H A B I T A T
                                 ___
   Double-toothed             ,-'   '-.              Amazônia -
   Kite                      (    o    )             Campinarana.
   Harpagus bidentatus        \   .   /              canto
   ────                        \  |  /
   Porto Velho-RO,              '-,-'
   Rondônia, Brazil          7:15 AM · 2015

        name          →          map          →        habitat
```

## Status

The panel (Waveshare SSD1351) hasn't arrived. Everything runs today against
`luma.emulator` or headless with just the web preview; swapping to the real
hardware is one config key. See [Hardware](#hardware).

## Install

```sh
sudo apt install fonts-inter          # or fonts-ibm-plex
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.json config.json    # then edit the broker address
```

The font is a real dependency, not a nicety: without it the theme falls back
to DejaVu Serif, which is not what this is designed in. `config.json` is
gitignored — it holds the broker address and any credentials. Everything in
it is optional; the defaults in `ambient_display/config.py` are what you get
if the file is absent.

## Run

```sh
.venv/bin/python -m ambient_display                    # headless + web preview
.venv/bin/python -m ambient_display --device emulator  # luma.emulator window
.venv/bin/python -m ambient_display --force-day        # ignore the night blank
```

One-shots that don't start the loop:

```sh
# Every slide of every sounding record, side by side at 3×
.venv/bin/python -m ambient_display --sheet /tmp/slides.png

# Work offline from a saved payload
.venv/bin/python -m ambient_display --replay CONTRACT.json --sheet /tmp/slides.png

# One frame, as the panel would show it right now
.venv/bin/python -m ambient_display --once /tmp/frame.png
```

`--replay` picks up a `STATE.json` sitting next to the contract automatically.

## Slides

The placard settles on **one recording** and turns pages inside it, rather
than cutting between buses. Each page holds for 60–90 seconds with an
eight-second crossfade:

| slide | holds |
| --- | --- |
| **name** | the label, the headline, the scientific name, the rule, the place |
| **map** | South America in outline, a dot at the record's coordinates, and the moment: `7:15 AM · 2015` |
| **habitat** | the recordist's habitat note, given the whole card, with the vocalisation type or their name beneath |

A recording with no coordinates loses its map slide; one with no usable
habitat note loses its habitat slide. Two slides, or one, still work.

**Which recording gets featured** is whichever bus most recently changed
file — that's the news. A minimum dwell (5 minutes by default) stops it
flitting when several buses turn over close together, and featuring is
re-decided every frame rather than only when the feed changes, so a bus that
became the newest during another's dwell is picked up when that dwell ends.

### The headline is the most specific field, not the species

For a bird that's the common name. For the mixer's soundscape recordings it
isn't the species at all: `Sonus naturalis` is the mixer's way of saying "no
taxon", and a name of `Soundscape` means "not a species". Spending the
largest type on either wastes the card. Those records are carried by their
place instead — the headline becomes the locality and the label above it
carries the country:

```
   P E R U                          B I R D S
   Río Los Amigos                   Glossy Antshrike
   ────                             Sakesphorus luctuosus
```

Long localities shorten through a ladder rather than being truncated:
`Centro de Investigación y Conservación de Río Los Amigos` → `Río Los
Amigos` → `CICRA` → `Peru`. The renderer takes the most specific one that
still sets at 16px or larger, because below that it isn't a headline any
more. (Spanish and Portuguese bury the real name behind an institutional
prefix, so the ladder splits on `de`/`da`/`do` and keeps the tail.)

Set `content.place_label` to `"locality"` if you'd rather the label named the
field than the country.

### Making a remark fit 128 pixels

Recordists' notes arrive in three shapes, all handled:

| in the feed | on the placard |
| --- | --- |
| `Habitat: bamboo` | `Bamboo.` |
| `remarks:Empoleirado; perch-height:25m; habitat:Amazônia - Campinarana; recorder:Sony PCM-M10;` | `Amazônia - Campinarana.` |
| `Cerrado, mata seca, céu limpo, sem vento, temperatura 14 graus C, umidade relativa do ar 69%…` | `Cerrado, mata seca, céu limpo, sem vento.` |

A structured note is mined for its `habitat:` field; if it only carries gear
and weather, the remark is dropped rather than printed as junk. Free prose is
searched for the shortest sentence mentioning habitat (English, Portuguese or
Spanish), and a long comma-run is cut at the first clause containing a number
— measurements are where the habitat description ends. The trimmed form is
offered *before* the full sentence, so having room doesn't drag the
thermometer back onto the placard.

Place names get the same treatment from the other direction: full place,
then parentheticals dropped, then region + country, then country; first that
fits wins. Nothing is clipped at the frame edge.

## The map

Natural Earth 1:110m coastlines, vendored as GeoJSON in `data/`, clipped to
South America and simplified to 288 points — at this size a vertex finer
than about a fifth of a pixel is wasted. Equirectangular, aspect preserved,
centred. No tiles, no network, no projection library: the continent is 69
degrees tall and the map is eighty pixels, so anything fancier would buy
nothing.

The coastline is a thin dim line; the record sits under one brighter dot
inside a ring one step down. A record outside the clip bounds simply doesn't
get a map slide.

To cover more of the world, re-clip from the upstream
[natural-earth-vector](https://github.com/nvkelso/natural-earth-vector)
`ne_110m_coastline.geojson` and widen the `clip` bounds in the file — the
renderer reads them from the data.

## Typography

**Inter**, semibold down to regular. A serif was the first design and it was
wrong: at 128px the stems and bracketed serifs land on half a pixel and break
up. A sans with a tall x-height and open apertures survives the pixel grid.
There are no italics anywhere — at 9–11px a sloped sans is mush, so **weight
carries the hierarchy** instead. The letterspaced small-caps label and the
hairline rule stayed; that's what still reads as a placard.

On a name slide the rule sits directly under the headline as a title rule,
so it earns its place even when nothing follows it.

The headline takes the largest size that wraps into three lines *without*
hyphenating a word — breaking a name across a hyphen looks like a mistake,
one size down does not. Wrapping minimises squared slack rather than filling
greedily, so a two-line name breaks evenly instead of leaving a stub. When a
card is too full the layout tightens gaps to 65% before it starts shedding:
the footnote first, then the rule, the scientific name, the place. Anything
trimmed ends on an ellipsis, and a gap belonging to a block that isn't drawn
rolls onto the next one.

Blocks are measured ink-top to ink-bottom, so the vertical rhythm holds
across families. Try another with `?family=` — IBM Plex Sans, Noto Serif,
Roboto Slab and others are found automatically, or drop a font in `fonts/`
and name it.

## Burn-in

An OLED that shows the same placard in the same place for five years will
keep showing it after you turn it off. Four things, all on from the start:

- **Drift.** The whole layout walks a small lattice (±3px), moving every ~5
  minutes and easing over 20 seconds. It is re-rendered at the fractional
  offset rather than the frame being resampled, so the type stays crisp the
  whole way across and the antialiasing lands differently each time.
- **Dim RGB, not dim panel.** The brightest ink is `#ccc0a4` — peak channel
  204 of 255 — and every colour is capped at `max_channel`. The SSD1351
  contrast register is deliberately left alone: driving dark values into a
  bright panel keeps the antialiasing ramp intact, where turning the panel
  down would crush it. The cap leaves deliberate headroom, because this was
  judged on a monitor and the OLED will read brighter in a dark room.
- **Overnight blank.** Full through the day, easing down from `evening`,
  reaching `night_level` at `sleep`, then fading to true black over three
  minutes and staying there until `wake`. Not a dimmed placard overnight —
  black.
- **Slide rotation.** The page turns every 60–90s and the whole layout
  changes shape between the three kinds, so no glyph sits on a pixel for long.

The frame is only pushed to the panel when the pixels actually changed, so a
static placard costs nothing on the SPI bus.

## The web preview

<http://localhost:8324/> — the live frame at 1× and 4×, refreshing every
second, next to a still you can push typography around on.

| route | what it is |
| --- | --- |
| `/frame.png` | the live frame, exactly what the panel is showing (`?scale=N`) |
| `/frame@4x.png` | same, at 4× nearest-neighbour |
| `/still.png` | one slide, no drift, no night fade (`?card=N&scale=N`) |
| `/slides.json`, `/theme.json`, `/families.json`, `/status.json` | what's on air, and why |

Any theme key can be overridden per request:

```
/still.png?scale=4&family=IBM+Plex+Sans&head_sizes=26,22,18&ink_head=%23e0d4b4
```

The controls on the preview page do this for you and print the matching
`"theme"` block for `config.json` as you go. Separately, while `preview.dev`
is true the theme is re-read from `config.json` on every request — edit the
file, hit refresh, no restart.

Nearest-neighbour scaling throughout: at 4× you are looking at real pixels
and real antialiasing, not a smoothed guess.

## The feed

`ambient/nowplaying` is retained, so a placard appears the moment the client
connects. `ambient/state` is read too — it carries per-bus `sounding`, which
decides whether a bus is a candidate at all. If state is unavailable the
contract's own `level` is used instead; neither topic is required for the
client to run.

Only `known` entries get placards by default (`content.known_only`) — those
are the xeno-canto recordings with a species, a place and a recordist's note.
The library sound effects carry filenames like `WATRFlow-LR Thailand-Water,
Flow, River, Birds Calm, Daytime`, which is not placard material; with
`known_only: false` they appear under their bus name instead.

## Hardware

Waveshare 1.5" RGB OLED (SSD1351, 128×128) on Bloopy, over SPI:

| panel | Pi |
| --- | --- |
| VCC | 3.3V |
| GND | GND |
| DIN | GPIO10 / MOSI |
| CLK | GPIO11 / SCLK |
| CS | GPIO8 / CE0 |
| DC | GPIO25 |
| RST | GPIO27 |

Enable SPI (`sudo raspi-config` → Interface Options → SPI), then set
`"display": { "device": "ssd1351" }`.

Two things to check on first light, both config keys:

- **Colour.** If the warm ink looks cold and blue, flip
  `display.ssd1351.bgr`. Waveshare panels are usually BGR, the default here.
- **Pins.** `display.spi.gpio_dc` / `gpio_rst` default to 25/27, which is
  what Waveshare's own examples use — confirm against your wiring.

`display.rotate` is 0–3 (90° steps) for whichever way the frame hangs.

## Deploy on Bloopy

```sh
sudo mkdir -p /var/www/ambient-display
sudo chown rcampbell: /var/www/ambient-display
rsync -a --exclude .venv --exclude .git ./ rcampbell@bloopy:/var/www/ambient-display/

ssh bloopy
cd /var/www/ambient-display
sudo apt install fonts-inter
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
sudo usermod -aG spi,gpio rcampbell

sudo cp deploy/ambient-display.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ambient-display
journalctl -u ambient-display -f
```

`deploy/nginx-ambient-display.conf` puts the preview on port 80, restricted
to the LAN. It's a bench for tuning type from a laptop, not something to
expose.

## Layout

```
ambient_display/
  app.py        main loop, CLI, and the Display that owns the frame
  records.py    contract -> one recording's content (headline, place, remark)
  slides.py     a record -> its pages
  render.py     wrapping, block layout, drawing        <- typography lives here
  theme.py      fonts, weights, sizes, colours         <- and the knobs here
  mapdraw.py    coastline projection and the dot
  motion.py     drift, featuring, slide rotation, day-night curve
  feed.py       MQTT subscriber
  device.py     noop | emulator | ssd1351
  preview.py    the web bench
data/
  ne_110m_coastline_sa.json   Natural Earth, clipped (public domain)
```

`render.render_slide(slide, theme, size, offset, brightness)` is pure, which
is why the preview and the panel can't disagree about what's on screen.
