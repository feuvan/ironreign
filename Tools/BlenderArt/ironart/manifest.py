"""The DESIGN.md section 8 asset manifest as data (no bpy; system python3 works).

Every final asset script saves through :func:`ironart.post.save_asset`, which calls
:func:`validate` - so a wrong size, a missing alpha channel or a sprite clipped at the canvas edge
fails the script instead of reaching the UI.  ``Tools/BlenderArt/check_art.py`` runs the same
checks over ``Content/Data/Art`` (and :func:`cross_check_design` keeps this table in sync with the
markdown).

Entry fields
    size          (w, h) exact pixel size
    transparent   True: RGBA with real alpha.  False: opaque (saved RGBA with alpha 255)
    clear_border  True: alpha must be 0 on the outer 1 px ring (sprites placed on the map/board)
    tint          'white' (runtime multiplies by the faction colour: R = G = B in the tint mask),
                  'mask' (pure white shape), or None
    family        recipe family in :mod:`ironart.recipes`
"""

import os
import re

HEX_TERRAINS = ("Plain", "Forest", "Hill", "Mountain", "Water", "Ford", "Bridge", "Road", "Wall",
                "Gate", "Town", "Castle", "Rubble")
ICONS = ("Farm", "Commerce", "Walls", "Patrol", "Draft", "Train", "Search", "Recruit", "Move",
         "Transport", "SectTraining", "Alliance", "Truce", "Gift", "March", "Market", "Tavern",
         "Officers", "Factions", "Save", "Load", "EndTurn", "Gold", "Food", "Troops", "Population",
         "Order", "Defense", "Training", "Loyalty", "Settings", "Delegate", "Prisoner", "Fire",
         "Confuse", "Rally", "Duel", "Attack", "Wait", "Undo")
EVENTS = ("Court", "Battle", "Harvest", "Disaster", "Wanderer", "Sect", "Bandits", "Envoy",
          "Festival", "Plague", "Flood", "Omen")
PORTRAIT_SETS = (("m_warrior", 30), ("m_scholar", 20), ("m_elder", 12), ("m_monk", 6),
                 ("m_rogue", 10), ("f_warrior", 10), ("f_scholar", 10), ("f_elder", 4))


def _e(size, transparent, family, clear_border=False, tint=None):
    return {"size": tuple(size), "transparent": transparent, "clear_border": clear_border,
            "tint": tint, "family": family}


def _build():
    m = {
        "Art/Map/WorldMap.png": _e((2400, 1500), False, "map"),
        "Art/Map/Banner.png": _e((64, 96), True, "tint_plate", True, "white"),
        "Art/Map/Sect.png": _e((64, 64), True, "sprite", True),
        "Art/Map/Flag.png": _e((32, 48), True, "tint_plate", True, "white"),
        "Art/Battle/Hex_Fill.png": _e((128, 111), True, "mask", False, "mask"),
        "Art/Battle/Hex_Outline.png": _e((128, 111), True, "mask", False, "mask"),
        "Art/Battle/Unit_Base.png": _e((96, 96), True, "tint_plate", True, "white"),
        "Art/Battle/Background.png": _e((1920, 1080), False, "background"),
        "Art/UI/Panel.png": _e((128, 128), True, "ui"),
        "Art/UI/PanelDark.png": _e((128, 128), True, "ui"),
        "Art/UI/Frame_Portrait.png": _e((212, 260), True, "ui"),
        "Art/UI/Title_Background.png": _e((1920, 1080), False, "background"),
        "Art/UI/Title_Logo.png": _e((1200, 400), True, "ui"),
        "Art/UI/Seal.png": _e((128, 128), True, "ui"),
        "Art/UI/Scroll.png": _e((1024, 640), True, "ui"),
        "Art/UI/Divider.png": _e((512, 16), True, "ui"),
        "Art/Duel/Background.png": _e((1280, 720), False, "background"),
        "Art/Portraits/unknown.png": _e((192, 240), False, "portrait"),
    }
    for i in (1, 2, 3):
        m["Art/Map/City_%d.png" % i] = _e((96, 96), True, "sprite", True)
    for t in HEX_TERRAINS:
        m["Art/Battle/Hex_%s.png" % t] = _e((128, 111), True, "hex")
    for u in ("Infantry", "Cavalry", "Archer"):
        m["Art/Battle/Unit_%s.png" % u] = _e((96, 96), True, "sprite", True, "white")
    for fx in ("Fire", "Confuse", "Rally", "Hit"):
        m["Art/Battle/Fx_%s.png" % fx] = _e((96, 96), True, "fx", True)
    for b in ("Button", "Button_Hover", "Button_Pressed", "Button_Disabled"):
        m["Art/UI/%s.png" % b] = _e((192, 64), True, "ui")
    for t in ("Tab", "Tab_Active"):
        m["Art/UI/%s.png" % t] = _e((160, 48), True, "ui")
    for ic in ICONS:
        m["Art/UI/Icon_%s.png" % ic] = _e((64, 64), True, "icon", True)
    for ev in EVENTS:
        m["Art/Events/%s.png" % ev] = _e((640, 360), False, "event")
    for prefix, n in PORTRAIT_SETS:
        for i in range(1, n + 1):
            m["Art/Portraits/%s_%02d.png" % (prefix, i)] = _e((192, 240), False, "portrait")
    return m


#: path (relative to Content/Data) -> entry
MANIFEST = _build()


def entry(rel_path):
    rel = rel_path.replace("\\", "/")
    if rel not in MANIFEST:
        raise KeyError("%s is not in the DESIGN.md section 8 manifest" % rel_path)
    return MANIFEST[rel]


def validate(img, rel_path):
    """Check an RGBA float image (H x W x 4) against the manifest. Returns the entry or raises."""
    e = entry(rel_path)
    h, w = img.shape[:2]
    errors = []
    if (w, h) != e["size"]:
        errors.append("size %dx%d != %dx%d" % (w, h, e["size"][0], e["size"][1]))
    if img.ndim != 3 or img.shape[2] != 4:
        errors.append("not RGBA")
    elif e["transparent"]:
        a = img[..., 3]
        if a.min() > 0.999:
            errors.append("transparent asset has no transparent pixels")
        if e["clear_border"]:
            ring = max(a[0].max(), a[-1].max(), a[:, 0].max(), a[:, -1].max())
            if ring > 0.0:
                errors.append("alpha %.3f on the outer 1 px ring (clipped sprite/shadow)" % ring)
    if errors:
        raise ValueError("%s: %s" % (rel_path, "; ".join(errors)))
    return e


def cross_check_design(design_md):
    """Compare sizes in docs/DESIGN.md section 8 with :data:`MANIFEST`. Returns a list of
    problems (empty = in sync)."""
    text = open(design_md, encoding="utf-8").read()
    sec = text[text.index("## 8."):text.index("## 9.")]
    problems = []
    for line in sec.splitlines():
        mm = re.match(r"\|\s*(`Art/[^|]+)\|\s*(\d+)x(\d+)\s*\|", line)
        if not mm:
            continue
        size = (int(mm.group(2)), int(mm.group(3)))
        for p in re.findall(r"`([^`]+\.png)`", mm.group(1)):
            if "<" in p:
                continue
            path = p if p.startswith("Art/") else os.path.dirname(
                re.findall(r"`(Art/[^`]+)`", mm.group(1))[0]) + "/" + p
            e = MANIFEST.get(path)
            if e is None:
                problems.append("%s in DESIGN.md but not in manifest.py" % path)
            elif e["size"] != size:
                problems.append("%s size %s in DESIGN.md vs %s" % (path, size, e["size"]))
    return problems
