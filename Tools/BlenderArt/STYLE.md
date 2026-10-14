# Iron Reign art pipeline: Blender style guide

This guide covers the Blender pipeline in `Tools/BlenderArt/` that every artist uses to regenerate
the game art listed in `docs/DESIGN.md` section 8. That manifest is a hard contract with the UI
code: keep the same paths, the same pixel sizes, transparency and the white-cloth tint rules
(`ironart/manifest.py` holds it as data and `check_art.py` enforces it).

**Where the numbers live.** Every look number (samples, rigs, ink, Kuwahara, grade, paper,
margins, anchors) lives once, in `ironart/recipes.py`. The library defaults equal it, the style
frames call it, and the tables in section 5 and section 7 are generated from it
(`recipes.update_style_md()`). Every other number in this guide was **measured** on the style
frames of the last full run (`styleframes/run_all.sh`), and most of them are asserted by those
frames, so a change that breaks the look fails the run.

## 1. The look

Painterly non-photorealistic rendering over real 3D, in the style of Koei games of 1998-2004
(Romance of the Three Kingdoms IX and Taiko Risshiden IV).

| Family | What it must read as |
|---|---|
| World map | A painted 3D relief map seen from above. Sage plains (hue 75-85), ochre foothills, sandy steppe, one continuous blue-grey range with snow along the crests, forests as lobed clusters of tiny trees plus small copses, clear blue rivers widening to the sea, a beach strip, bright coastal shallows and a deep teal-indigo sea. A thin ink line runs along the coast. |
| Cities and buildings | Small 3D Chinese walled cities in a 3/4 top-down view. Low grey stone walls with a light coping, a gate tower with red-lacquer doors in front, a keep on a tall podium behind (the roofs step up front to back), dark teal-grey tile roofs with upturned eaves, trees in the courtyard. Three clear values: tops, west faces, south faces. |
| Portraits | Dramatic painted realism. A warm key from the upper left at 35 deg (Rembrandt triangle on the shadow cheek), a cool fill, a warm bounce and a cool rim on an umber paper ground. Eyes look at the viewer with a catchlight. Rich but muted armour and silk, a red/cream collar as the colour accent. Fine brushwork on the face, big directional strokes on armour and ground. |
| UI | Lacquered dark wood and red lacquer, bevelled gold trim lit from the top-left, gold corner fittings, warm parchment, ink lines and red seals. |

Rules that apply everywhere:

- One sun: the light comes from the top-left of the screen (screen angle 135 deg) and shadows
  fall to the bottom-right (section 4).
- Use no neon or photographic colours. Build colours from the palette in section 7.
- Cycles handles form and light. Kuwahara compositing, paper grain and controlled saturation add
  the paint.
- Freestyle ink lines are selective: sprites and UI yes, canopy silhouettes on hex tiles, the map
  only as a 2D coast line, never on faces.

## 2. Pipeline

```
build (MeshBuilder / geometry.walled_city / figure.bust / terrain)
  -> r = recipes.setup(family, w, h)          Cycles CPU, colour management, ss x target size
  -> recipes.camera / recipes.frame           exact pixel framing, margins, ground anchor
  -> recipes.light                            the family rig (one sun, section 4)
  -> recipes.ink                              Freestyle brush ink as a separate pass
  -> recipes.paint                            compositor: [background] -> straight-alpha
                                              anisotropic Kuwahara -> mix -> ink over
  -> scene.render(raw)                        asserts Cycles/CPU/no denoise/Standard|Filmic
  -> img = recipes.finish(family, raw)        Lanczos downsample (premultiplied) -> grade ->
                                              unsharp -> paper -> vignette -> [neutralize]
                                              -> contact shadow -> alpha clean-up / hex mask
  -> post.QA(...) asserts                     measured values against the targets below
  -> post.save_asset(img, "Art/...png")       validates size/mode/border against the manifest,
                                              writes 8-bit RGBA (opaque assets get alpha 255)
```

Run every script through the wrapper. It runs Blender at `nice 10` with the same flags every
time, filters Blender's log noise, reports timing and exits non-zero on any Python exception or
crash:

```
Tools/BlenderArt/render.sh <script.py> [args...]
IRONART_OUT=/tmp/x Tools/BlenderArt/styleframes/run_all.sh    # all frames, sheets, timings
python3 Tools/BlenderArt/check_art.py [--strict]               # committed art vs the manifest
```

`run_all.sh` exits non-zero if any frame, any QA assert or the sheet builder fails.

| Variable | Effect |
|---|---|
| `IRONART_OUT` | Scratch root. The default is `/tmp/ironart`. |
| `IRONART_THREADS` | Fixed Cycles thread count. |
| `IRONART_NICE` | Scheduling niceness (default 10; the 4 cores are shared). |
| `IRONART_VERBOSE=1` | Shows Blender's per-sample log. |
| `IRONART_LOG=file` | Appends the full log to `file`. |

Scripts write intermediates such as `*_raw_Nx.png` to `$IRONART_OUT/...`. Only final PNGs go to
`Content/Data/Art/...`, through `post.save_asset`. Never commit the raw renders.

### Facts about this machine's Blender build (Blender 4.0.2, Ubuntu package)

- **Rendering:** only **Cycles on CPU** works; EEVEE and Workbench crash headless. The factory
  state is EEVEE, so `scene.reset()` switches to Cycles and `scene.render()` refuses anything
  else. **OpenImageDenoise is not available**; denoising stays off (supersampling, adaptive
  sampling, `clamp_indirect=4`, and the Kuwahara pass absorbs the rest).
- **Colour management:** `Standard`, `Filmic`, `AgX` and `Raw` exist (the enum lists `NONE`
  headless, but setting by name works). Studio views are `Standard` and `Filmic` only, and
  `scene.set_color_management` rejects a look that does not belong to the view (Blender silently
  accepts a Filmic look on Standard).
