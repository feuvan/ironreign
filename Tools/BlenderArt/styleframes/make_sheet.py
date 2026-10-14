"""Overview contact sheet of the style frames + the cross-family light-coherence sheet.

    python3 Tools/BlenderArt/styleframes/make_sheet.py <styleframes_dir>

Runs under the system python3 or Blender's python.  Exits non-zero (with a message) when no
style frame is found, so ``run_all.sh`` reports a broken run.

``styleframes_coherence.png`` composites the city sprite and two forest hexes onto the map crop and
puts the portrait into the parchment panel next to the button: every family must share one sun
(top-left, shadows falling to the bottom-right at the same length) and one palette.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from ironart import post  # noqa: E402

FRAMES = [("sf_terrain_512x320.png", "(a) terrain 512x320", 1),
          ("sf_city_96.png", "(b) city 96x96 (x2)", 2),
          ("sf_hex_forest_128x111.png", "(c) hex 128x111 (x2)", 2),
          ("sf_portrait_192x240.png", "(d) portrait 192x240", 1),
          ("sf_button_192x64.png", "(e) button 192x64 (x2)", 2),
          ("sf_panel_128.png", "(e) panel 128 (x2)", 2)]


EXTRAS = [("sf_city_1_96.png", "City_1 town (x2)", 2),
          ("sf_city_3_96.png", "City_3 great city (x2)", 2),
          ("arch_scholar_192x240.png", "archetype: scholar (preview)", 1),
          ("arch_female_192x240.png", "archetype: female (preview)", 1)]


def _load(d, name):
    p = os.path.join(d, name)
    return post.load(p) if os.path.exists(p) else None


def coherence(d):
    """Map crop with the city and hexes placed on it + portrait/UI strip (1x, then shown x2)."""
    terr = _load(d, "sf_terrain_512x320.png")
    city = _load(d, "sf_city_96.png")
    hexf = _load(d, "sf_hex_forest_128x111.png")
    if terr is None or city is None:
        return None
    board = terr.copy()
    # the runtime draws City_2 at 58 px (SIronMapView CityIconSize) - show both 1:1 and 58 px
    board = post.paste(board, city, 150, 150)
    small = post.resize(city, (58, 58))
    board = post.paste(board, small, 300, 180)
    if hexf is not None:
        board = post.paste(board, hexf, 20, 205)
        board = post.paste(board, hexf, 20 + 96, 205 + 56)
    items = [(board, "coherence: city 96 + 58 px and forest hexes on the map crop")]
    port = _load(d, "sf_portrait_192x240.png")
    panel = _load(d, "sf_panel_128.png")
    button = _load(d, "sf_button_192x64.png")
    if port is not None and panel is not None:
        frame = post.nine_slice(panel, (24, 24, 24, 24), (240, 288))
        frame = post.paste(frame, port, 24, 24)
        strip = post.solid(512, 300, "Night")
        strip = post.paste(strip, frame, 8, 6)
        if button is not None:
            strip = post.paste(strip, button, 270, 40)
            strip = post.paste(strip, post.nine_slice(button, (20, 16, 20, 16), (220, 56)), 270, 120)
        items.append((strip, "portrait in Panel 9-slice, buttons, on Night"))
    return post.contact_sheet(items, cols=1, scale=2)


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.environ.get("IRONART_OUT", "/tmp/ironart"), "styleframes")
    items = []
    for name, label, scale in FRAMES:
        img = _load(d, name)
        if img is not None:
            if scale != 1:
                img = post.resize(img, (img.shape[1] * scale, img.shape[0] * scale), "nearest")
            items.append((img, label))
    if not items:
        print("[make_sheet] ERROR: no style frames found in %s" % d, file=sys.stderr)
        sys.exit(1)
    # optional extras: the city tiers and the portrait archetypes (1:1)
    for name, label, scale in EXTRAS:
        img = _load(d, name)
        if img is not None:
            if scale != 1:
                img = post.resize(img, (img.shape[1] * scale, img.shape[0] * scale), "nearest")
            items.append((img, label))
    out = os.path.join(d, "styleframes_overview.png")
    post.save(post.contact_sheet(items, cols=3), out)
    print("[make_sheet] wrote", out, "(%d frames)" % len(items))
    coh = coherence(d)
    if coh is not None:
        p = os.path.join(d, "styleframes_coherence.png")
        post.save(coh, p)
        print("[make_sheet] wrote", p)
    if len(items) < len(FRAMES):
        missing = [n for n, _, _ in FRAMES if not os.path.exists(os.path.join(d, n))]
        print("[make_sheet] ERROR: missing frames: %s" % ", ".join(missing), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
