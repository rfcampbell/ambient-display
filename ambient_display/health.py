"""What the placard says about itself, and what it structurally cannot say.

A dark panel has five causes and every one of them looks the same from the
room:

  1. the process died, or is crash-looping
  2. the Pi hung, lost power, or lost its wifi
  3. nothing is arriving from the mixer -- broker down, or jungler silent
  4. THE OVERNIGHT SCHEDULE, which is healthy. `brightness_at` returns 0.0
     from 23:03 to 07:00 and app.py pushes true black, not a dimmed frame.
     On 2026-09-07 the panel was found dark at 06:20 and power-cycled; that
     is inside the blank, and the reboot could not have lit it before 07:00.
     An instrument that does not report this sends someone hunting a fault
     that was never there.
  5. the process is fine and composing frames the panel is not showing

This publishes enough to tell them apart.

WHY THE BEAT IS EMITTED FROM THE RENDER LOOP AND NOT FROM A THREAD OF ITS
OWN. `preview.healthz` already returns "ok" unconditionally, from the Flask
daemon thread, with no reference to the render loop at all -- it would go on
saying ok through a completely wedged renderer. The last wifi outage
surfaced only because someone noticed the placard had frozen, which is that
same wedge seen by eye. A heartbeat on its own timer would reproduce the lie
on MQTT, at which point it would be worse than nothing: a green entity
covering a frozen panel. `maybe_publish` is therefore called from the body of
the loop in `app.main`, so a loop that stops turning stops the beat, and
`expire_after` turns that into `unavailable`.

WHAT THIS CANNOT COVER, said plainly, because a monitor whose blind spots are
undocumented gets read as covering everything:

  * ANY FAILURE THAT PRECEDES ITS OWN STARTUP. If the process dies in
    `config.load` or in `device.make` -- a bad config.json, a panel that will
    not initialise -- nothing here has run and nothing here publishes. That is
    the jungler crash loop of 2026-09-03 exactly: 291 restarts, every
    in-process instrument structurally blind, and the restart sensor serving a
    confident `1` from the last start that worked. deploy/display-stop-notify
    is the answer to that case and the only reason this file is not the same
    trap. It is not an optional extra.
  * A BROKER THAT CANNOT BE REACHED. Then neither this nor the stop notifier
    publishes anything, and a crash loop during a network outage is silent
    from this end. It is covered from the other side, by `expire_after`
    making the entity `unavailable`, and by an alert that watches for
    `unavailable` rather than for a state value.
  * TELLING A HUNG PI FROM A DEAD RADIO FROM A DEAD BROKER, AT THE TIME. All
    three are silence and silence carries no detail. That discrimination is
    retroactive and local: it is what persistent journald buys, which is why
    the two halves of this work shipped together. This says THAT the placard
    went quiet and WHEN. The journal says why.
  * ANYTHING AT ALL IF HOME ASSISTANT OR MOSQUITTO IS DOWN. Both live on
    robix. Nothing outside robix is watching robix.
"""

import datetime as dt
import json
import logging
import os
import socket
import subprocess
import time

log = logging.getLogger(__name__)

# Every 30 s, expire after 120. Four missed beats before Home Assistant calls
# it dead: long enough that a reconnect or a slow frame is not an alarm, short
# enough that "the placard is dark" is answered in minutes rather than in the
# morning. Deliberately tighter than the mixer's 300/900 -- that one is
# rate-limited by checks that cost real work, and this payload is a dict.
BEAT_S = 30.0
EXPIRE_S = 120

DISCOVERY_PREFIX = "homeassistant"

# Folded the same way the mixer folds it, and for the same reason: this ends
# up in an entity_id, and two machines sharing one entity means a live box
# holds a dead box's sensor green.
HOST = "".join(c if c.isalnum() else "_"
               for c in socket.gethostname().split(".")[0].lower()) or "unknown"

NODE = f"ambient_display_{HOST}"