- **Freestyle:** the factory line set has no line style and segfaults; `scene.reset()` removes it
  and `ink.enable()` always creates fresh styles. Freestyle's Python also crashes on open edges of
  smooth-shaded meshes; `ink._patch_freestyle()` patches the two thickness setters and refuses to
  run on any Blender other than 4.0. The harmless `Error: strokes set empty` is filtered.
- **Shader nodes:** Shader to RGB is EEVEE-only (the "paint" banding uses the Toon BSDF). Some
  sockets differ from their names (Hair BSDF `Random Color`): use `materials.sock()`. The AOV
  Output node's AOV name is a second RNA property called `name` that shadows `Node.name`
  (`materials.white_cloth` handles it).
- **Hair:** 4.x `Curves` datablocks (`geometry.hair_curves`), not particle systems.
- **Compositor:** Kuwahara (classic and anisotropic), Inpaint, Premul Key, Set Alpha, ID Mask,
  Color Balance, Bilateral Blur all work on CPU. The Kuwahara node filters alpha too: on
  transparent renders `comp_painterly` runs it on straight colour extended past the silhouette
  (Premul Key -> Inpaint -> Kuwahara -> Set Alpha) so silhouettes and edge colours stay exact.

## 3. Units, cameras, framing

| Family | Scene scale | Camera | Framing rule |
|---|---|---|---|
| World map | 1 target px = 1 cm | `ortho_top_down`, screen-up = north | full frame; relief 0.55 m per unit height on the ranges, lowlands at 0.42 m |
| City, sect, unit, banner, icon sprites | 1 m (a walled city is 6.4 x 5.6 m) | `sprite_camera(elevation 35, azimuth -20)`, ortho | `recipes.frame`: margins (l, t, r, b) = (2, 2, 6, 6) target px, ground centre on (0.5, 0.70) of the canvas |
| Hex tiles | r = 1 m (64 px/m) | `ortho_top_down(width=2.0)` | strictly top-down, mask cut by `post.hex_mask` |
| UI 9-slices, frames, seals | 1 target px = 1 mm | `ortho_top_down(width=px(W), height=px(H))` | slabs built by profile sweeps |
| Portraits | 1 m (head 0.232 m chin to crown) | `portrait_camera(85 mm, yaw 20, pitch -4)` | eyes at 38 % from the top, head 48 % of the frame height, headwear >= 6 px below the top edge, `center_on` head + gear |

- `cameras.fit_ortho(cam, objs, margin_px, anchor, anchor_world, anchor_px, units_per_px)`
  frames the evaluated vertices exactly; margins may be one number or a (l, t, r, b) tuple.
- **City_1..3 are fitted independently**, each filling its 96 px canvas: the UI already draws
  them at 46 / 58 / 74 px (`SIronMapView` CityIconSize), so a shared scale would shrink a town
  twice. Share `units_per_px` only inside families the UI draws at one size (Unit_* over
  Unit_Base).
- `cameras.world_to_target_px(cam, co)` / `cameras.target_rect(cam, corners)` give **target**
  pixels (render pixels divided by the supersample factor) for anything written into the game.

## 4. Light: one sun

Every rig places its lights in **screen space** (`lights.screen_dir(cam, angle, elevation)`:
angle counter-clockwise from screen-right, elevation towards the viewer). `lights.SUN` is the
studio sun; every rig default below equals the recipe.

| Family | Key | Fill / bounce | Rim | Ambient |
|---|---|---|---|---|
| Map (`rig_map`) | sun 3.4, screen 135 / 50, `#FFF7EC`, 16 deg soft | - | - | sky `#AEB4B8` x 0.55 |
| Hex (`rig_map`) | as the map, 45 % of the key cast without shadows (`shadow_lift 0.45`) | - | - | sky x 0.6 |
| Sprites (`rig_sprite`) | sun 4.6, screen 155 / 52 (world elevation 40 from WSW: the oblique camera needs it to split the planes), 6 deg soft, 20 % without shadows | sun 0.25, -30 / 35, `#B8C8E0`; shadowless zenith 0.45 | sun 1.2, 60 / -35 | sky x 0.18 |
| Portraits (`rig_portrait`) | area 0.5 m, 40 W at 1.6 m, screen 135 / 35, `#FFEBD2` | area 1.6 m 12 W, -15 / 25, cool, no shadow; warm bounce 0.8 m 9 W `#C89060` from below (-90 / -20) | area 0.5 x 1.2 m, 26 W, 40 / -45 | `#3A3530` x 0.04 |
| UI (`rig_ui`) | sun 135 / 50, **white**, strength solved so a flat face-up surface renders at 1.0 x albedo | - | - | uniform white 0.2 (diffuse); glossy rays see a studio ring, bright at the horizon and dark at the zenith |

Shadows fall towards screen 315 deg (bottom-right) everywhere. On the map and the hex tiles they
are about 0.84 x the object height long (tan 50); the composited sprite contact shadow uses the
matching (2.2, 2.2) px offset. `styleframes_coherence.png` composites the city and two forest hexes
on the map crop and the portrait into the parchment panel as the coherence check.

**Measured on the style frames** (8-bit, final images):

