"""Output device. The panel is the only thing that changes between the
development machine and Bloopy, so it's the only thing behind a factory.

Every device exposes .display(PIL.Image) and .cleanup().
"""

import logging

log = logging.getLogger(__name__)


class Noop:
    """Preview-only. The default until the panel is wired up."""

    def __init__(self, width=128, height=128, **_):
        self.width = width
        self.height = height

    def display(self, image):
        pass

    def cleanup(self):
        pass


def make(cfg):
    """Build the output device named in config['display']['device']."""
    d = cfg["display"]
    kind = (d.get("device") or "noop").lower()
    width, height = d["width"], d["height"]
    rotate = d.get("rotate", 0)

    if kind in ("noop", "none", "preview"):
        return Noop(width, height)

    if kind == "ssd1351":
        # The real panel: Waveshare 1.5" 128x128 RGB OLED over SPI.
        try:
            from luma.core.interface.serial import spi
            from luma.oled.device import ssd1351
        except ImportError as exc:
            raise RuntimeError(
                f"the ssd1351 device needs luma.oled and Pi GPIO support ({exc}). "
                "On anything but the Pi use device 'noop' or 'emulator'."
            ) from exc

        s = d.get("spi", {})
        serial = spi(
            port=s.get("port", 0),
            device=s.get("device", 0),
            bus_speed_hz=s.get("bus_speed_hz", 16000000),
            gpio_DC=s.get("gpio_dc", 25),
            gpio_RST=s.get("gpio_rst", 27),
        )
        device = ssd1351(serial, width=width, height=height, rotate=rotate,
                         bgr=d.get("ssd1351", {}).get("bgr", True))
        # Contrast stays at the panel default on purpose: burn-in is managed
        # by keeping the RGB values themselves low, which also keeps the
        # antialiasing ramp intact. See README.
        return device

    # luma.emulator stand-ins.
    from luma.emulator import device as emu

    e = d.get("emulator", {})
    kwargs = dict(width=width, height=height, rotate=rotate, mode="RGB",
                  transform=e.get("transform", "none"), scale=e.get("scale", 4))
    if kind in ("emulator", "pygame"):
        return emu.pygame(**kwargs)
    if kind == "capture":
        return emu.capture(file_template=e.get("file_template", "frame_{0:06}.png"),
                           **kwargs)
    if kind == "gifanim":
        return emu.gifanim(filename=e.get("filename", "ambient.gif"), **kwargs)

    raise ValueError(f"unknown display device: {kind!r}")
