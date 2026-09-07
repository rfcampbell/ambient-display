"""MQTT feed.

ambient/nowplaying is the source of truth for what's loaded and it is
retained, so a placard appears the moment we connect. ambient/state is read
too when available -- it carries per-bus `sounding`, which is what decides
whether a bus earns a placard at all. Neither is required: with state absent
we fall back to the contract's own level.

The same client also PUBLISHES, under a base of this box's own
(`ambient/<host>/...`), which is where the placard says whether it is alive.
One client rather than two: it halves the connections to the broker, and it
means the last will below covers the same socket the heartbeat rides on, so
the two can never disagree about whether we are connected.

THE LAST WILL AND `expire_after` ARE NOT THE SAME MECHANISM and neither
replaces the other:

  * The will is the BROKER saying our TCP session ended. It is prompt for a
    crash -- the socket closes at once -- and slow for a hung Pi or a dead
    radio, where nothing closes and the broker must wait out keepalive x 1.5.
  * `expire_after` on the retained heartbeat is Home Assistant saying nothing
    has been SAID for two minutes. It is the only one of the two that catches
    a process still holding a healthy socket while no longer doing its work.
    A wedged render loop keeps the connection open indefinitely; the will
    never fires for it, ever.

So: the will covers a clean disconnect, expire_after covers a publisher that
stopped producing, and the pair still cannot cover a failure that happens
before this module is imported. That one is deploy/display-stop-notify.
"""

import json
import logging
import threading

import paho.mqtt.client as mqtt

from .health import HOST

log = logging.getLogger(__name__)