| Frame | Measured | Asserted target |
|---|---|---|
| Map | open plains mean `#91A367`, hue 77.7; steppe (203, 176, 119); lit canopy luma 108, hue 88; shadow canopy luma 56; snow 4.9 % of the range; near-navy (< 60) 0.3 % | plains hue 75-85; steppe within 14 of `#C7AC76`; lit canopy 80-125, hue 80-115; shadow canopy 30-70; snow 3-6 %; navy <= 3 %; every river reaches the sea |
| City_2 | wall tops 196, west faces 141, south faces 102; roof lit / shadow slope 130 / 70 (1.85 x); courtyard p10 102; west face in cast shadow p10 61 | 178-205 / 135-165 / 92-118; 105-140 / 45-75 (1.6-3.0 x; City_1 45-90, >= 1.4); >= 58; >= 50 |
| Hex forest | ground gap floor p5 v 0.26; canopy shadow p5 v 0.20; lit vs shadow canopy hue swing 9.8 deg; seam band - interior luma -2.0 | v >= 0.22; v >= 0.18; <= 15 deg; within +-8 |
| Portrait | mean luma 65.5; background 67; lit / shadow cheek 138 / 98 (0.71); armour midtones 65; top margin 15 px; catchlights 199 / 186 | 65-80; 45-70; >= 0.35; 55-95; >= 6 px; >= 120 |
| UI | button field (125, 31, 23) vs Lacquer (126, 31, 23); panel field (233, 220, 192) vs Paper (233, 220, 192); 9-slice border row / column std 1.4 / 1.3 (button), 0.8 / 0.9 (panel); field mottling 0.7 | within 3 levels per channel; std <= 2; mottling <= 4 |

East and north faces are not visible from the sprite camera (azimuth -20), so they are not
measured. The sprite key sits at screen 155 / 52 rather than 135: measured at 145 / 48 the planes
collapse (west 138, south 90, roof shadow 80), so 155 / 52 is the closest angle that keeps the
three values apart; its shadows still fall to the bottom-right. The UI rig is white on purpose:
a warm key shifted Paper to (238, 215, 175), 17 levels short in blue, and a luminance-only
compensation cannot correct hue.

## 5. Recipes (generated from `ironart/recipes.py`)

Kuwahara `size` and ink `thickness_px` are in **target** pixels: the helpers multiply them by the
supersample factor, so a `--preview` render paints at the same scale as the final. Grades are
single values, never ranges.

<!-- BEGIN recipes -->
| Family | Supersample | Samples | Preset | View / look | Alpha | Camera |
|---|---|---|---|---|---|---|
| map | 2x | 40 | map | Standard / None | opaque | top |
| sprite | 4x | 64 | sprite | Standard / None | cleanup | sprite elevation_deg 35, azimuth_deg -20 |
| tint_plate | 4x | 64 | sprite | Standard / None | cleanup | sprite elevation_deg 35, azimuth_deg -20 |
| hex | 4x | 48 | sprite | Standard / None | hex | top width 2 |
| portrait | 2x | 56 | portrait | Filmic / Medium Contrast | opaque | portrait head_height 0.232, yaw_deg 20, pitch_deg -4, eye_line 0.38, head_frac 0.48 |
| ui | 4x | 48 | ui | Standard / None | cleanup | top |
| icon | 4x | 48 | sprite | Standard / None | cleanup | sprite elevation_deg 35, azimuth_deg -20 |
| fx | 4x | 32 | fast | Standard / None | straight | top |
| event | 2x | 48 | map | Filmic / Medium Contrast | opaque | persp focal_mm 35 |
| background | 2x | 48 | map | Filmic / Medium Contrast | opaque | persp focal_mm 35 |

| Family | Light rig | Ink (target px) |
|---|---|---|
| map | rig_map(key 3.4, sky 0.55, elevation_deg 50, softness_deg 16) | - |
| sprite | rig_sprite(key 4.6, fill 0.25, rim 1.2, sky 0.18, key_angle 155, key_elev 52, top_fill 0.45, shadow_lift 0.2) | thickness_px 0.9, alpha 1, inner_scale 0.5, inner_alpha 0.5, crease_angle 125, calligraphy 0.3, pressure_noise 0.15 |
| tint_plate | rig_sprite(key 4.6, fill 0.25, rim 1.2, sky 0.18, key_angle 155, key_elev 52, top_fill 0.45, shadow_lift 0.2, neutral True) | thickness_px 0.9, alpha 1, inner_scale 0.5, inner_alpha 0.5, crease_angle 125, calligraphy 0.3, pressure_noise 0.15 |
| hex | rig_map(key 3.4, sky 0.6, elevation_deg 50, softness_deg 16, shadow_lift 0.45) | thickness_px 0.8, alpha 0.6, inner_scale 0, outer_select contour, calligraphy 0.3, pressure_noise 0.2, crease False |
| portrait | rig_portrait(key 40, fill 12, bounce 9, rim 26, key_elev 35) | - |
| ui | rig_ui(flat_gain 1, ambient 0.2, warm False) | thickness_px 1, inner_scale 0, calligraphy 0, pressure_noise 0, taper False, alpha 0.85 |
| icon | rig_sprite(key 4.6, fill 0.25, rim 1.2, sky 0.18, key_angle 155, key_elev 52, top_fill 0.45, shadow_lift 0.2) | thickness_px 0.75, alpha 1, inner_scale 0.5, inner_alpha 0.5, calligraphy 0.4, pressure_noise 0.2 |
| fx | none (emission) | - |
| event | rig_map(key 3.4, sky 0.55, elevation_deg 35, softness_deg 16) | thickness_px 1.6, alpha 0.8, inner_scale 0.5, inner_alpha 0.5 |
| background | rig_map(key 3.4, sky 0.55, elevation_deg 35, softness_deg 16) | thickness_px 2, alpha 0.8, inner_scale 0.5, inner_alpha 0.5 |

