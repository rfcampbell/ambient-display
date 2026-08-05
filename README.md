# ambient-display

The placard beside the aquariums. It subscribes to the ambient-mixer's MQTT
feed on robix and renders what's currently sounding onto a 1.5" 128×128 RGB
OLED: common name, scientific name, place, habitat remark.

Dim warm type on black, in a walnut frame. Nothing on it ever snaps.

```
┌──────────────────┐
│  B I R D S       │
│  Double-toothed  │
│  Kite            │
│  Harpagus bidentatus
│  ────            │
│  Porto Velho-RO, │
│  Rondônia, Brazil│
│  Amazônia - Campinarana.
└──────────────────┘
```

## Status

The panel (Waveshare SSD1351) hasn't arrived. Everything runs today against
`luma.emulator` or headless with just the web preview; swapping to the real
hardware is one config key. See [Hardware](#hardware).

## Install

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.json config.json      # then edit the broker address
```

`config.json` is gitignored — it holds the broker address and any credentials.
Everything in it is optional; the defaults in `ambient_display/config.py` are
what you get if the file is absent.

## Run

```sh
.venv/bin/python -m ambient_display                    # headless + web preview
.venv/bin/python -m ambient_display --device emulator  # luma.emulator window
.venv/bin/python -m ambient_display --force-day        # ignore the night blank
```

Useful one-shots that don't start the loop:

```sh
# Render every card the mixer is currently playing, side by side at 4×
.venv/bin/python -m ambient_display --sheet /tmp/cards.png

# Work offline from a saved payload
.venv/bin/python -m ambient_display --replay CONTRACT.json --sheet /tmp/cards.png

# One frame, as the panel would show it right now
.venv/bin/python -m ambient_display --once /tmp/frame.png
```

`--replay` picks up a `STATE.json` sitting next to the contract automatically.

## The web preview

<http://localhost:8324/> — the live frame at 1× and 4×, refreshing every
second, next to a still you can push typography around on.

| route | what it is |
| --- | --- |
| `/frame.png` | the live frame, exactly what the panel is showing (`?scale=N`) |
| `/frame@4x.png` | same, at 4× nearest-neighbour |
| `/still.png` | one card, no drift, no night fade (`?card=N&scale=N`) |
| `/still@4x.png` | same, at 4× |
| `/cards.json`, `/theme.json`, `/families.json`, `/status.json` | what's on air, and why |

**Iterating on type.** Any theme key can be overridden per-request, so you can
try a setting without touching a file:

```
/still.png?scale=4&family=Roboto+Slab&head_sizes=26,22,18&ink_head=%23c0b090
```

The controls on the preview page do this for you and print the matching
`"theme"` block for `config.json` as you go. Separately, while
`preview.dev` is true the theme is re-read from `config.json` on every
request — edit the file, hit refresh, no restart.

Nearest-neighbour scaling throughout: at 4× you are looking at real pixels and
real antialiasing, not a smoothed guess.

## What gets a placard

`ambient/nowplaying` is retained, so a placard appears the moment the client
connects. `ambient/state` is read too — it carries per-bus `sounding`, which
is what actually decides whether a bus earns a card. If state is unavailable
the contract's own `level` is used instead; neither topic is required for the
client to run.

Only `known` entries get placards by default (`content.known_only`) — those
are the xeno-canto recordings with a species, a place, and a recordist's note.
The library sound effects on `stream` and `insects` carry filenames like
`WATRFlow-LR Thailand-Water, Flow, River, Birds Calm, Daytime`, which is not
placard material. Set `known_only: false` to include them anyway.

Cards rotate on a 45s hold with a 6s crossfade. When the mixer starts a *new*
recording, that card jumps the queue rather than waiting its turn — the
placard should be about what just changed.

### Making a remark fit 128 pixels

Recordists' notes arrive in three shapes, and all three are handled:

| in the feed | on the placard |
| --- | --- |
| `Habitat: bamboo` | `Bamboo.` |
| `remarks:Empoleirado; perch-height:25m; habitat:Amazônia - Campinarana; recorder:Sony PCM-M10;` | `Amazônia - Campinarana.` |
| `Cerrado, mata seca, céu limpo, sem vento, temperatura 14 graus C, umidade relativa do ar 69%…` | `Cerrado, mata seca, céu limpo, sem vento.` |

A structured note is mined for its `habitat:` field; if it only carries gear
and weather, the remark is dropped rather than printed as junk. Free prose is
searched for the shortest sentence that mentions habitat (in English,
Portuguese or Spanish), and a long comma-run is cut at the first clause
containing a number — measurements are where the habitat description ends.

Place names get the same treatment from the other direction: the full place is
tried first, then progressively shorter forms (parentheticals dropped, then
region + country, then country), and the first one that fits is used. Nothing
is clipped at the frame edge.

## Typography

Noto Serif, antialiased, autofitting. The headline takes the largest size that
wraps into three lines *without hyphenating a word* — breaking a name across a
hyphen looks like a mistake, one size down does not. Wrapping minimises
squared slack rather than filling greedily, so a two-line name breaks evenly
instead of leaving a stub.

Blocks are stacked with the gaps in the theme, and when a card is too full the
layout tightens gaps to 65% before it starts shedding: remark lines first,
then the remark, the rule, the scientific name, the place. Anything trimmed
ends on an ellipsis. A gap belonging to a block that isn't drawn rolls onto
the next one, so a card with no scientific name doesn't crowd its rule.

Fonts are measured, not guessed: a block's box runs from the ink top of its
first line to the ink bottom of its last, so the vertical rhythm holds across
families. Try another with `?family=` — Noto Serif Display, Roboto Slab,
DejaVu Serif and Liberation Serif are all found automatically, or drop a
`.ttf` in `fonts/` and name it.

## Burn-in

An OLED that shows the same placard in the same place for five years will
keep showing it after you turn it off. Four things, all on from the start:

- **Drift.** The whole layout walks a small lattice (±3px), moving every ~5
  minutes and easing over 20 seconds. It is re-rendered at the fractional
  offset rather than the frame being resampled, so the type stays crisp the
  whole way across and the antialiasing lands differently each time.
- **Dim RGB, not dim panel.** The brightest ink is `#a89e84` — peak channel
  168 of 255 — and every colour is capped at `max_channel` (190). The SSD1351
  contrast register is deliberately left alone: driving dark values into a
  bright panel keeps the antialiasing ramp intact, where turning the panel
  down would crush it.
- **Overnight blank.** Full through the day, easing down from `evening`,
  reaching `night_level` at `sleep`, then fading to true black over three
  minutes and staying there until `wake`. Not a dimmed placard overnight —
  black.
- **Content rotation.** Cards change every 45s, so no single glyph sits on a
  pixel for long.

The frame is only pushed to the panel when the pixels actually changed, so a
static placard costs nothing on the SPI bus.

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

Enable SPI (`sudo raspi-config` → Interface Options → SPI), then:

```json
"display": { "device": "ssd1351" }
```

Two things to check on first light, both config keys:

- **Colour.** If the warm ink looks cold and blue, flip
  `display.ssd1351.bgr`. Waveshare panels are usually BGR, which is the
  default here.
- **Pins.** `display.spi.gpio_dc` / `gpio_rst` default to 25/27, which is what
  Waveshare's own examples use — confirm against your wiring.

`display.rotate` is 0–3 (90° steps) for whichever way the frame ends up
hanging.

## Deploy on Bloopy

```sh
sudo mkdir -p /var/www/ambient-display
sudo chown rcampbell: /var/www/ambient-display
rsync -a --exclude .venv --exclude .git ./ rcampbell@bloopy:/var/www/ambient-display/

ssh bloopy
cd /var/www/ambient-display
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
sudo usermod -aG spi,gpio rcampbell

sudo cp deploy/ambient-display.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ambient-display
journalctl -u ambient-display -f
```

`deploy/nginx-ambient-display.conf` puts the preview on port 80, restricted to
the LAN. It's a bench for tuning type from a laptop, not something to expose.

## Layout

```
ambient_display/
  app.py        main loop, CLI, and the Display that owns the frame
  cards.py      contract -> placard content (place and remark fitting)
  render.py     wrapping, block layout, drawing        <- typography lives here
  theme.py      fonts, sizes, colours                  <- and the knobs here
  motion.py     drift, rotation/crossfade, day-night curve
  feed.py       MQTT subscriber
  device.py     noop | emulator | ssd1351
  preview.py    the web bench
```

`render.render_card(card, theme, size, offset, brightness)` is pure, which is
why the preview and the panel can't disagree about what's on screen.
