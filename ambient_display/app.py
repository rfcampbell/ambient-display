"""The display client: subscribe, feature a recording, turn its pages."""

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime

from PIL import Image

from . import config as config_mod
from . import device as device_mod
from . import motion
from . import records as records_mod
from . import render
from . import slides as slides_mod
from .feed import Feed

log = logging.getLogger("ambient-display")


class Display:
    """Owns the frame. The panel and the preview both read it here, so they
    can never disagree about what is on screen."""

    def __init__(self, cfg, feed):
        self.cfg = cfg
        self.feed = feed
        self.size = (cfg["display"]["width"], cfg["display"]["height"])
        self._theme = config_mod.theme_of(cfg)

        b = cfg["burnin"]
        self.drift = motion.Drift(amplitude=b["amplitude"],
                                  interval=b["interval_seconds"],
                                  ease=b["ease_seconds"])
        r = cfg["rotation"]
        self.feature = motion.Feature(min_dwell=r["feature_min_dwell_seconds"])
        self.show = motion.SlideShow(hold=r["slide_hold_seconds"],
                                     jitter=r["slide_hold_jitter"],
                                     fade=r["slide_fade_seconds"])

        self.lock = threading.Lock()
        self.frame = Image.new("RGB", self.size, (0, 0, 0))
        self.records = []
        self.brightness = 1.0
        self.offset = (0.0, 0.0)
        self._featured = None
        self._cache = {}

    # -- content ------------------------------------------------------------

    def theme(self):
        return dict(self._theme)

    def all_slides(self):
        """Every slide of every sounding record -- what the preview browses."""
        with self.lock:
            records = list(self.records)
        with_map = self.cfg["content"].get("with_map", True)
        out = []
        for record in records or [records_mod.idle_record()]:
            out.extend(slides_mod.slides_for(record, with_map=with_map))
        return out

    def reload(self):
        contract, state = self.feed.snapshot()
        c = self.cfg["content"]
        built = records_mod.build(contract, state,
                                  known_only=c.get("known_only", True),
                                  place_label=c.get("place_label", "country"))
        with self.lock:
            self.records = built

    def on_feed_change(self):
        self.reload()

    # -- rendering ----------------------------------------------------------

    def _render(self, slide, offset, theme=None):
        """A slide at full brightness, memoised on (slide, offset)."""
        if theme is not None:
            return render.render_slide(slide, theme, self.size, offset)
        key = (slide.key, round(offset[0], 2), round(offset[1], 2))
        image = self._cache.get(key)
        if image is None:
            image = render.render_slide(slide, self._theme, self.size, offset)
            if len(self._cache) > 24:
                self._cache.clear()
            self._cache[key] = image
        return image

    def render_still(self, index, overrides=None):
        """A slide with no drift and no night fade, for the preview bench.

        In dev mode the config is re-read first, so editing config.json and
        hitting refresh is enough to see a change.
        """
        if self.cfg["preview"].get("dev", True):
            try:
                fresh = config_mod.load(self.cfg.get("_path"))
                self._theme = config_mod.theme_of(fresh)
            except (OSError, ValueError) as exc:
                log.warning("config reload failed: %s", exc)
        t = dict(self._theme)
        if overrides:
            t.update(overrides)
        items = self.all_slides()
        if not items:
            return Image.new("RGB", self.size, (0, 0, 0))
        slide = items[max(0, min(len(items) - 1, index))]
        return render.render_slide(slide, t, self.size, (0.0, 0.0))

    def live_frame(self):
        with self.lock:
            return self.frame.copy()

    def tick(self, now, wall=None):
        """Advance every slow thing by one frame and compose."""
        with self.lock:
            records = list(self.records)

        # Featuring is decided every frame, not only when the feed changes:
        # a bus that became the newest while another was still inside its
        # minimum dwell has to be picked up once that dwell expires.
        record = self.feature.choose(records, now) or records_mod.idle_record()
        if self._featured != record.key:
            self._featured = record.key
            self.show.set(slides_mod.slides_for(
                record, with_map=self.cfg["content"].get("with_map", True)), now)

        offset = self.drift.offset(now)
        brightness = motion.brightness_at(wall or datetime.now(), self.cfg["schedule"])
        brightness *= float(self.cfg["display"].get("brightness", 1.0))

        outgoing, incoming, alpha = self.show.tick(now)

        if brightness <= 0.0 or incoming is None:
            # Overnight: push true black rather than a dimmed placard.
            image = Image.new("RGB", self.size, (0, 0, 0))
        else:
            image = self._render(incoming, offset)
            if outgoing is not None and alpha < 1.0:
                image = render.blend(self._render(outgoing, offset), image, alpha)
            if brightness < 1.0:
                image = render.dim(image, brightness)

        with self.lock:
            self.frame = image
            self.brightness = brightness
            self.offset = offset
        return image

    def status(self):
        s = self.feed.status()
        with self.lock:
            s.update({"brightness": round(self.brightness, 3),
                      "offset": [round(v, 2) for v in self.offset],
                      "records": len(self.records)})
        showing = self.show.current()
        s["featured"] = self._featured
        s["slide"] = showing.kind if showing else None
        s["slides"] = len(self.show.slides)
        return s