| Family | Kuwahara (size in target px) | Grade | Paper | Unsharp | Shadow | Margins (l, t, r, b) / anchor |
|---|---|---|---|---|---|---|
| map | size 3.5, sharpness 0.45, eccentricity 1.2, amount 0.75 | saturation 0.98, contrast 1.04, warmth 0 | 0.1 (land only) | - | - | - / - |
| sprite | size 1.5, sharpness 0.7, eccentricity 0.8, amount 0.5 | saturation 0.98, contrast 1.05, warmth 0 | 0 | (0.8, 0.3) | offset (2.2, 2.2), blur_px 1.6, opacity 0.35, depth_px 6, shear 0.15 | (2, 2, 6, 6) / ground centre at (0.5, 0.7) of canvas |
| tint_plate | size 1, sharpness 0.7, eccentricity 0.8, amount 0.4 | saturation 1, contrast 1, warmth 0 | 0 | (0.8, 0.25) | - | (2, 2, 2, 2) / ground centre at (0.5, 0.9) of canvas |
| hex | size 1.5, sharpness 0.5, eccentricity 1.2, amount 0.85 | saturation 1, contrast 1.05, warmth 0 | 0 | - | - | - / - |
| portrait | size 3, sharpness 0.5, eccentricity 2, amount 0.85, detail_index 1, detail_size 1.5, detail_eccentricity 1 | saturation 0.96, contrast 1.02, warmth 0.008 | 0.07 | (0.7, 0.4) | - | - / - |
| ui | - | - | 0 | - | - | - / - |
| icon | size 1, sharpness 0.7, eccentricity 0.8, amount 0.4 | saturation 0.98, contrast 1.06, warmth 0 | 0 | (0.6, 0.35) | - | (4, 4, 4, 4) / center |
| fx | size 1.5, sharpness 0.5, eccentricity 1.5, amount 0.7 | saturation 1, contrast 1, warmth 0 | 0 | - | - | (3, 3, 3, 3) / center |
| event | size 4.5, sharpness 0.45, eccentricity 1.5, amount 0.85 | saturation 0.96, contrast 1.04, warmth 0.008 | 0.08 | - | - | - / - |
| background | size 5, sharpness 0.45, eccentricity 1.5, amount 0.85 | saturation 0.96, contrast 1.04, warmth 0.008 | 0.08 | - | - | - / - |

| Family | Notes |
|---|---|
| map | 1 px = 1 cm, relief 0.55 m per unit height on ranges; coast ink line drawn in numpy (InkSoft, alpha 0.55); paper on land only; render the full map as ONE frame |
| sprite | City_1..3, Sect: each fitted independently to fill its canvas (the UI scales the tiers 46/58/74 px); ground centre at (0.5, 0.70) of the canvas; City pennant keep-out x 56-83, y 0-23 (alpha < 0.1); 1 px border alpha 0 |
| tint_plate | Banner 64x96, Flag 32x48, Unit_Base, white areas of Unit_*: white_cloth (TintMask AOV), neutral rig, post.neutralize(mask), neutral_check(mask) mean <= 1, p99 <= 4; glyph area = cameras.target_rect(banner corners) as 'x y w h'; no drop shadow (the UI composites units over Unit_Base) |
| hex | r = 1 m, top-down; ground painted to 1.12 r and content may cross the hex edge (the mask cuts it) so neighbours meet canopy to canopy; edge density radially uniform; ink on canopy silhouettes only (collection) |
| portrait | 192x240 opaque; figure.bust(archetype); eyes at 38 % from the top aimed at the camera, head 48 % of the frame, headwear >= 6 px from the top; face objects pass_index 1 (fine Kuwahara), rest big directional strokes; umber paper background base (0.20,0.16,0.12) halo (0.46,0.39,0.30); asserted: mean luma 65-80, background 45-70, shadow cheek >= 35 % of the lit cheek, armour 55-95, catchlights |
| ui | 1 px = 1 mm; 9-slice margins: Button 20/16, Tab 20/16, Panel/PanelDark 24, Scroll 80; gold_leaf(uniform=True) and lacquer(vary=0) on edges; QA: field within 3 levels of its token, per-row/column std <= 2 levels in the stretch zones |
| icon | Icon_* 64x64: one prop per icon (sheaf, coin string, wall, scroll...), sprite camera, centred, 4 px margins, no ground shadow, ink 0.75 |
| fx | Fx_* 96x96 overlays: emission-only materials (no lights), straight-alpha Kuwahara, no drop shadow, no edge bleed beyond 2 px; additive look comes from the art, the UI draws them normally |
| event | Events 640x360, Duel 1280x720, Title 1920x1080, Battle background: perspective 35 mm, same top-left sun at 35 deg; mist = world gradient + depth-masked blur |
| background | Duel 1280x720, Title 1920x1080, Battle background: as 'event' with bigger strokes (5 px) and ink 2.0 |
| mask | Hex_Fill / Hex_Outline: pure numpy (post.hex_mask, outline = mask - hex_mask(inset=3)), white RGB, no render |

| UI piece (no style frame yet) | Recipe |
|---|---|
| PanelDark | Panel profile with LacquerDark/dark_wood field instead of paper; gold moulding 9-12 px; field = Night #1B1712 lifted to #2A2119 at the centre |
| Tab / Tab_Active | 160x48, Button profile at 2/3 height, margins 20/16; inactive = dark_wood field, active = Lacquer field + gold underline |
| Frame_Portrait | 212x260, 10 px border (transparent centre 192x240 exactly): dark wood + 2.5 px gold moulding + 7x7 gold corner fittings; alpha 0 inside |
| Seal | 128x128 extruded square, glyph carved by boolean, Lacquer #7E1F17 field with paper showing in the carved strokes, Kuwahara 0, paper 0.06, rotated 3 deg |
| Divider | 512x16: gold moulding 2.5 px with a central cloud-scroll knot 16x16; uniform along x outside the central 64 px (it may be stretched) |
| Scroll | 1024x640, 80 px margins: paper field (parchment, calibrated), rolled ends as dark_wood cylinders with gold caps inside the 80 px margins |
| Title_Logo | 1200x400 transparent: extruded Heading-font letters in iron with gold bevel + brush calligraphy as a lacquer-red emission layer; ink 2.0 |
| unknown | 192x240 portrait recipe with a matte #2A2119 silhouette bust (same head/torso), rim light only |
<!-- END recipes -->