def _utc(ts=None):
    when = dt.datetime.fromtimestamp(ts, dt.timezone.utc) if ts else \
        dt.datetime.now(dt.timezone.utc)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def systemd_restarts(unit=None):
    """How many times systemd has auto-restarted this unit, or None.

    THE SCOPE MUST BE CHECKED, not assumed. `systemctl show -p NRestarts` for
    a unit that does not exist in the scope being asked returns `0` and exits
    0 -- no error, indistinguishable from a healthy unit that has never
    restarted. That was demonstrated on jungler on 2026-09-07: asking system
    scope for `ambient-mixer`, which is a *user* unit, gave back
    `ActiveState=inactive, Result=success, NRestarts=0` for a service that had
    been running for a day and a half. So LoadState is read first, and a unit
    that is `not-found` returns None.

    None is not zero. A count that could not be read must not arrive as a
    reassuring number -- that is the whole failure this family of sensors
    exists to end.
    """
    unit = unit or os.environ.get("AMBIENT_UNIT")
    if not unit:
        # Not under systemd -- run by hand. Say unknown rather than guess.
        return None
    scope = ["--user"] if os.environ.get("XDG_RUNTIME_DIR") else []
    try:
        out = subprocess.run(
            ["systemctl", *scope, "show", unit,
             "--property=LoadState", "--property=NRestarts"],
            capture_output=True, text=True, timeout=5.0)
    except (OSError, subprocess.SubprocessError) as exc:
        log.debug("NRestarts for %s: %s", unit, exc)
        return None
    # Parsed as KEY=value rather than by position, and NOT with `--value`.
    # systemd emits properties in ITS OWN order, not the order they were
    # asked for: on pixelpup 2026-09-07, `-p LoadState -p NRestarts` and
    # `-p NRestarts -p LoadState` both print NRestarts first. Positional
    # parsing therefore reads the count as the load state and vice versa,
    # and the first version of this function did exactly that -- it returned
    # None for a perfectly healthy unit, which would have left the restart
    # sensor blank forever while looking like a deliberate "unknown".
    props = dict(line.split("=", 1)
                 for line in (out.stdout or "").splitlines() if "=" in line)
    if props.get("LoadState") != "loaded":
        log.debug("unit %s not loaded in this scope: %r", unit, out.stdout)
        return None
    val = props.get("NRestarts", "").strip()
    return int(val) if val.isdigit() else None


