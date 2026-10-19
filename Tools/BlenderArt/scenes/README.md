# Illustrated Scenes family (gongbi)

Title background, the 12 event illustrations and the duel background, painted as **gongbi
ink-and-colour on silk** (工笔重彩, 界画 for architecture, 青绿山水 for landscape).  Every picture is
built as a 3D scene in Blender and rendered as a painting; nothing is downloaded or hand-drawn.

```
Tools/BlenderArt/render.sh Tools/BlenderArt/scenes/build.py                     # everything (final)
Tools/BlenderArt/render.sh Tools/BlenderArt/scenes/build.py --only Court        # one scene
Tools/BlenderArt/render.sh Tools/BlenderArt/scenes/build.py --only Title --preview 0.5 --no-save
Tools/BlenderArt/render.sh Tools/BlenderArt/scenes/build.py --only Title --region 0.4,0.1,0.9,0.6 --no-save
Tools/BlenderArt/render.sh Tools/BlenderArt/scenes/build.py --only Court --no-save --reuse   # re-composite only
python3 Tools/BlenderArt/scenes/make_sheet.py $IRONART_OUT/scenes/preview       # contact sheet
```

| Output | Size | Master (ArtSource) |
|---|---|---|
| `Content/Data/Art/UI/Title_Background.png` | 1920x1080 | `UI/Title_Background@2x.png` 3840x2160 |
| `Content/Data/Art/Events/<Name>.png` (12) | 640x360 | `Events/<Name>@2x.png` 1280x720 |
| `Content/Data/Art/Duel/Background.png` | 1280x720 | `Duel/Background@2x.png` 2560x1440 |

## How a scene becomes a painting

1. **Build** (`sc_<name>.py: build(r)`): geometry in metres with the family kit -
   `ironart/scenes_gongbi_land.py` (青绿 mountain heightfields on a camera-centred polar grid,
   rib coordinates for 披麻皴, rocks, boulders, pinnacles, water, ground, clouds),
   `ironart/scenes_gongbi_flora.py` (pines with needle fans, broadleaf canopies with 点叶 dots,
   willows, bamboo, crab-claw dead trees, plum, grass), `ironart/scenes_people.py` (posed,
   dressed figures, horses, riders) and the World Models architecture kit
   (`ironart/world_kit.py`, `ironart/world_city.py`) through `ironart/scenes_gongbi_kit.py`
   (city tiers, banners, cottages, figure placement, `ScreenMap` - composition authored in
   screen space).  Objects go into one collection per ink kind.
2. **Materials** (`ironart/scenes_gongbi.py`): emission-only mineral washes (DESIGN.md palette),
   graded towards the outlines (分染 / 晕染), a very gentle painter's light, no lights, no
   shadows, no speculars.  Texture strokes are written into the `gb_ink` AOV (皴, moss dots,
   pine needles, wave lines, lattice, armour lamellae, coffers...), bare silk into `gb_bare`.
3. **Ink** (image space, `ironart/scenes_gongbi_ink.py`): outlines are found in the sample-0
   passes Cycles writes anyway (depth, object / material index, normal) - silhouettes where the
   inverse depth steps, creases where normals turn, boundaries where object or material changes -
   and drawn with a per-kind brush: `arch` ruled even lines (界画), `fig` fine pressure-varied lines,
   `skin` a fine reddish-brown line (赭线), `land` heavier tapered strokes, `tree`, `fine` (thin
   props), `cloud`, `water`.  Widths are in game px, thin out and fade with distance, and carry
   dry-brush breaks.  The same edges drive the 分染 band: colour deepens towards every outline inside
   each form.  (Freestyle took ~85 % of the render time and is no longer used; a scene can still ask
   for it with `ink_mode="freestyle"`.)
4. **Render**: Cycles CPU, Standard view, film transparent, 6-12 spp at 4x the game size for
   events (2x for Title / Duel); passes to EXR.
5. **Composite** (numpy): sky wash, painted 2D motifs (`ironart/scenes_gongbi_2d.py`: moon left
   as bare silk, sun disc, comet, fireworks, petals, rain, locust swarm, glows), distance fade to
   paler washes, mist bands of bare silk (noisy or 祥云 scalloped with an ink edge), shoreline
   ink, ink with a hint of bleed and dry-brush breaks, pigment granulation and edge pooling, the
   aged silk ground (weft / warp threads, slubs, mottling, darker edges), a touch of age.
6. **Save**: master (Lanczos from the render), game size (Lanczos + light unsharp) through
   `post.save_asset`; masters are added to `ArtSource/manifest.json`.

`scenes/legacy_cg/` holds the previous (photographic CG) scene scripts for reference only; they
are not part of the build.