Measured render times (last full run, 4 shared cores, `nice 10`; expect +-50 % with load):

| Frame | Settings | Render | Total wall |
|---|---|---|---|
| (a) map crop 512x320 | 2x, 40 spp | 12.3 s | 24.6 s (fields + albedo 8.5 s) |
| (b) City_2 96x96 (City_1 / City_3) | 4x, 64 spp | 4.7 s (5.7 / 6.1 s) | 5.9 s (7.1 / 7.4 s) |
| (c) forest hex 128x111 | 4x, 48 spp | 14.5 s | 17.3 s |
| (d) portrait 192x240 | 2x, 56 spp (preview 2x / 24 spp) | 19.9 s (preview 13.2 s) | 31.4 s (build 7.3 s) |
| (e) button 192x64 + panel 128x128 | 4x, 48 spp | 7.2 s + 14.5 s | 23.6 s |

The whole `run_all.sh` (5 frames, City_1 / City_3, the archetype sheet at preview quality, sheets)
took 3 min 15 s. Under heavy load from other jobs (load average 8 on 4 cores) the same frames took
about 2x longer (portrait 48 s, panel 27 s). Hair curves dominate the portrait: 102 portraits
at the production setting take about 102 x 31 s = 53 min on free cores, up to about 80 min
under load.

## 6. Ink (Freestyle) and paint (Kuwahara)

