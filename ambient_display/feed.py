"""MQTT feed.

ambient/nowplaying is the source of truth for what's loaded and it is
retained, so a placard appears the moment we connect. ambient/state is read
too when available -- it carries per-bus `sounding`, which is what decides
whether a bus earns a placard at all. Neither is required: with state absent
we fall back to the contract's own level.
"""

import json
import logging
import threading

import paho.mqtt.client as mqtt

log = logging.getLogger(__name__)


class Feed:
    def __init__(self, cfg, on_change=None):
        self.cfg = cfg["mqtt"]
        self.on_change = on_change
        self.lock = threading.Lock()
        self.contract = None
        self.state = None
        self.online = None
        self.connected = False
        self._client = None

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

    # -- mqtt ---------------------------------------------------------------

    def start(self):
        c = self.cfg
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                             client_id=c.get("client_id") or None)
        if c.get("username"):
            client.username_pw_set(c["username"], c.get("password"))
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        # paho retries with backoff on its own once the loop is running.
        client.reconnect_delay_set(min_delay=1, max_delay=60)
        client.connect_async(c["host"], c["port"], c.get("keepalive", 60))
        client.loop_start()
        self._client = client
        return self

    def stop(self):
        if self._client:
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
        log.info("mqtt connected to %s:%s, subscribed to %s",
                 self.cfg["host"], self.cfg["port"], ", ".join(self._topics()))

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
