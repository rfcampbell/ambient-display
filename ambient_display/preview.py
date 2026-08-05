"""Web preview: the rendered frame as PNG at 1x and 4x, plus a typography
bench that re-reads the theme on every request so you can tune type in a
browser instead of restarting the client."""

import io
import json
import logging

from flask import Flask, Response, jsonify, request
from PIL import Image

from . import theme as theme_mod

log = logging.getLogger(__name__)

PAGE = """<!doctype html>
<meta charset="utf-8"><title>ambient-display preview</title>
<style>
 :root { color-scheme: dark; }
 body { background:#111; color:#b9b2a2; font:13px/1.5 ui-monospace,Menlo,monospace;
        margin:0; padding:20px 24px; }
 h1 { font:600 13px/1 ui-monospace,monospace; letter-spacing:.18em;
      text-transform:uppercase; color:#6d6656; margin:0 0 18px; }
 .row { display:flex; gap:28px; align-items:flex-start; flex-wrap:wrap; }
 figure { margin:0; }
 figcaption { color:#6d6656; margin-top:8px; letter-spacing:.1em;
              text-transform:uppercase; font-size:10px; }
 img { image-rendering:pixelated; display:block; background:#000;
       outline:1px solid #2a2a2a; }
 aside { min-width:340px; flex:1; }
 label { display:flex; justify-content:space-between; gap:10px; padding:2px 0;
         align-items:center; }
 label span { color:#7d7666; }
 input { background:#1b1b1b; border:1px solid #333; color:#cfc7b4;
         font:12px ui-monospace,monospace; padding:3px 6px; width:130px; }
 fieldset { border:1px solid #2a2a2a; padding:10px 14px; margin:0 0 14px; }
 legend { color:#6d6656; letter-spacing:.14em; text-transform:uppercase;
          font-size:10px; padding:0 6px; }
 textarea { width:100%; height:150px; background:#1b1b1b; border:1px solid #333;
            color:#9a9384; font:11px ui-monospace,monospace; padding:8px; }
 button, select { background:#232323; color:#cfc7b4; border:1px solid #3a3a3a;
                  font:12px ui-monospace,monospace; padding:4px 10px; }
 .status { color:#6d6656; margin-top:14px; font-size:11px; }
</style>
<h1>ambient-display &middot; 128&times;128</h1>
<div class="row">
  <figure><img id="live1" width="128" height="128"><figcaption>live 1&times;</figcaption></figure>
  <figure><img id="live4" width="512" height="512"><figcaption>live 4&times;</figcaption></figure>
  <figure><img id="still" width="512" height="512"><figcaption id="stillcap">still 4&times;</figcaption></figure>
  <aside>
    <fieldset><legend>card</legend>
      <select id="card"></select>
      <button id="reload">reload</button>
    </fieldset>
    <fieldset><legend>type</legend><div id="controls"></div></fieldset>
    <fieldset><legend>theme block for config.json</legend>
      <textarea id="out" readonly></textarea>
    </fieldset>
    <div class="status" id="status"></div>
  </aside>
</div>
<script>
const KEYS = ["family","head_sizes","head_max_lines","head_leading","sci_size",
 "place_size","remark_size","remark_max_lines","bus_size","bus_tracking",
 "margin_x","margin_y","vertical_bias","gap_bus_head","gap_head_sci",
 "gap_sci_rule","gap_rule_place","gap_place_remark","rule_width","max_channel",
 "ink_head","ink_sci","ink_place","ink_remark","ink_rule","ink_bus"];
let base = {}, families = [];

function overrides() {
  const o = {};
  for (const k of KEYS) {
    const el = document.getElementById("f_" + k);
    if (!el) continue;
    const v = el.value.trim();
    if (v !== "" && v !== String(base[k])) o[k] = v;
  }
  return o;
}
function stillURL(scale) {
  const p = new URLSearchParams(overrides());
  p.set("card", document.getElementById("card").value);
  p.set("scale", scale);
  p.set("t", Date.now());
  return "/still.png?" + p.toString();
}
function refreshStill() {
  document.getElementById("still").src = stillURL(4);
  const o = overrides();
  document.getElementById("out").value = Object.keys(o).length
    ? JSON.stringify({theme: o}, null, 2) : "{}";
}
function buildControls() {
  const box = document.getElementById("controls");
  box.innerHTML = "";
  for (const k of KEYS) {
    if (!(k in base)) continue;
    const row = document.createElement("label");
    const name = document.createElement("span"); name.textContent = k;
    let input;
    if (k === "family") {
      input = document.createElement("select");
      for (const f of families) {
        const opt = document.createElement("option");
        opt.value = opt.textContent = f;
        if (f === base[k]) opt.selected = true;
        input.appendChild(opt);
      }
    } else {
      input = document.createElement("input");
      input.value = Array.isArray(base[k]) ? base[k].join(",") : base[k];
    }
    input.id = "f_" + k;
    input.addEventListener("change", refreshStill);
    row.append(name, input);
    box.appendChild(row);
  }
}
async function load() {
  base = await (await fetch("/theme.json")).json();
  families = await (await fetch("/families.json")).json();
  const cards = await (await fetch("/cards.json")).json();
  const sel = document.getElementById("card");
  const keep = sel.value;
  sel.innerHTML = "";
  cards.forEach((c, i) => {
    const opt = document.createElement("option");
    opt.value = i; opt.textContent = c.bus + " · " + c.title;
    sel.appendChild(opt);
  });
  if (keep) sel.value = keep;
  sel.onchange = refreshStill;
  buildControls();
  refreshStill();
}
document.getElementById("reload").onclick = load;
setInterval(() => {
  const t = Date.now();
  document.getElementById("live1").src = "/frame.png?t=" + t;
  document.getElementById("live4").src = "/frame@4x.png?t=" + t;
}, 1000);
setInterval(async () => {
  const s = await (await fetch("/status.json")).json();
  document.getElementById("status").textContent =
    "mqtt " + (s.connected ? "connected" : "offline") + " · " + s.broker +
    " · cards " + s.cards + " · brightness " + s.brightness.toFixed(2) +
    " · offset " + s.offset.map(v => v.toFixed(1)).join(",");
}, 2000);
load();
</script>
"""


