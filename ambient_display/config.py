"""Config: JSON on disk, deep-merged over the defaults below."""

import json
import os

from . import theme as theme_mod

DEFAULTS = {
    "mqtt": {
        "host": "192.168.221.163",
        "port": 1883,
        "topic": "ambient/nowplaying",
        "state_topic": "ambient/state",
        "availability_topic": "ambient/availability",
        "use_state": True,
        "username": None,
        "password": None,
        "keepalive": 60,
        # null lets paho pick a unique id. Two clients sharing an id keep
        # kicking each other off the broker, which bites when a dev instance
        # is running alongside the one on Bloopy. Pin it if you want the
        # client recognisable broker-side.
        "client_id": None,
    },
    "display": {
        # noop -> preview only (no hardware, no X). emulator/capture/gifanim
        # are luma.emulator. ssd1351 is the panel on Bloopy.
        "device": "noop",
        "width": 128,
        "height": 128,
        "rotate": 0,
        "fps": 12,
        "brightness": 1.0,
        "spi": {
            "port": 0,
            "device": 0,
            "bus_speed_hz": 16000000,
            "gpio_dc": 25,
            "gpio_rst": 27,
        },
        "ssd1351": {"bgr": True},
        "emulator": {"transform": "none", "scale": 4},
    },
    "rotation": {"hold_seconds": 45, "fade_seconds": 6},
    "burnin": {"amplitude": 3, "interval_seconds": 300, "ease_seconds": 20},
    "schedule": {
        "enabled": True,
        "wake": "07:00",
        "evening": "20:00",
        "sleep": "23:00",
        "night_level": 0.55,
        "fade_seconds": 180,
    },
    "content": {
        "known_only": True,
        "subtitle_blocklist": ["Sonus naturalis"],
        "remark_truncate": True,
    },
    "preview": {"enabled": True, "host": "0.0.0.0", "port": 8324, "dev": True},
    "theme": {},
}

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")


def _merge(base, over):
    out = dict(base)
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load(path=None):
    """Read config.json if present. Missing file is fine -- defaults work."""
    path = path or DEFAULT_PATH
    data = {}
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    cfg = _merge(DEFAULTS, data)
    cfg["_path"] = path
    return cfg


def theme_of(cfg):
    """Full theme dict: theme defaults + the config's theme block."""
    t = theme_mod.merged(cfg.get("theme"))
    t["remark_truncate"] = cfg.get("content", {}).get("remark_truncate", True)
    return t