def _sheet(display, path, scale=3):
    """Every slide of every sounding record, side by side."""
    items = display.all_slides()
    t = display.theme()
    images = [render.render_slide(s, t, display.size) for s in items]
    w, h = display.size
    pad = 6
    sheet = Image.new("RGB", (len(images) * (w * scale + pad) + pad,
                              h * scale + 2 * pad), (24, 24, 24))
    for i, image in enumerate(images):
        sheet.paste(image.resize((w * scale, h * scale), Image.NEAREST),
                    (pad + i * (w * scale + pad), pad))
    sheet.save(path)
    return path


def build_args():
    p = argparse.ArgumentParser(prog="ambient-display",
                                description="Placard display client for ambient-mixer.")
    p.add_argument("-c", "--config", default=None, help="path to config.json")
    p.add_argument("--device", default=None,
                   help="override display device (noop, emulator, capture, gifanim, ssd1351)")
    p.add_argument("--replay", metavar="CONTRACT.json",
                   help="render this contract instead of connecting to MQTT")
    p.add_argument("--state", metavar="STATE.json",
                   help="state payload to accompany --replay")
    p.add_argument("--no-mqtt", action="store_true", help="don't connect to the broker")
    p.add_argument("--no-preview", action="store_true", help="don't serve the web preview")
    p.add_argument("--host", default=None, help="preview bind host")
    p.add_argument("--port", type=int, default=None, help="preview port")
    p.add_argument("--force-day", action="store_true",
                   help="ignore the overnight schedule (development)")
    p.add_argument("--once", metavar="OUT.png", help="render one frame and exit")
    p.add_argument("--sheet", metavar="OUT.png",
                   help="render every slide of every record and exit")
    p.add_argument("--log-level", default="INFO")
    return p


def main(argv=None):
    args = build_args().parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    cfg = config_mod.load(args.config)
    if args.device:
        cfg["display"]["device"] = args.device
    if args.force_day:
        cfg["schedule"]["enabled"] = False
    if args.host:
        cfg["preview"]["host"] = args.host
    if args.port:
        cfg["preview"]["port"] = args.port
    if args.no_preview:
        cfg["preview"]["enabled"] = False

    feed = Feed(cfg)
    display = Display(cfg, feed)
    feed.on_change = display.on_feed_change

    offline = args.replay or args.no_mqtt
    if args.replay:
        with open(args.replay, encoding="utf-8") as handle:
            contract = json.load(handle)
        state = None
        state_path = args.state
        if not state_path:
            sibling = os.path.join(os.path.dirname(os.path.abspath(args.replay)),
                                   "STATE.json")
            state_path = sibling if os.path.exists(sibling) else None
        if state_path:
            with open(state_path, encoding="utf-8") as handle:
                state = json.load(handle)
        feed.inject(contract, state)
    elif not args.no_mqtt:
        feed.start()

    display.reload()

    if args.sheet or args.once:
        if not offline:
            _wait_for_content(display, 5.0)
        if args.sheet:
            print(_sheet(display, args.sheet))
        if args.once:
            display.tick(time.monotonic()).save(args.once)
            print(args.once)
        feed.stop()
        return 0

    device = device_mod.make(cfg)
    log.info("display device: %s", cfg["display"]["device"])

    if cfg["preview"].get("enabled", True):
        from .preview import create_app
        server = create_app(display)
        host, port = cfg["preview"]["host"], cfg["preview"]["port"]
        threading.Thread(
            target=lambda: server.run(host=host, port=port, threaded=True,
                                      debug=False, use_reloader=False),
            daemon=True, name="preview").start()
        log.info("preview on http://%s:%s/", host, port)

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())

    interval = 1.0 / max(1, cfg["display"].get("fps", 12))
    last_pushed = None
    log.info("running")
    try:
        while not stop.is_set():
            started = time.monotonic()
            image = display.tick(started)
            # Only touch the bus when the pixels actually changed; a static
            # placard should cost nothing.
            payload = image.tobytes()
            if payload != last_pushed:
                device.display(image)
                last_pushed = payload
            stop.wait(max(0.0, interval - (time.monotonic() - started)))
    finally:
        log.info("stopping")
        feed.stop()
        try:
            device.display(Image.new("RGB", display.size, (0, 0, 0)))
            device.cleanup()
        except Exception:
            pass
    return 0


def _wait_for_content(display, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        contract, _ = display.feed.snapshot()
        if contract is not None:
            display.reload()
            return True
        time.sleep(0.2)
    log.warning("no contract received within %.0fs", timeout)
    return False


if __name__ == "__main__":
    sys.exit(main())