def _png(image, scale=1):
    scale = max(1, min(16, int(scale)))
    if scale > 1:
        image = image.resize((image.width * scale, image.height * scale),
                             Image.NEAREST)
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return Response(buf.getvalue(), mimetype="image/png",
                    headers={"Cache-Control": "no-store, max-age=0"})


def create_app(ctl):
    """`ctl` is the running Display from app.py."""
    app = Flask(__name__)
    app.logger.setLevel(logging.WARNING)

    @app.get("/")
    def index():
        return Response(PAGE, mimetype="text/html")

    @app.get("/frame.png")
    def frame():
        return _png(ctl.live_frame(), request.args.get("scale", 1, type=int) or 1)

    @app.get("/frame@4x.png")
    def frame4x():
        return _png(ctl.live_frame(), 4)

    @app.get("/still.png")
    def still():
        # No drift, no night fade, theme re-read from disk: what you're
        # actually iterating on.
        overrides = theme_mod.parse_overrides(request.args.items())
        image = ctl.render_still(request.args.get("card", 0, type=int) or 0,
                                 overrides)
        return _png(image, request.args.get("scale", 1, type=int) or 1)

    @app.get("/still@4x.png")
    def still4x():
        overrides = theme_mod.parse_overrides(request.args.items())
        image = ctl.render_still(request.args.get("card", 0, type=int) or 0,
                                 overrides)
        return _png(image, 4)

    @app.get("/cards.json")
    def cards_json():
        return jsonify([
            {"bus": c.bus, "title": c.title, "subtitle": c.subtitle,
             "place": (c.place_variants or [""])[0], "remark": c.remark}
            for c in ctl.cards()
        ])

    @app.get("/theme.json")
    def theme_json():
        return Response(json.dumps(ctl.theme(), indent=2),
                        mimetype="application/json")

    @app.get("/families.json")
    def families_json():
        return jsonify(theme_mod.available_families())

    @app.get("/status.json")
    def status_json():
        return jsonify(ctl.status())

    @app.get("/healthz")
    def healthz():
        return "ok"

    return app
