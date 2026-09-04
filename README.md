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

Running on pixelpup. The Waveshare SSD1351 is installed and lit: 128×128 over
SPI, DC on GPIO24 and RST on GPIO25 -- not the 25/27 the driver defaults to.
See [Hardware](#hardware) for the rest of the wiring.

The `luma.emulator` and headless web-preview paths are still here, and still
the way to work on slides without a panel in front of you. They are not what
runs on pixelpup.

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
| DC | GPIO24 |
| RST | GPIO25 |

That DC/RST pair is what is actually wired on pixelpup. It is *not* the
default: `display.spi.gpio_dc` / `gpio_rst` default to 25/27 in `config.py`,
which is what Waveshare's own examples use. pixelpup's `config.json`
overrides them to 24/25. Confirm against your own wiring before believing
either number.

Enable SPI by uncommenting `dtparam=spi=on` in `/boot/firmware/config.txt`
(`raspi-config` → Interface Options → SPI does the same thing), reboot, then
set `"display": { "device": "ssd1351" }`. That one line is the *only* boot
config the panel needs -- no overlay, no `gpio=` directives: DC and RST are
plain GPIOs the luma driver drives itself.

Two things to check on first light, both config keys:

- **Colour.** If the warm ink looks cold and blue, flip
  `display.ssd1351.bgr`. Waveshare panels are usually BGR, the default here.
- **Pins.** `display.spi.gpio_dc` / `gpio_rst` default to 25/27, which is
  what Waveshare's own examples use — confirm against your wiring.

`display.rotate` is 0–3 (90° steps) for whichever way the frame hangs.

## Deploy

It runs on robix today, at <http://display.robix>, as a systemd **user**
service — the same shape as ambient-mixer, and the same process Bloopy will
run. On robix `display.device` stays `noop`: no panel, so the client
subscribes, composes frames and serves the bench. That is the whole deploy
except the last inch.

```sh
install -Dm644 deploy/ambient-display.service \
    ~/.config/systemd/user/ambient-display.service
systemctl --user daemon-reload
systemctl --user enable --now ambient-display
journalctl --user -u ambient-display -f

sudo install -m644 deploy/ambient-display.nginx \
    /etc/nginx/sites-available/display.robix
sudo ln -s /etc/nginx/sites-available/display.robix /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

A user service rather than a system one because that is how robix runs the
mixer, and `loginctl enable-linger rcampbell` is already set, so it starts at
boot with nobody logged in. It needs no privileges on robix, and on Bloopy it
needs only group membership, which a user service inherits.

### Rebuilding the card from scratch

The placard runs on **pixelpup**, a Pi Zero 2 W. Its setup once existed only
on its SD card, and when a power cut corrupted that card the whole
arrangement went with it. This section is the replacement for that: enough to
go from a freshly flashed card to a lit panel without remembering anything.

Starting point: Raspberry Pi OS Lite 64-bit (Debian 13, trixie) flashed with
hostname `pixelpup`, user `rcampbell`, wifi and ssh configured by the imager.
Nothing else installed.

**1. Packages and SPI.** The only steps that need root.

```sh
sudo apt update
sudo apt install -y git fonts-inter
sudo cp /boot/firmware/config.txt /boot/firmware/config.txt.stock
sudo sed -i 's/^#dtparam=spi=on$/dtparam=spi=on/' /boot/firmware/config.txt
```

Then check the *other* boot file while you are in there, because a fresh
imager run is exactly when this gets set wrong:

```sh
grep -o 'cfg80211.ieee80211_regdom=[A-Z]*' /boot/firmware/cmdline.txt
cat /sys/module/cfg80211/parameters/ieee80211_regdom   # what is actually in effect
```

It must be a real regulatory domain -- `US`, not `UM`. `UM` is the US Minor
Outlying Islands, which has no entry in the regulatory database, so the
kernel falls back to the world domain where every channel is
passive-scan-only. The symptom is vicious: the radio sees every AP at full
signal and can never transmit to associate, and it stays survivable for as
long as the box never has to associate from scratch. See "Coming back from a
power cut".

`dtparam=spi=on` is the single line that separates a stock config.txt from a
working one -- verified by diffing a stock image against the card's own
backup, which differed by that line and nothing else. `fonts-inter` is not
optional: `theme.py` resolves `/usr/share/fonts/opentype/inter/Inter-*.otf`
by absolute path, and a Lite image ships no fonts at all.

**2. The code.**

```sh
git clone https://github.com/rfcampbell/ambient-display.git ~/ambient-display
cd ~/ambient-display
```

**3. The venv.** The `--system-site-packages` flag is load-bearing, not
tidiness:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/pip install "pillow>=10" "paho-mqtt>=2.0" "flask>=3.0" "luma.oled>=3.13"
```

`luma.oled` imports `RPi.GPIO`. Raspberry Pi OS trixie no longer ships the
classic RPi.GPIO -- it ships `python3-rpi-lgpio`, an apt package that
re-implements the RPi.GPIO API on top of lgpio, and that is the supported
path on current kernels. It is an apt package, so a sealed venv cannot see
it, and `pip install RPi.GPIO` is the wrong fix: it installs the old library
that does not drive these kernels. Hence a venv that can see system packages.

`requirements.txt` is deliberately *not* used here. It lists `luma.emulator`,
which drags in pygame for the development panel; the comment there already
says it is not needed once the real display is wired up, and on a 512 MB Zero
2 W it is worth the omission. The four packages above are what the panel
path actually imports.

**4. `config.json`.** Gitignored, so it is exactly the piece that lived only
on the lost card. Everything not named here comes from the defaults in
`config.py`.

```json
{
  "mqtt": {
    "host": "192.168.221.163",
    "port": 1883,
    "topic": "ambient/jungler/nowplaying",
    "state_topic": "ambient/jungler/state",
    "availability_topic": "ambient/jungler/availability",
    "use_state": true
  },

  "display": {
    "device": "ssd1351",
    "width": 128,
    "height": 128,
    "rotate": 0,
    "spi": {
      "port": 0,
      "device": 0,
      "bus_speed_hz": 8000000,
      "gpio_dc": 24,
      "gpio_rst": 25
    }
  }
}
```

**5. Groups.** A stock Raspberry Pi OS image already puts the first user in
`spi` and `gpio`, so the `usermod` this section used to prescribe is usually
a no-op. Check rather than assume: `id | tr ' ' '\n' | grep -E 'spi|gpio'`.

**6. The service.**

```sh
install -Dm644 deploy/ambient-display.service \
    ~/.config/systemd/user/ambient-display.service
loginctl enable-linger rcampbell
systemctl --user daemon-reload
systemctl --user enable --now ambient-display
```

`enable-linger` is what makes a *user* service start at boot with nobody
logged in; without it the placard only runs while someone is ssh'd in. It
does not need sudo -- polkit lets a user linger themselves.

**7. Reboot**, both to pick up `dtparam=spi=on` and because a placard that
has not survived a reboot is not yet deployed.

```sh
sudo reboot
# then, once it is back:
ls -l /dev/spidev0.0                       # the SPI device now exists
systemctl --user status ambient-display    # active, and not restart-looping
journalctl --user -u ambient-display -b    # this boot only
```

The nginx vhost is robix-only. It proxies the typography bench, which is a
tuning tool, not part of the placard; pixelpup serves the same bench directly
on `:8324` if you want it.

### Coming back from a power cut

The failure that cost the card was a power cut, so this was looked at
deliberately rather than assumed. What is actually true today:

- **Wifi reassociates on its own.** NetworkManager owns `wlan0` via a
  netplan-generated connection with `autoconnect=yes` and powersave at the
  default `0`. Nothing needs adding.
- **The client tolerates starting before the network is up**, which matters
  because it will. `feed.py` uses `connect_async` + `loop_start` with
  `reconnect_delay_set(1, 60)`, so a broker that is not there yet is a retry
  with backoff, not a crash.
- **`After=network-online.target` in the unit is a no-op** and should not be
  trusted. That target does not exist in the *user* systemd manager
  (`systemctl --user show network-online.target` reports
  `LoadState=not-found`). It is harmless only because of the previous point.
  If the client ever grows a hard requirement on the network at startup, this
  is the line that will not save it.
- **`nowplaying` is retained on the broker**, so a cold boot draws real
  content immediately instead of waiting for the mixer's next publish.
- **`Restart=always` with `RestartSec=5`** covers the remaining cases.

No watchdog is configured, and none was added. `/dev/watchdog` exists and
`systemd`'s `RuntimeWatchdogSec` is off. A watchdog reboots a *hung* board,
which is not what happened here -- the card's filesystem was corrupted by
losing power mid-write, and a watchdog neither prevents nor detects that. If
this card dies the same way again, the things that would actually help are a
better-quality card, or moving the root filesystem to read-only or USB. Say
the word and that can be a separate piece of work.

### The wifi watchdog

`deploy/wifi-watchdog` pings the default gateway once a minute from a systemd
timer and bounces the connection after three consecutive failures. It belongs
on both Pis -- pixelpup and jungler -- and this repo holds the canonical copy
even though jungler runs the mixer rather than the placard.

**Installing it is a separate act from writing it.** The commit that added
this script (`da653f3`) said it ran on both Pis. It ran on neither: the files
were committed and the install block below was never executed, so for the
whole of 2026-09-03 there was no timer, no unit and no journal line on either
host. It was found by checking the Pis rather than the repo:
`systemctl is-enabled wifi-watchdog.timer` returned `not-found` on both.
Nothing in this file could have told you, because a README records what
someone meant to do. Before believing this section, read the target:

```sh
systemctl is-enabled wifi-watchdog.timer   # enabled, not not-found
systemctl show wifi-watchdog.timer -p LastTriggerUSec   # non-empty
journalctl -u wifi-watchdog | tail         # it has actually run
```

**And the recovery path was broken.** As first written the bounce called
`nmcli device reconnect`, which is not a command: nmcli takes `connect` and
`disconnect`, and rejects `reconnect` with exit 2 *without touching the
device*. So the watchdog counted to three, logged `bouncing wlan0`, called
nothing, logged `failed`, reset its counter and repeated -- detection with no
recovery, which against the outage that prompted it would have changed
nothing. It now does `nmcli -w 30 device disconnect` then
`nmcli -w 30 device connect`; the unit allows 120s because nmcli's default
90s wait races the oneshot's start timeout.

Both were found by driving it against deliberate failures on jungler
(2026-09-03) rather than by reading it:

| case | how | result |
| --- | --- | --- |
| gateway unreachable, link up | `ip route add blackhole $gw` | counted 1/3, 2/3, 3/3 and bounced on schedule; `nmcli device reconnect wlan0: failed`, NetworkManager logged no state change. This is what exposed the bug. |
| device disconnected | `nmcli device disconnect wlan0` | down 20:50:34, `<no default route>` counted 1/3-3/3, `nmcli device connect wlan0: ok` at 20:53:05, reachable 20:53:16 -- 2m31s, the watchdog's own doing. An independent 10-minute fallback was armed and never fired. |

The second case is the one that matters: a disconnected device with no default
route at all is the shape the power cut left, and it is the case a blocked-ICMP
test alone would not have exercised.

`deploy/wifi-watchdog-selftest` now guards the specific mistake. It reads the
nmcli verbs out of the watchdog script -- so changing the recovery call
re-tests the new call -- and probes each one against a device name that cannot
exist. A real verb comes back `Device not found` (exit 10); a verb that does
not exist comes back `not understood` (exit 2), which is the failure, reported
as one. Nothing is disconnected to find out. It is deliberately not a test of
the whole watchdog: the counter was never the part that was broken.

```
$ wifi-watchdog-selftest
ok:   'nmcli device connect' exists (exit 10 against a nonexistent device)
ok:   'nmcli device disconnect' exists (exit 10 against a nonexistent device)
PASS: recovery path calls exist
```

Run against a copy reverted to `reconnect`, it exits 1 with
`FAIL: 'nmcli device reconnect' is not an nmcli subcommand`. That case was
driven before trusting it -- a check nobody has watched fail is the thing this
whole section is about.

Where it stands as of 2026-09-03: **jungler** has the fixed script installed,
enabled, fired, and both failure cases driven through it. **pixelpup** has not
been done. Do not take that from this paragraph either -- run the three checks
above on the host itself.

The install, which has to be run on each Pi:

```sh
sudo install -Dm755 deploy/wifi-watchdog /usr/local/sbin/wifi-watchdog
sudo install -Dm644 deploy/wifi-watchdog.service /etc/systemd/system/wifi-watchdog.service
sudo install -Dm644 deploy/wifi-watchdog.timer   /etc/systemd/system/wifi-watchdog.timer
sudo install -Dm644 deploy/wifi-watchdog.default /etc/default/wifi-watchdog
sudo install -Dm755 deploy/wifi-watchdog-selftest /usr/local/sbin/wifi-watchdog-selftest

# Fail here rather than at 3am: check the recovery path's nmcli calls exist.
sudo wifi-watchdog-selftest || echo "do not enable the timer until this passes"

sudo systemctl daemon-reload
sudo systemctl enable --now wifi-watchdog.timer

systemctl status wifi-watchdog.timer
journalctl -u wifi-watchdog -f
```

A system service, not a user one: `nmcli` needs root to reconnect a device,
and this has to run with nobody logged in. It is a oneshot on a timer rather
than a daemon so that a crash inside it cannot take the watchdog out
permanently -- the next tick starts clean -- and the failure count lives in
`/run`, so a reboot starts at zero.

It pings whatever `ip route` currently calls the default gateway rather than
a hardcoded address, because a watchdog aimed at a stale IP fails in the
direction of reporting that everything is fine.

What it cannot do is recreate a NetworkManager profile that has gone missing,
which is half of what happened to jungler. When no wifi profile exists at all
it says so in the journal instead of bouncing a device that has nothing to
bounce to.

The reason it exists is not that either original bug is likely to recur. It
is that the failure was silent in the worst direction: the room kept playing
while every alarm went dark, and it was found by noticing the placard had
stopped changing.

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
