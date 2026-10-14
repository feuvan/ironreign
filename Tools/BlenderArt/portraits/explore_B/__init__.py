"""Explore approach B - "painterly shading in the renderer".

MakeHuman (CC0) anatomy, art-directed Cycles materials and a pass-based painterly compositor.

Run one portrait (Blender 4.0.2, Cycles CPU, headless)::

    blender -b --factory-startup -noaudio -P Tools/BlenderArt/portraits/explore_B/run_portrait.py \\
            -- hero_warlord <out_dir> [--preview]
    Tools/BlenderArt/portraits/explore_B/prev3.sh <out_dir> [--preview]      # the three heroes
    python3 Tools/BlenderArt/portraits/explore_B/make_sheet.py <out_dir>     # 1x / 2x sheets

Modules (data flows top to bottom)

    mh.py         MakeHuman reader: hm08 base mesh, sparse .target morphs, .mhclo proxy fitting,
                  macro weighting (gender x age x muscle x weight x race) - own implementation
    zones.py      per-vertex paint zones on the base mesh (lips/nose/ears/cheeks from the morph
                  targets' displacement magnitude; scalp/beard/moustache/brow/lash analytic)
    identity.py   Identity dataclass (macro values, face sliders, expression units, skin, hair
                  colour, wrinkles/frown/gaunt, painted hair-root masses) + archetype presets
    head.py       morph -> lower the A-pose arms -> crop the bust -> subdivide -> displace real
                  wrinkles (wrinkles.py) -> eyes fitted from the MH high-poly proxy, aimed at camera
    wrinkles.py   geometric creases (forehead, glabella, crow's feet, tear trough, nasolabial,
                  marionette, neck) as a height field over the rest positions
    hair.py       strand grooms on the evaluated skin: beard, moustache, brows, lashes, hair combed
                  to a top-knot, wound buns, side locks; clumping, collisions (BVH), Principled Hair
    costume.py    garment shells offset from the body, lamellar plates by ray casting, pauldron lames,
                  helmets (bowl, ribs, rim, plaque, finial, lamellar neck guard), ribbons/collars,
                  chest mirror, beads, crowns, hairpins, flowers, bead dangles
    outfits.py    outfit builders: ``warlord_armour`` and layered ``robe`` (crossed collars,
                  beads, crown or hairpins) - options switch helmets, fur, tassels, palettes
    shading.py    the painterly materials: skin colour zones, analytic painted brows, key-relative
                  warm terminator / cool shadow tint, controlled specular, painter's catchlight,
                  laced iron plates with gold inlay, brocade silk with embroidered borders,
                  hand-painted stroke variation; AOVs skin/hair/costume/eye/accent
    rig.py        camera (85 mm, eyes at 38 %), five-light rig with one light group per light
    compositor.py relight from passes: diffuse light value-grouped by a curve (planar painted
                  read), tinted by value, specular shaped, rim emphasised; over the painted ground;
                  three anisotropic Kuwahara scales chosen per region (costume/hair at half res);
                  eyes kept clean; ink accents from the 'accent' AOV
    background.py painted umber ground with a key-side glow and brush strokes (numpy + Pillow)
    finish.py     brush-texture overlay (darks / costume), painted-out bottom edge, grade,
                  Lanczos to 384x480 and 192x240, masked unsharp on the eyes
    specs.py      the three hero specs;  catalog.py: id + scenario officer -> spec for all 102 ids
"""