class Heartbeat:
    """Counters the render loop feeds, and the payload they become.

    Owns no thread. Everything here runs on the caller's stack, inside the
    loop being measured, which is the point.
    """

    def __init__(self, feed, device_name, beat_s=BEAT_S):
        self.feed = feed
        self.device_name = device_name
        self.beat_s = beat_s
        self.unit = os.environ.get("AMBIENT_UNIT") or None
        self.restarts = systemd_restarts(self.unit)
        self.started_utc = _utc()
        self.started_mono = time.monotonic()
        # ticks advance every pass of the loop; frames only when pixels
        # actually changed and were pushed. They are separate because a
        # static placard -- and the whole overnight blank -- pushes nothing
        # while being perfectly healthy, so `frames` alone cannot mean
        # liveness. `ticks` is the one that flatlines on a wedge.
        self.ticks = 0
        self.frames = 0
        self.pushes_failed = 0
        self.last_push_mono = None
        self.last_error = None
        self._last_beat = 0.0
        self._last_material = None

    # -- fed by the render loop --------------------------------------------

    def note_tick(self):
        self.ticks += 1

    def note_push(self, error=None):
        if error is None:
            self.frames += 1
            self.last_push_mono = time.monotonic()
            self.last_error = None
        else:
            self.pushes_failed += 1
            self.last_error = f"{type(error).__name__}: {error}"[:200]

    # -- payload ------------------------------------------------------------

    def payload(self, display):
        s = display.status()
        bright = s.get("brightness", 0.0)
        last_push = None
        if self.last_push_mono is not None:
            last_push = _utc(time.time() - (time.monotonic() - self.last_push_mono))
        return {
            # ok/failing is ONLY about this box's ability to put the frame it
            # composed onto the panel. It is deliberately not a verdict on the
            # room: the mixer going quiet is a different entity, because a
            # placard showing the idle record over a silent mixer is a
            # healthy placard reporting a real thing, and folding the two
            # together produces an alarm nobody can act on.
            "result": "failing" if self.last_error else "ok",
            "error": self.last_error,
            "device": self.device_name,
            # Cause 4. Without this, a correctly blank panel at 03:00 is
            # indistinguishable from a broken one.
            "brightness": round(bright, 3),
            "scheduled_dark": bool(bright <= 0.0),
            "ticks": self.ticks,
            "frames": self.frames,
            "pushes_failed": self.pushes_failed,
            "last_push_utc": last_push,
            # Cause 3, split so the answer names a side. `connected` is our
            # socket to the broker; `mixer_online` is jungler's own last will
            # as we see it. Broker down and mixer down are different mornings.
            "connected": bool(s.get("connected")),
            "mixer_online": s.get("mixer_online"),
            "have_contract": bool(s.get("have_contract")),
            "have_state": bool(s.get("have_state")),
            "records": s.get("records"),
            "featured": s.get("featured"),
            "slide": s.get("slide"),
            "host": HOST,
            "unit": self.unit,
            "restarts": self.restarts,
            "started_utc": self.started_utc,
            "uptime_s": int(time.monotonic() - self.started_mono),
        }

    def _material(self, body):
        """The fields worth waking the bus for between beats.

        Counters and uptime are excluded on purpose: they change every pass,
        and a heartbeat that publishes at 12 Hz is a heartbeat that will be
        turned off.
        """
        return (body["result"], body["scheduled_dark"], body["connected"],
                body["mixer_online"], body["have_contract"], body["records"],
                body["pushes_failed"])

    # -- publishing ---------------------------------------------------------

    def maybe_publish(self, display, now=None, force=False):
        now = now if now is not None else time.monotonic()
        body = self.payload(display)
        material = self._material(body)
        due = force or (now - self._last_beat) >= self.beat_s \
            or material != self._last_material
        if not due:
            return False
        self._last_beat = now
        self._last_material = material
        # Fire-and-forget at QoS 0: paho's network thread does the write, and
        # the render loop must never wait on a broker. A beat lost to a
        # disconnect is not worth a stalled panel -- the next one is 30 s
        # away, and reconnect republishes immediately.
        self.feed.publish_self("display/health", body, retain=True)
        return True

    def discovery(self, state_topic, availability_topic):
        device = {"identifiers": [NODE],
                  "name": f"ambient-display placard ({HOST})",
                  "manufacturer": "ambient-display", "model": "SSD1351 placard"}
        common = {"state_topic": state_topic, "device": device,
                  "origin": {"name": "ambient-display"},
                  # The last will, so a clean drop greys these out at once
                  # instead of waiting the full expire window.
                  "availability_topic": availability_topic,
                  "payload_available": "online",
                  "payload_not_available": "offline"}
        return [
            # THE DEADMAN. Its state says whether the panel is taking frames;
            # its ABSENCE -- expire_after with nothing arriving -- is the part
            # that matters, and it is `unavailable`, not `on`. Anything that
            # pages on this must trigger on unavailable. Triggering on a state
            # value is what left ambient_health_jungler_failing silent through
            # 23 hours of crash loop.
            (f"{DISCOVERY_PREFIX}/binary_sensor/{NODE}/alive/config", dict(
                common, name=f"placard alive ({HOST})",
                unique_id=f"{NODE}_alive",
                default_entity_id=f"binary_sensor.{NODE}_alive",
                device_class="problem",
                payload_on="failing", payload_off="ok",
                value_template="{{ value_json.result }}",
                json_attributes_topic=state_topic,
                expire_after=EXPIRE_S,
                icon="mdi:television-ambient-light")),
            # Cause 4, as a number a person can read. "It is dark and
            # brightness is 0.0 at 04:00" is a working placard; the same
            # panel dark with brightness 1.0 is a fault.
            (f"{DISCOVERY_PREFIX}/sensor/{NODE}/brightness/config", dict(
                common, name=f"placard brightness ({HOST})",
                unique_id=f"{NODE}_brightness",
                default_entity_id=f"sensor.{NODE}_brightness",
                value_template="{{ value_json.brightness }}",
                state_class="measurement", expire_after=EXPIRE_S,
                icon="mdi:brightness-6")),
            # Cause 3. Separate from the deadman because the placard can be
            # entirely healthy while this is a problem.
            (f"{DISCOVERY_PREFIX}/binary_sensor/{NODE}/feed/config", dict(
                common, name=f"placard feed ({HOST})",
                unique_id=f"{NODE}_feed",
                default_entity_id=f"binary_sensor.{NODE}_feed",
                device_class="problem",
                payload_on="False", payload_off="True",
                value_template=(
                    "{{ value_json.connected and value_json.have_contract }}"),
                json_attributes_topic=state_topic,
                expire_after=EXPIRE_S,
                icon="mdi:transit-connection-variant")),
            # THE WEDGE DETECTOR. A flat line here with brightness above zero
            # is a render loop that has stopped turning, and it is visible on
            # a graph well before expire_after fires. total_increasing so a
            # restart reads as a restart rather than as a cliff.
            (f"{DISCOVERY_PREFIX}/sensor/{NODE}/ticks/config", dict(
                common, name=f"placard render ticks ({HOST})",
                unique_id=f"{NODE}_ticks",
                default_entity_id=f"sensor.{NODE}_ticks",
                value_template="{{ value_json.ticks }}",
                state_class="total_increasing",
                expire_after=EXPIRE_S, icon="mdi:pulse")),
            # No expire_after on the two below, for the reason the mixer's
            # last_ok carries none: a retained message replayed on a Home
            # Assistant restart re-arms an expiry clock from what may be a
            # corpse. A timestamp cannot be freshened that way. Their job is
            # to survive and go on saying what they said; freshness is the
            # deadman's question, and it is answered above.
            (f"{DISCOVERY_PREFIX}/sensor/{NODE}/started/config", dict(
                common, name=f"placard started ({HOST})",
                unique_id=f"{NODE}_started",
                default_entity_id=f"sensor.{NODE}_started",
                value_template="{{ value_json.started_utc }}",
                device_class="timestamp", icon="mdi:play-circle-outline")),
            # The in-process restart count, which can only ever report
            # restarts the process SURVIVED. Its honest twin is published by
            # display-stop-notify from outside; when they disagree, that one
            # is right and this one is the reassuring number.
            (f"{DISCOVERY_PREFIX}/sensor/{NODE}/restarts/config", dict(
                common, name=f"placard restarts, in process ({HOST})",
                unique_id=f"{NODE}_restarts",
                default_entity_id=f"sensor.{NODE}_restarts",
                value_template="{{ value_json.restarts }}",
                state_class="total_increasing", icon="mdi:restart")),
        ]
