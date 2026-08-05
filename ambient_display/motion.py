"""Slow movement: burn-in drift, which recording is featured, which slide is
showing, and the day/night curve.

Nothing here steps. Every value returned is a point on an eased ramp.
"""

import random
from dataclasses import dataclass, field


def smoothstep(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


# --- burn-in drift ----------------------------------------------------------

@dataclass
class Drift:
    """A slow random walk over a small lattice of whole-pixel offsets.

    The walk is eased, and the layout is re-rendered at the fractional
    position rather than the frame being resampled, so the type stays crisp
    the whole way across.
    """
    amplitude: int = 3
    interval: float = 300.0
    ease: float = 20.0
    rng: random.Random = field(default_factory=random.Random)
    _from: tuple = (0.0, 0.0)
    _to: tuple = (0.0, 0.0)
    _started: float = 0.0
    _next: float = 0.0

    def _pick(self, now):
        a = self.amplitude
        if a <= 0:
            return (0.0, 0.0)
        choices = [(x, y)
                   for x in range(-a, a + 1)
                   for y in range(-a, a + 1)
                   if (x, y) != self._to and x * x + y * y <= a * a + 1]
        return self.rng.choice(choices) if choices else (0.0, 0.0)

    def offset(self, now):
        if self._next == 0.0:
            self._next = now + self.interval
        if now >= self._next:
            self._from = self.offset_now(now)
            self._to = self._pick(now)
            self._started = now
            self._next = now + self.interval + self.rng.uniform(-0.15, 0.15) * self.interval
        return self.offset_now(now)

    def offset_now(self, now):
        if self.ease <= 0:
            return self._to
        t = smoothstep((now - self._started) / self.ease)
        return (self._from[0] + (self._to[0] - self._from[0]) * t,
                self._from[1] + (self._to[1] - self._from[1]) * t)


# --- which recording is featured --------------------------------------------

@dataclass
class Feature:
    """Picks the one recording the placard is currently about.

    Whichever bus most recently changed file wins -- that's the news. A
    minimum dwell keeps it from flitting when several buses turn over close
    together: having just committed to a recording, the placard stays with it
    long enough to finish saying what it has to say.
    """
    min_dwell: float = 300.0
    _stamps: dict = field(default_factory=dict)      # bus -> (file, when)
    _bus: str = None
    _since: float = 0.0

    def choose(self, records, now):
        if not records:
            self._bus = None
            return None

        live = {r.bus for r in records}
        self._stamps = {k: v for k, v in self._stamps.items() if k in live}
        for record in records:
            previous = self._stamps.get(record.bus)
            if previous is None or previous[0] != record.file:
                self._stamps[record.bus] = (record.file, now)

        current = next((r for r in records if r.bus == self._bus), None)
        # Ties (everything stamped on the same first pass) fall to contract
        # order, because max() keeps the first maximal element.
        newest = max(records, key=lambda r: self._stamps[r.bus][1])

        if current is None:
            chosen = newest
        elif newest.bus != current.bus and (now - self._since) >= self.min_dwell:
            chosen = newest
        else:
            chosen = current

        if self._bus != chosen.bus:
            self._bus = chosen.bus
            self._since = now
        return chosen

    def held_for(self, now):
        return now - self._since


# --- which slide is showing -------------------------------------------------

@dataclass
class SlideShow:
    """Turns the pages of one recording, crossfading between them."""
    hold: float = 75.0
    jitter: float = 15.0
    fade: float = 8.0
    rng: random.Random = field(default_factory=random.Random)
    slides: list = field(default_factory=list)
    _i: int = 0
    _prev: object = None
    _changed_at: float = 0.0
    _shown_at: float = 0.0
    _hold_now: float = 0.0

    def _pick_hold(self):
        return max(1.0, self.hold + self.rng.uniform(-self.jitter, self.jitter))

    def current(self):
        return self.slides[self._i] if self.slides else None

    def set(self, slides, now):
        """Install the featured recording's slides."""
        if not slides:
            self.slides = []
            self._i = 0
            return
        keys = [s.key for s in slides]
        showing = self.current()
        if showing is not None and showing.key in keys:
            # Same recording, refreshed metadata: hold position.
            self.slides = slides
            self._i = keys.index(showing.key)
            return
        self._prev = showing
        self.slides = slides
        self._i = 0
        self._changed_at = now
        self._shown_at = now
        self._hold_now = self._pick_hold()

    def tick(self, now):
        """-> (outgoing, incoming, alpha). alpha 0 shows the outgoing slide."""
        if not self.slides:
            return None, None, 1.0
        if self._hold_now <= 0:
            self._hold_now = self._pick_hold()
            self._shown_at = now

        if len(self.slides) > 1 and now - self._shown_at >= self._hold_now:
            self._prev = self.current()
            self._i = (self._i + 1) % len(self.slides)
            self._changed_at = now
            self._shown_at = now
            self._hold_now = self._pick_hold()

        showing = self.current()
        if self._prev is None or self.fade <= 0:
            return None, showing, 1.0
        alpha = smoothstep((now - self._changed_at) / self.fade)
        if alpha >= 1.0:
            self._prev = None
            return None, showing, 1.0
        return self._prev, showing, alpha


# --- day / night ------------------------------------------------------------

def _seconds(hhmm):
    hours, _, minutes = str(hhmm).partition(":")
    return (int(hours) * 3600 + int(minutes or 0) * 60) % 86400


def brightness_at(now_local, cfg):
    """Brightness 0..1 for a datetime, following the schedule.

    Full through the day, easing down through the evening, off overnight.
    The overnight blank is the point -- an OLED showing nothing at 3am is an
    OLED that still looks new in five years.
    """
    if not cfg.get("enabled", True):
        return 1.0

    wake = _seconds(cfg.get("wake", "07:00"))
    evening = _seconds(cfg.get("evening", "20:00"))
    sleep = _seconds(cfg.get("sleep", "23:00"))
    night = max(0.0, min(1.0, float(cfg.get("night_level", 0.55))))
    fade = max(1.0, float(cfg.get("fade_seconds", 180)))

    now = (now_local.hour * 3600 + now_local.minute * 60 + now_local.second - wake) % 86400
    evening = (evening - wake) % 86400
    sleep = (sleep - wake) % 86400
    if sleep <= evening:
        sleep = evening + 1.0

    anchors = sorted([(0.0, 0.0), (fade, 1.0), (evening, 1.0),
                      (sleep, night), (min(sleep + fade, 86399.0), 0.0),
                      (86400.0, 0.0)], key=lambda a: a[0])

    for (t0, v0), (t1, v1) in zip(anchors, anchors[1:]):
        if t0 <= now <= t1:
            if t1 == t0:
                return v1
            return v0 + (v1 - v0) * ((now - t0) / (t1 - t0))
    return 0.0