class Feed:
    def __init__(self, cfg, on_change=None):
        self.cfg = cfg["mqtt"]
        self.on_change = on_change
        # Called after every successful (re)connect, on paho's network
        # thread. The heartbeat uses it to re-assert discovery and put a
        # fresh beat on the bus immediately, rather than leaving up to a full
        # interval of silence behind a reconnect.
        self.on_connect_hook = None
        self.lock = threading.Lock()
        self.contract = None
        self.state = None
        self.online = None
        self.connected = False
        self._client = None
        # Host-derived, like the mixer's. Never shared between machines: two
        # boxes publishing one topic means a live one holds a dead one green.
        self.publish_base = str(
            self.cfg.get("publish_base") or f"ambient/{HOST}").strip("/")

    # -- snapshot for the render loop / preview -----------------------------

    def snapshot(self):
        with self.lock:
            return self.contract, self.state

    def status(self):
        with self.lock:
            return {
                "connected": self.connected,
                "mixer_online": self.online,
                "have_contract": self.contract is not None,
                "have_state": self.state is not None,
                "broker": f"{self.cfg['host']}:{self.cfg['port']}",
            }

    # -- offline / replay ---------------------------------------------------

    def inject(self, contract, state=None):
        """Feed a payload directly, for --replay and tests."""
        with self.lock:
            self.contract = contract
            if state is not None:
                self.state = state
        if self.on_change:
            self.on_change()

    # -- topics we own ------------------------------------------------------

    @property
    def self_availability_topic(self):
        """OURS. Not to be confused with cfg['availability_topic'], which is
        the mixer's will and something we only ever read."""
        return f"{self.publish_base}/availability"

    def self_topic(self, subtopic):
        return f"{self.publish_base}/{subtopic.strip('/')}"

    def publish_self(self, subtopic, obj, retain=True, qos=0):
        """Publish under our own base. Never raises and never blocks.

        Called from the render loop. A broker that is unreachable must cost
        the panel nothing at all, so the result is dropped rather than waited
        on: paho queues, its network thread writes, and a beat lost to a
        disconnect is replaced by the next one 30 s later.
        """
        if not self._client:
            return False
        body = obj if isinstance(obj, (str, bytes)) else json.dumps(obj, sort_keys=True)
        try:
            self._client.publish(self.self_topic(subtopic), body,
                                 qos=qos, retain=retain)
            return True
        except Exception as exc:                      # never take the loop down
            log.debug("publish %s failed: %s", subtopic, exc)
            return False

    def publish_raw(self, topic, obj, retain=True, qos=0):
        """Same, on an absolute topic. Home Assistant discovery lives outside
        our base."""
        if not self._client:
            return False
        body = obj if isinstance(obj, (str, bytes)) else json.dumps(obj, sort_keys=True)
        try:
            self._client.publish(topic, body, qos=qos, retain=retain)
            return True
        except Exception as exc:
            log.debug("publish %s failed: %s", topic, exc)
            return False

    # -- mqtt ---------------------------------------------------------------

    def start(self):
        c = self.cfg
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id=c.get("client_id") or f"ambient-display-{HOST}")
        if c.get("username"):
            client.username_pw_set(c["username"], c.get("password"))
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        # Retained, so Home Assistant greys the placard's entities out the
        # moment the broker notices the socket is gone -- and so a subscriber
        # that connects later is told immediately rather than being left to
        # infer it from an absence.
        client.will_set(self.self_availability_topic, "offline", retain=True)
        # paho retries with backoff on its own once the loop is running.
        client.reconnect_delay_set(min_delay=1, max_delay=60)
        client.connect_async(c["host"], c["port"], c.get("keepalive", 60))
        client.loop_start()
        self._client = client
        return self

    def stop(self):
        if self._client:
            # Say offline on the way out. A clean stop suppresses the will --
            # paho sends a DISCONNECT and the broker deliberately does not
            # publish it -- so without this line a deliberate `systemctl stop`
            # would leave the last retained availability reading `online`
            # forever, which is the reassuring-stale-value fault in its
            # purest form.
            try:
                self._client.publish(self.self_availability_topic, "offline",
                                     qos=1, retain=True).wait_for_publish(timeout=2)
            except Exception:
                pass
            self._client.loop_stop()
            try:
                self._client.disconnect()
            except Exception:
                pass

    def _topics(self):
        c = self.cfg
        topics = [c["topic"]]
        if c.get("use_state", True) and c.get("state_topic"):
            topics.append(c["state_topic"])
        if c.get("availability_topic"):
            topics.append(c["availability_topic"])
        return topics

    def _on_connect(self, client, _userdata, _flags, reason, _props=None):
        if getattr(reason, "is_failure", False):
            log.warning("mqtt connect failed: %s", reason)
            return
        self.connected = True
        for topic in self._topics():
            client.subscribe(topic, qos=0)
        client.publish(self.self_availability_topic, "online", retain=True)
        log.info("mqtt connected to %s:%s, subscribed to %s, publishing under %s",
                 self.cfg["host"], self.cfg["port"], ", ".join(self._topics()),
                 self.publish_base)
        if self.on_connect_hook:
            try:
                self.on_connect_hook()
            except Exception as exc:
                log.warning("on_connect hook failed: %s", exc)

    def _on_disconnect(self, _client, _userdata, _flags, reason, _props=None):
        self.connected = False
        log.warning("mqtt disconnected (%s); will retry", reason)

    def _on_message(self, _client, _userdata, msg):
        c = self.cfg
        changed = False
        try:
            if msg.topic == c.get("availability_topic"):
                with self.lock:
                    self.online = msg.payload.decode("utf-8", "replace").strip() == "online"
                return
            payload = json.loads(msg.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            log.warning("bad payload on %s: %s", msg.topic, exc)
            return

        with self.lock:
            if msg.topic == c["topic"]:
                changed = payload != self.contract
                self.contract = payload
            elif msg.topic == c.get("state_topic"):
                # State ticks constantly; only wake the renderer when the part
                # we care about -- which buses are sounding -- actually moves.
                changed = _sounding(payload) != _sounding(self.state)
                self.state = payload

        if changed and self.on_change:
            self.on_change()


def _sounding(state):
    if not isinstance(state, dict):
        return None
    return {name: (info.get("sounding"), info.get("enabled"))
            for name, info in (state.get("buses") or {}).items()
            if isinstance(info, dict)}
