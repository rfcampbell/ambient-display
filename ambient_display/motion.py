"""Slow movement: burn-in drift, card rotation, and the day/night curve.

Nothing here steps. Every value returned is a point on an eased ramp, so the
panel only ever shows a state that is on its way somewhere.
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


# --- card rotation ----------------------------------------------------------

@dataclass
class Rotation:
    """Holds one card, then crossfades to the next. New recordings jump the
    queue so the placard tracks what the mixer just started."""
    hold: float = 45.0
    fade: float = 6.0
    cards: list = field(default_factory=list)
    _order: list = field(default_factory=list)
    _priority: list = field(default_factory=list)
    _seen: set = field(default_factory=set)
    _current: object = None
    _previous: object = None
    _changed_at: float = 0.0
    _held_since: float = 0.0

    def update(self, cards, now):
        """Install a new card list, preserving position where possible."""
        self.cards = cards
        keys = [c.key for c in cards]
        first_load = not self._seen
        fresh = [k for k in keys if k not in self._seen]
        self._seen = set(keys)

        # Keep the established cycle order, drop what's gone, append the rest
        # in contract order.
        self._order = [k for k in self._order if k in self._seen]
        for key in keys:
            if key not in self._order:
                self._order.append(key)

        # A recording that just started is the news; show it next rather than
        # waiting for it to come round. (On first load everything is "new",
        # so the contract's own order stands.)
        if not first_load:
            for key in fresh:
                if key not in self._priority:
                    self._priority.append(key)
        self._priority = [k for k in self._priority if k in self._seen]

        if self._current is not None and self._current.key in self._seen:
            # Refresh the object in case its metadata changed.
            self._current = next(c for c in cards if c.key == self._current.key)
        elif cards:
            self._advance(now, immediate=self._current is None)

    def _by_key(self, key):
        return next((c for c in self.cards if c.key == key), None)

    def _advance(self, now, immediate=False):
        if not self._order:
            return
        nxt = None
        while self._priority and nxt is None:
            key = self._priority.pop(0)
            if self._current is None or key != self._current.key:
                nxt = self._by_key(key)
        if nxt is None:
            if self._current is None:
                nxt = self._by_key(self._order[0])
            else:
                try:
                    i = self._order.index(self._current.key)
                except ValueError:
                    i = -1
                nxt = self._by_key(self._order[(i + 1) % len(self._order)])
        if nxt is None:
            return
        self._previous = None if immediate else self._current
        self._current = nxt
        self._changed_at = now
        self._held_since = now

    def tick(self, now):
        """-> (outgoing_card, incoming_card, alpha). alpha 0 shows outgoing."""
        if self._current is None:
            return None, None, 1.0

        if len(self.cards) > 1 and now - self._held_since >= self.hold + self.fade:
            self._advance(now)

        if self._previous is None or self.fade <= 0:
            return None, self._current, 1.0
        alpha = smoothstep((now - self._changed_at) / self.fade)
        if alpha >= 1.0:
            self._previous = None
            return None, self._current, 1.0
        return self._previous, self._current, alpha


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

    # (seconds since wake, brightness) anchors, interpolated linearly.
    anchors = [(0.0, 0.0), (fade, 1.0), (evening, 1.0),
               (sleep, night), (min(sleep + fade, 86399.0), 0.0), (86400.0, 0.0)]
    anchors = sorted(anchors, key=lambda a: a[0])

    for (t0, v0), (t1, v1) in zip(anchors, anchors[1:]):
        if t0 <= now <= t1:
            if t1 == t0:
                return v1
            return v0 + (v1 - v0) * ((now - t0) / (t1 - t0))
    return 0.0