`ink.enable(thickness_px, ...)` builds a two-weight brush ink: the **Outer** line set traces the
external contour (or each object's contour, `outer_select='contour'`, for hex canopies) at
`thickness_px`; the **Inner** set traces silhouettes and creases at `inner_scale x thickness_px`
and `inner_alpha`. Taper, 45 deg calligraphy, pressure noise and Bezier smoothing give the brush
feel. Always render with `as_pass=True`; `comp_painterly(ink=True)` lays it over the paint.

`ink.thickness_for(short_side)` (fallback for new families; recipes win):

| Output short side | Outer ink |
|---|---|
| <= 64 px (icons, flag) | 0.75 |
| <= 128 px (cities, units, hex) | 0.9 (hex canopies use 0.8 at alpha 0.6) |
| <= 256 px (UI) | 1.0 (portraits: no ink) |
| <= 720 px (events) | 1.6 |
| larger (backgrounds, title) | 2.0 (the map uses a 2D coast line: InkSoft, alpha 0.55) |

Kuwahara is always anisotropic, uniformity 4. Portraits use two scales: the face objects
(`pass_index 1`: head, eyeballs, brows, mustache) get 1.5 px strokes so skin keeps its form and the
eyes stay crisp; armour, beard and ground get 3 px strokes at eccentricity 2.0 (directional). The
UI is never painted.

## 7. Palette (generated from `ironart/palette.py`)

All colours are authored as sRGB hex. Blender sockets need linear values: always go through
`palette.lin()` / `lin4()` or pass a token name to the material factories.

<!-- BEGIN palette -->
| Group | Token | sRGB | Linear |
|---|---|---|---|
| UI | Paper | `#E9DCC0` | 0.815, 0.716, 0.527 |
| UI | PaperDark | `#CDB990` | 0.610, 0.485, 0.279 |
| UI | Ink | `#2A2119` | 0.023, 0.015, 0.010 |
| UI | InkSoft | `#5A4A3A` | 0.102, 0.068, 0.042 |
| UI | Lacquer | `#7E1F17` | 0.209, 0.014, 0.009 |
| UI | LacquerDark | `#4A120D` | 0.068, 0.006, 0.004 |
| UI | Gold | `#C9A24A` | 0.584, 0.361, 0.068 |
| UI | Jade | `#3F6E5A` | 0.050, 0.156, 0.102 |
| UI | Indigo | `#2E3F5C` | 0.027, 0.050, 0.107 |
| UI | Night | `#1B1712` | 0.011, 0.009, 0.006 |
| Faction | IronBanner | `#B3282D` | 0.451, 0.021, 0.026 |
| Faction | WolfRiders | `#B07A2A` | 0.434, 0.195, 0.023 |
| Faction | AzureCourt | `#2F6DB5` | 0.028, 0.153, 0.462 |
| Faction | SeaLeague | `#1F8F8A` | 0.014, 0.275, 0.254 |
| Faction | SouthernLotus | `#4C9A3C` | 0.072, 0.323, 0.045 |
| Faction | BlackMountain | `#4A4A55` | 0.068, 0.068, 0.091 |
| Faction | Independent | `#8C8577` | 0.262, 0.235, 0.184 |
| Material | stone | `#8E8B82` | 0.270, 0.258, 0.223 |
| Material | stone_dark | `#5E5C57` | 0.112, 0.107, 0.095 |
| Material | mortar | `#B5AE9E` | 0.462, 0.423, 0.342 |
| Material | roof_tile | `#3D4A4E` | 0.047, 0.068, 0.076 |
| Material | roof_tile_light | `#5E6E70` | 0.112, 0.156, 0.162 |
| Material | roof_ridge | `#2C3436` | 0.025, 0.034, 0.037 |
| Material | pillar_red | `#8C2A1C` | 0.262, 0.023, 0.012 |
| Material | plaster | `#D9CCB0` | 0.694, 0.604, 0.434 |
| Material | timber | `#5A3B26` | 0.102, 0.044, 0.019 |
| Material | dark_wood | `#3A2619` | 0.042, 0.019, 0.010 |
| Material | lacquer | `#7E1F17` | 0.209, 0.014, 0.009 |
| Material | lacquer_dark | `#4A120D` | 0.068, 0.006, 0.004 |
| Material | gold | `#C9A24A` | 0.584, 0.361, 0.068 |
| Material | bronze | `#8A6A3A` | 0.254, 0.144, 0.042 |
| Material | iron | `#5C6066` | 0.107, 0.117, 0.133 |
| Material | iron_dark | `#3A3D42` | 0.042, 0.047, 0.054 |
| Material | leather | `#5A3E2A` | 0.102, 0.048, 0.023 |
| Material | lacing_red | `#9A2E22` | 0.323, 0.027, 0.016 |
| Material | cloth_white | `#FFFFFF` | 1.000, 1.000, 1.000 |
| Material | silk_blue | `#2F4A6A` | 0.028, 0.068, 0.144 |
| Material | silk_red | `#8A2A20` | 0.254, 0.023, 0.014 |
| Material | paper | `#E9DCC0` | 0.815, 0.716, 0.527 |
| Material | paper_dark | `#CDB990` | 0.610, 0.485, 0.279 |
| Material | ink | `#2A2119` | 0.023, 0.015, 0.010 |
| Material | skin | `#C68F6A` | 0.565, 0.275, 0.144 |
| Material | skin_shadow | `#8A5440` | 0.254, 0.089, 0.051 |
| Material | lips | `#A0584A` | 0.352, 0.098, 0.068 |
| Material | hair_black | `#1C1714` | 0.012, 0.009, 0.007 |
| Material | hair_grey | `#8A8580` | 0.254, 0.235, 0.216 |
| Material | hair_white | `#DAD5CC` | 0.701, 0.665, 0.604 |
| Material | eye_white | `#D8D0C4` | 0.687, 0.631, 0.552 |
| Material | iris | `#3A2416` | 0.042, 0.018, 0.008 |
| Material | plain | `#94A26E` | 0.296, 0.361, 0.156 |
| Material | grass | `#7E9A5C` | 0.209, 0.323, 0.107 |
| Material | meadow | `#93A867` | 0.292, 0.392, 0.136 |
| Material | steppe | `#B5A06E` | 0.462, 0.352, 0.156 |
| Material | desert | `#BFA776` | 0.521, 0.386, 0.181 |
| Material | hill | `#949A6A` | 0.296, 0.323, 0.144 |
| Material | rock | `#8A8578` | 0.254, 0.235, 0.188 |
| Material | mountain | `#7C838C` | 0.202, 0.227, 0.262 |
| Material | mountain_dark | `#5A6068` | 0.102, 0.117, 0.138 |
| Material | snow | `#ECEBE6` | 0.839, 0.831, 0.791 |
| Material | forest | `#3E5E3A` | 0.048, 0.112, 0.042 |
| Material | forest_dark | `#2C4430` | 0.025, 0.058, 0.030 |
| Material | forest_light | `#5E7A44` | 0.112, 0.195, 0.058 |
| Material | bamboo | `#6E8A4A` | 0.156, 0.254, 0.068 |
| Material | trunk | `#4A3626` | 0.068, 0.037, 0.019 |
| Material | sea_deep | `#1D3A52` | 0.012, 0.042, 0.084 |
| Material | sea | `#2A5068` | 0.023, 0.080, 0.138 |
| Material | sea_shallow | `#5E9A9A` | 0.112, 0.323, 0.323 |
| Material | beach | `#CDBB8E` | 0.610, 0.497, 0.270 |
| Material | river | `#4F86A8` | 0.078, 0.238, 0.392 |
| Material | river_bank | `#3A6A88` | 0.042, 0.144, 0.246 |
| Material | lake | `#3F7290` | 0.050, 0.168, 0.279 |
| Material | dirt | `#8E7552` | 0.270, 0.178, 0.084 |
| Material | road | `#A8916A` | 0.392, 0.283, 0.144 |
<!-- END palette -->

The material tokens `lacquer`, `lacquer_dark`, `gold`, `paper`, `paper_dark` and `ink` are aliases
of the UI tokens with the same values.

## 8. Tinting conventions (hard contract)

The runtime multiplies these areas by the faction colour, so they must be **pure white and
neutral**: `Banner.png` cloth, `Flag.png` pennant, the white clothing and flags on `Unit_*.png`,
`Unit_Base.png`, `Hex_Fill.png` and `Hex_Outline.png`.

- Use `materials.white_cloth()`: albedo exactly 1.0, no sheen, no variation, no paint mix. It
  also writes 1.0 into the `TintMask` AOV (`materials.enable_tint_aov()` once per scene).
- Use the `tint_plate` recipe: Standard view, `rig_sprite(neutral=True)` (white key, fill and
  rim, grey sky), grade saturation 1 / contrast 1 / warmth 0, no paper, no drop shadow.
- Save the AOV with `post.comp_outputs(out, {"tint": rl.outputs["TintMask"]})` and pass it to
  `recipes.finish(..., tint_mask=mask)`, which runs `post.neutralize` (R = G = B inside the mask,
  luma kept) after every grading step.
- Check with `post.neutral_check(img, mask)`: mean <= 1 and p99 <= 4 levels over **every** cloth
  pixel, folds included. Measured on the test banner: (0.51, 7.9) before `neutralize`,
  (0.06, 2.4) after.
- Glyph area (`BannerGlyphArea.txt`): `geometry.banner()` returns the cloth's 4 world corners;
  write `cameras.target_rect(cam, corners)` as integer `x y w h`, space-separated, in target
  pixels (the UI splits on whitespace).
- Faction colours never appear in art. City sprites use neutral stone and wood.

## 9. NPR "paint" shading

`materials.paint(mat, amount, size, smooth)` mixes a Toon BSDF diffuse into a material (a banded
terminator with a soft edge).

| Use | Amount |
|---|---|
| Hex canopies | 0.4 |
| Map trees | 0.3 |
| Roof tiles (`architecture_set`) | 0.65, size 0.62, smooth 0.06: splits roof slopes into a lit and a shadow plane |
| Skin, metal, UI | 0 |

## 10. Sprites: anchoring, shadow, alpha

- **Anchoring.** One rule: the ground centre (world origin) lands on (0.5, 0.70) of the canvas
  (48, 67 on a 96 px city) with margins (2, 2, 6, 6) target px (`recipes.frame`).
- **Pennant keep-out.** The UI draws `Flag.png` over x 56-83, y 0-23 of the 96 px city canvas;
  city alpha there must stay below 0.1 (asserted).
- **Contact shadow.** `post.drop_shadow(img, offset=(2.2, 2.2), blur_px=1.6, opacity=0.35,
  depth_px=6, shear=0.15)` takes the ground footprint (the bottom 6 px of every column), shears
  it right and pushes it towards 315 deg, matching the map's cast shadows, then fades it over the
  last 2.5 px of the canvas. No shadow catchers.
- **Alpha.** `post.alpha_cleanup` (dust below 0.03 removed, edge colour bled 4 px with padded,
  non-wrapping shifts). The outer 1 px ring of every map/board sprite must be alpha 0
  (asserted; `check_art.py` checks committed sprites).
- **Downsampling.** `post.downsample` is premultiplied Lanczos with ringing clamped to alpha; the
  supersample factor must be an integer.

## 11. Per-family recipes

**World map (2400x1500).** Follow `styleframes/sf_terrain.py`: domain-warped land mask; one
continuous ridged range per spine (`ridged_at` scale 70 px, 4 octaves, sharpness 1.5; spine width
42 +- 6 px; relief 0.55 m); foothill fbm amplitude 0.12 at 40 px; rivers from `meander()` with
`join_tributary()` snapping tributaries onto the meandered main river, width 2 -> 6.4 px plus a
9-10 px mouth flare and a 1 px bank line at 50 %; `paint_albedo` (snow line at the 85th
percentile of range height, slope shedding 0.3, forest floor 0.45, beach 1.5 px, shallows 10 px
fading over 20 px); forests as elongated domain-warped lobes along the rivers plus 6-10 copses
(`scatter_forest`, canopy 1.8-2.6 px). Render the full map as **one** 4800x3000 frame (the
compositor handles it; tiles would seam the Kuwahara and the coast line). Compute the fields in
float32 and `polyline_distance` per block (`block_rows`). Prototype (measured):
`sf_terrain.make_fields` on a quarter of the full map (fields 2400x1500) takes 45 s and peaks at
1.07 GB, so the full 4800x3000 field set extrapolates to about 3 min and 4 GB; albedo painting,
the 3.6 M-vertex mesh and the render are not yet measured at full size. Never draw city icons, roads or labels
into the map. QA: `terrain.check_rivers` and the plains/snow/navy asserts of the style frame.

**City_1 / City_2 / City_3 (96x96).** `geometry.walled_city(mb, rng, size=1|2|3)` with
`materials.architecture_set()`; recipe `sprite`; each tier fitted independently.

| Tier | Walls | Contents |
|---|---|---|
| City_1 (town) | 5.0 x 4.4 m, 0.7 m high, no towers | gate, hall, 4 houses, 3 tree clumps |
| City_2 (walled city) | 6.4 x 5.6 m, 0.95 m, corner towers | two-storey gate tower with red-lacquer doors, keep on a 1.8 m podium, 4 houses, trees |
| City_3 (great city) | 7.6 x 6.6 m, 1.1 m, corner towers | as City_2 with a 2.1 m keep podium, a hall and a 5-tier pagoda |

**Banner (64x96), Flag (32x48), Unit_Base.** Recipe `tint_plate` (section 8).

**Sect (64x64).** `geometry.pagoda(tiers=3-5)` on a rock with pines; recipe `sprite`.

**Units (96x96).** Small figures from the figure kit (`torso`, `helmet`, a `white_cloth` tabard
or flag) drawn over `Unit_Base`; recipe `tint_plate` for the white areas; one shared
`units_per_px` for the whole family.

**Hex tiles (128x111).** Recipe `hex`; r = 1 m. Forest floor painted out to 1.12 r; trunks out
to 0.98 r with the edge band (hex metric > 0.72) generated from one shared seed and copied to the
6 lattice neighbours, so a canopy cut by one tile's mask continues in the next; radially uniform
density 54 trees/m2 (about 100-120 trees, 27 % pines, broadleaf crowns 0.07-0.10 m with 7-9
sub-clumps); `--variant N` changes only the interior, so variants mix freely (or rotate 60 deg at
runtime). Water / Ford / Bridge use `materials.water`; Wall, Gate, Castle and Town reuse
`walled_city` parts at about 0.35 scale. `Hex_Fill` / `Hex_Outline` are 2D masks (recipe `mask`).

**Events (640x360), duel (1280x720), title (1920x1080), battle background.** Recipes `event` /
`background`: perspective 35 mm, the same sun at 35 deg, Kuwahara 4.5 / 5 target px, ink 1.6 /
2.0, paper 0.08; mist from a world gradient plus a depth-masked compositor blur.

**Portraits (192x240, opaque).** `figure.bust(kind, rng, mats)` then
`figure.eyeballs(r["specs"], mats["Eye"], look_at=cam.location)`; recipe `portrait`.

- Head: `figure.head(HeadParams)` is a smooth SDF union of skull, forehead, face/jaw, chin and
  jaw-angle masses (no creases), plus additive relief: brow ridge, cheekbones, a nose 34 mm across
  the alae with the tip volume cut, a 14 mm philtrum, lips, a 50 mm mouth painted as a dark line
  (`lip` / `mouth` vertex attributes read by `materials.skin`), mentolabial sulcus and chin boss.
  Lids conform to spheres around the eyeballs, the opening is carved behind the eyeball, and no
  skin may sit inside an eyeball (crisp lid edges, nothing pokes through). Pupils 62 mm apart.
- Hair as curves: brows (300-700 strands), beard (full: 7.5k strands, 95 mm, converge 0.75,
  melanin 0.88, Huang reflection 0.55; it starts under the lower lip so the mouth shows), mustache
  (from under the nostrils, out along the upper lip above the vermilion, down beside the mouth
  corners), plume (3.2k).
- Gear: helmet with the brim 37 mm above the brow line (forehead shows), long flared neck guard,
  compact plume cup; lamellar torso (8 x 16 mm plates, alternate rows offset, lacing `#4A1510`
  at half width, a bronze band every 7 rows) with a lamellar neck collar; crossed jiaoling collar
  (`cross_collar`, silk red `#8A2A20` over cream `#D8CBB0`, left lapel on top); layered
  pauldrons; chest mirror. No cape, no neck scarf.

| Archetype (`figure.ARCHETYPES`) | Head | Hair / headwear | Body |
|---|---|---|---|
| warrior | jaw 1.15, chin 1.1, brow 1.12, cheekbone 1.2, nose_len 0.9, nose_width 0.88, socket 1.6, eye_size 0.95, lids 0.31 / 0.26, age 0.5; skin `#A26A4C` | helmet + plume, full beard, full mustache, thick angled brows | lamellar, red/cream collar, pauldrons, mirror |
| scholar | jaw 0.97, nose_len 1.04, nose_width 0.84, eye_tilt 0.10, age 0.35; skin `#B07E5E` | hair cap with natural hairline, topknot, black guan with a gold pin, goatee from under the lip, thin mustache | blue-grey robe with folds, dark/cream collar |
| female | width 0.142, height 0.218, jaw 0.80, chin 0.85, lower 0.9, nose_len 0.80, lips 1.5, eye_size 1.04, eye_width 1.3; skin `#C8977A`, lips `#A23C34` | parted hair cap, bun with a gold pin | wine robe with folds, red/cream collar, shorter neck drop |

- Before any batch run, render `styleframes/sf_archetypes.py` (warrior, scholar, female side by
  side, each through the portrait QA) and review `portrait_archetypes.png`.
- Same rig, background recipe and framing for every portrait, so a gallery reads as one set.

**Icons (64x64).** Recipe `icon`: one prop per icon, sprite camera, centred, 4 px margins, ink
0.75, no ground shadow.

**Fx_* (96x96).** Recipe `fx`: emission only, straight-alpha Kuwahara, no shadow, no edge bleed
beyond 2 px.

**UI.** Build pieces with `geometry.profile_sweep(mb, w, h, r, profile, ...)` from a cross-section
profile ((inset px, height px) pairs from the outside in) with per-segment materials. Keep every
ornament inside the 9-slice margins (Button / Tab 20 x 16, Panel / PanelDark 24, Scroll 80) and
make every border strip uniform along its stretch direction (`gold_leaf(uniform=True)`,
`lacquer(vary=0)`, vertical-only gradients).

- **Panel (24 px border).** 0-9 px lacquered dark wood (`#3A2619`) rolling into a LacquerDark
  bevel; 9-12 px a 2.5 px round gold bead lit top-left; 12-24 px aged paper PaperDark -> Paper
  over 10 px (per-ring `edge_t` attribute, uniform along every edge); 9 x 9 px gold meander
  ("hui") ornaments with a 1.5 px stroke in the four corners; isotropic paper fibre (no streaks)
  calibrated so the field mean lands on Paper.
- **Button.** 3 px LacquerDark rim (`#3A1A12`) with a top-left catchlight, 2 px bevelled gold
  trim, 7 x 7 px gold L-bracket corner fittings with a 2.4 px boss inside the 20 x 16 corners,
  Lacquer field with a vertical-only gradient and a soft sheen band (+15 % at 25-40 % of the
  height).
- **States.** Hover: Lacquer +12 % value. Pressed: LacquerDark field, content offset 1 px down
  and right. Disabled: desaturated, 60 % value.
- Pieces without a style frame yet (PanelDark, Tab, Frame_Portrait, Seal, Divider, Scroll,
  Title_Logo, unknown) have one-line recipes in the generated table of section 5.

## 12. QA

- `post.QA(label)` collects `range` / `max` / `color` / `hue` checks, prints them and raises at
  `check()`; `post.qa_values(img, checks)` is the one-call form. Every style frame asserts its
  measured targets (section 4), so `run_all.sh` fails when the look drifts.
- `post.nine_slice_uniformity(img, margins)` (detrended per-row / per-column std of the border
  strips), `post.border_alpha_max(img)`, `post.neutral_check(img, mask)`, `terrain.check_rivers`.
- `post.save_asset(img, rel_path)` validates against `ironart/manifest.py` (exact size, RGBA,
  clear border, tint) and `check_art.py` checks the committed tree (and that `manifest.py` still
  matches the DESIGN.md tables).

## 13. Naming and layout

```
Tools/BlenderArt/
  render.sh                 single entry point
  check_art.py              committed art vs the DESIGN.md manifest (system python3)
  STYLE.md                  this file (sections 5 and 7 are generated)
  ironart/                  the library (see the module docstrings); recipes.py = the numbers
  styleframes/              the five reference frames, sf_archetypes.py, run_all.sh, make_sheet.py
  assets/<family>.py        (to be added by artists) one script per manifest family, e.g.
                            assets/map_cities.py -> Content/Data/Art/Map/City_{1,2,3}.png
```

- Style frames and asset scripts guard `main()` with `if __name__ == "__main__":`, so their
  builders can be imported; reusable builders belong in `ironart` (`geometry.walled_city`,
  `figure.bust`).
- Scripts take an optional output directory as their first argument; intermediates are named
  `<asset>_raw_<N>x.png`; every script prints `[ironart] TIMES {...}` and its QA lines.
- Seeds are explicit (`scene.reset(seed=...)`, `random.Random(seed)`), so re-running a script
  gives an identical image.
