# Iron Reign art pipeline: Blender style guide

This guide covers the Blender pipeline in `Tools/BlenderArt/` that every artist uses to regenerate
the game art listed in `docs/DESIGN.md` section 8. That manifest is a hard contract with the UI
code: keep the same paths, the same pixel sizes, transparency and the white-cloth tint rules.
This guide gives the look in words and numbers. The code in `ironart/` puts those numbers into
practice, and the style frames in `styleframes/` show them working.

## 1. The look

Painterly non-photorealistic rendering over real 3D, in the style of Koei games of 1998-2004
(Romance of the Three Kingdoms IX and Taiko Risshiden IV).

| Family | What it must read as |
|---|---|
| World map | A painted 3D relief map seen from above. Soft natural colours: sage and ochre plains, sandy steppe, blue-grey mountains with light snow, deep teal-indigo sea with lighter shallows. Gentle hill shading from the top-left. Forests are dense clusters of tiny trees. Rivers are clear blue ribbons. A thin ink line runs along the coast. |
| Cities and buildings | Small 3D Chinese walled cities in a 3/4 top-down view. Grey stone walls, gate towers with dark teal-grey tile roofs and upturned eaves, and red lacquer pillars. Silhouettes must stay readable at 96 px. |
| Portraits | Dramatic painted realism. A strong warm key light from the upper left, a dark paper ground and a cool rim. Rich but muted armour and silk. Visible brushwork with crisp eyes. |
| UI | Lacquered dark wood and red lacquer, gold trim, warm parchment, ink lines and red seals. |

Rules that apply everywhere:

- The light comes from the top-left of the screen.
- Use no neon or photographic colours. Build colours from the palette in section 7.
- Cycles handles form and light. Kuwahara compositing, paper grain and controlled saturation add the paint.
- Freestyle ink lines are selective. Use them on sprites and UI, sparingly on the map (coast only), and not on faces.

## 2. Pipeline

```
build (MeshBuilder / figure / terrain)
  -> camera (cameras.*, exact pixel framing)
  -> light rig (lights.rig_*)
  -> Cycles CPU at supersample x target size, Freestyle ink as a separate pass
  -> compositor: [background] -> anisotropic Kuwahara -> mix -> grade -> ink over      (post.comp_painterly)
  -> numpy: Lanczos downsample (premultiplied) -> grade -> paper -> alpha clean-up/bleed (post.*)
  -> PNG (sRGB, 8-bit; RGBA for sprites/UI, RGB for portraits/map)
```

Run every script through the wrapper. It uses the same flags every time, reports timing and
exits non-zero on any Python exception:

```
Tools/BlenderArt/render.sh <script.py> [args...]
IRONART_OUT=/tmp/x Tools/BlenderArt/styleframes/run_all.sh     # all style frames + overview sheet
```

Environment variables:

| Variable | Effect |
|---|---|
| `IRONART_OUT` | Scratch root. The default is `/tmp/ironart`. |
| `IRONART_THREADS` | Fixed Cycles thread count. |
| `IRONART_VERBOSE=1` | Shows Blender's per-sample log. |
| `IRONART_LOG=file` | Writes a full log to `file`. |

Scripts write intermediates such as `*_raw_Nx.png` to `$IRONART_OUT/<family>/`. Only final PNGs go
to `Content/Data/Art/...`. Never commit the raw renders.

### Facts about this machine's Blender build (Blender 4.0.2, Ubuntu package)

The code depends on these:

- **Rendering:**
  - Only **Cycles on CPU** works. EEVEE and Workbench crash when headless, so never select them.
  - **OpenImageDenoise is not available**, so denoising stays off. Use supersampling, adaptive
    sampling, `clamp_indirect=4`, and let the Kuwahara pass absorb what noise remains.
- **Colour management:** the view transforms are `Standard`, `Filmic` (looks `Medium Contrast` /
  `Medium High Contrast` / `High Contrast`), `AgX` and `Raw`. Listing the enum headless shows
  `NONE`, but setting a value by name works.
- **Freestyle:**
  - An empty factory scene has a line set without a line style, which segfaults.
    `ink.enable()` always creates fresh line styles.
  - Freestyle's Python crashes on open-boundary edges of smooth-shaded faces
    (`FEdgeSmooth has no normal_left`). `ink._patch_freestyle()` monkey-patches the two thickness
    setters. `enable()` applies the patch for you.
- **Shader nodes:**
  - **Shader to RGB is EEVEE-only.** The "paint" banding uses the Toon BSDF instead (section 9).
  - Some 4.0 sockets have identifiers that differ from their names, such as the Hair BSDF's
    `Random Color`. Use `materials.sock(node.inputs, name)`.
- **Hair:** hair uses the 4.x `Curves` datablock (`geometry.hair_curves`), not particle systems,
  which are hard to shape by script. To pick a particle material, use `settings.material = index`.
  The `material_slot` enum is empty when headless.
- **Compositor:** the CPU compositor has the Kuwahara node (classic and anisotropic), Glare,
  Color Balance, Bilateral Blur, Denoise (unusable without OIDN) and the other standard nodes.

## 3. Units and cameras

| Family | Scene scale | Camera | Notes |
|---|---|---|---|
| World map | 1 target px = 1 cm | `ortho_top_down`, screen-up = +Y (north) | Relief: normalised height 1.0 = 0.42 m |
| City, unit, banner, sect, icon sprites | 1 m (a city is about 7 m across) | `sprite_camera(elevation 35, azimuth -20)`, ortho | Shows the front and the lit west face |
| Hex tiles | r = 1 m (64 px/m) | `ortho_top_down(width=2.0)` | Strictly top-down so the tiles join |
| UI 9-slices, frames, seals | 1 target px = 1 mm | `ortho_top_down(width=px(W), height=px(H))` | Slabs built by profile sweeps |
| Portraits | 1 m (head is 0.232 m from chin to crown) | `portrait_camera(85 mm, 36 mm vertical sensor)` | Eyes at 38 % from the top |

Framing helpers:

- `cameras.fit_ortho(cam, objs, margin_px, anchor='bottom_center' | 'center', anchor_world, anchor_px, units_per_px)`
  projects the evaluated vertices, so the frame is exact.
- To keep a family at one scale, take the `units_per_px` returned by the largest member and pass
  it to the others. For example, City_1..3 should share it so a town looks smaller than a great city.
- `cameras.center_on(cam, objs)` centres a portrait whatever the yaw.

## 4. Light

Every rig places its lights in **screen space** with `lights.screen_dir(cam, angle, elevation)`.
The angle is measured counter-clockwise from screen-right, so 135 means from the top-left. The
elevation is measured towards the viewer.

| Rig | Key | Fill | Rim | Ambient |
|---|---|---|---|---|
| `rig_sprite` | sun 3.2 W/m², 145° / 62°, warm `#FFF1DC`, 6° soft | sun 0.55, −30° / 35°, `#B8C8E0`, no shadow | sun 1.2, 60° / −35° | sky `#8C9AB0` × 0.45 |
| `rig_map` | sun 3.4, 135° / 36°, 10° soft | – | – | sky `#9FB2C8` × 0.62 |
| `rig_portrait` | area 0.5 m, 48 W at 1.6 m, 140° / 15°, warm | area 1.6 m, 5 W, −15° / 25°, cool, no shadow | area 0.5×1.2 m, 16 W, 40° / −45° | `#3A3530` × 0.04 |
| `rig_ui` (calibrated) | sun 135° / 50°, strength solved so that a flat face-up surface renders at exactly 1.0 × albedo | – | – | uniform white 0.2 for diffuse; glossy rays see a "studio ring" that is bright near the horizon and dark at the zenith |

Notes on the rigs:

- **Sprites.** With the sprite camera, the key lands at about 47° elevation from the south-west.
  Faces then read in three values: tops 0.73, west faces 0.56 and south faces 0.40. East and
  north faces get only fill and sky.
- **Portraits.** The rig is calibrated so skin reaches about 0.6 linear. Hotter keys look fine
  on skin under Filmic but wash dark armour out to grey.
- **UI.** Palette tokens land exactly. Lacquer measures (127, 37, 28) against `#7E1F17`, and
  paper (238, 215, 175) against `#E9DCC0`. Gold and bevels still get rich reflections.

## 5. Colour management, samples and supersampling

| Family | View / look | Supersample | Samples (adaptive 0.01) | Preset | Measured render time* |
|---|---|---|---|---|---|
| Map | Standard | 2× | 40 | `map` | 512×320 crop: 14–19 s (+10 s numpy fields). Full 2400×1500 at 4800×3000: about 7 min (estimated from pixel count; build the mesh with `grid_step=2`, one vertex per target pixel) |
| Sprites | Standard | 4× | 64 | `sprite` | 96×96 city: 4–7 s |
| Hex tiles | Standard | 4× | 48 | `sprite` | 128×111 forest: 10 s |
| Portraits | Filmic, Medium High Contrast | 3× | 96 (use `--preview` for 2× / 40 while iterating) | `portrait` | 192×240: 54–61 s (preview 13–19 s) |
| UI | Standard | 4× | 48 | `ui` | 192×64 button: 7 s; 128×128 panel: 13 s (the glossy studio-ring world doubles the time) |

\*Times are for 4 shared CPU cores and can vary by about ±50 %. A 256 px frame at 32 spp takes about 1 s.

Never use denoising. If a frame is noisy, raise the samples, or raise the supersampling for small
sprites. Do not lower the adaptive threshold below 0.005.

## 6. Ink (Freestyle) and paint (Kuwahara)

`ink.enable(thickness_px, ...)` builds the two-weight brush ink:

- The **Outer** set traces the external contour, the silhouette against the background, at
  `thickness_px`.
- The **Inner** set traces silhouettes and creases at `inner_scale × thickness_px` and
  `inner_alpha` opacity.
- Brush feel comes from four line-style modifiers: an along-stroke taper (0.3 → 1 → 0.3), a
  calligraphy modifier at 45° (×0.7 to ×1.2), a pressure-noise modifier that adds 0 to 25 %,
  and Bezier smoothing.
- Render with `as_pass=True`. `post.comp_painterly(ink=True)` lays the crisp ink over the painted
  colour after the Kuwahara.

Thickness is given in **target** pixels. The supersample scaling is automatic.

| Output short side | Outer thickness (`ink.thickness_for`) | Used in style frames | Inner |
|---|---|---|---|
| ≤ 64 px (icons, flag) | 0.75 | – | 0.5 × at α 0.6 |
| ≤ 128 px (sprites, hex, units) | 1.0 | city 0.6 at α 0.85; hex 0.55 at α 0.7 | 0.6–0.7 × at α 0.6 |
| ≤ 256 px (portraits, UI) | 1.25 | UI 1.0, outer only; portraits none | – |
| ≤ 720 px (events) | 1.6 | | 0.5 × |
| > 720 px (backgrounds, title) | 2.0 | the map uses a 2D coast line instead (InkSoft, α 0.55, about 1.2 px) | |

The Kuwahara radius is in **render** pixels. It always uses the anisotropic variation with
uniformity 4. The table lists the values used:

| Family | Size | Sharpness | Eccentricity | Mix (`amount`) |
|---|---|---|---|---|
| Map (2×) | 7 | 0.45 | 1.2 | 0.75 |
| Sprites (4×) | 4 | 0.7 | 0.8 | 0.6 |
| Hex (4×) | 7 | 0.5 | 1.2 | 0.85 |
| Portraits (3×) | 7 | 0.5 | 1.3 | 0.8 |
| Events and backgrounds (2×) | 8–10 | 0.45 | 1.2 | 0.8 |
| UI | 0 (off) | – | – | – |

Numpy finishing settings used by the style frames:

| Family | Unsharp | Grade | Paper (`apply_paper`) | Other |
|---|---|---|---|---|
| Sprites | 0.8 px, amount 0.3 | sat 0.95–1.08, contrast 1.04–1.06, warmth +0.01–0.015 | none | – |
| Portraits | 0.8 px, amount 0.45 (crisp eyes) | as above | strength 0.04 | vignette 0.3 |
| Map | – | as above | strength 0.05 | – |

## 7. Palette

All colours are authored as sRGB hex. Blender sockets need linear values, so always go through
`palette.lin()` / `lin4()` or pass the token name to the material factories. The table was
generated by `palette.table_markdown()`.

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
| Material | bronze | `#8A6A3A` | 0.254, 0.144, 0.042 |
| Material | iron | `#5C6066` | 0.107, 0.117, 0.133 |
| Material | iron_dark | `#3A3D42` | 0.042, 0.047, 0.054 |
| Material | leather | `#5A3E2A` | 0.102, 0.048, 0.023 |
| Material | lacing_red | `#9A2E22` | 0.323, 0.027, 0.016 |
| Material | cloth_white | `#FFFFFF` | 1.000, 1.000, 1.000 |
| Material | silk_blue | `#2F4A6A` | 0.028, 0.068, 0.144 |
| Material | silk_red | `#8A2A20` | 0.254, 0.023, 0.014 |
| Material | skin | `#C68F6A` | 0.565, 0.275, 0.144 |
| Material | skin_shadow | `#8A5440` | 0.254, 0.089, 0.051 |
| Material | lips | `#A0584A` | 0.352, 0.098, 0.068 |
| Material | hair_black | `#1C1714` | 0.012, 0.009, 0.007 |
| Material | hair_grey | `#8A8580` | 0.254, 0.235, 0.216 |
| Material | hair_white | `#DAD5CC` | 0.701, 0.665, 0.604 |
| Material | eye_white | `#D8D0C4` | 0.687, 0.631, 0.552 |
| Material | iris | `#3A2416` | 0.042, 0.018, 0.008 |
| Material | plain | `#A9A86A` | 0.397, 0.392, 0.144 |
| Material | grass | `#7E9A5C` | 0.209, 0.323, 0.107 |
| Material | meadow | `#93A867` | 0.292, 0.392, 0.136 |
| Material | steppe | `#C8B282` | 0.578, 0.445, 0.223 |
| Material | desert | `#D4BC8A` | 0.658, 0.503, 0.254 |
| Material | hill | `#9A9468` | 0.323, 0.296, 0.138 |
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
| Material | sea_shallow | `#4E8288` | 0.076, 0.223, 0.246 |
| Material | beach | `#CDBB8E` | 0.610, 0.497, 0.270 |
| Material | river | `#4F86A8` | 0.078, 0.238, 0.392 |
| Material | lake | `#3F7290` | 0.050, 0.168, 0.279 |
| Material | dirt | `#8E7552` | 0.270, 0.178, 0.084 |
| Material | road | `#A8916A` | 0.392, 0.283, 0.144 |

The material tokens `lacquer`, `lacquer_dark`, `gold`, `paper`, `paper_dark` and `ink` are aliases
of the UI tokens with the same values.

## 8. Tinting conventions (hard contract)

The runtime multiplies these areas by the faction colour, so they must be **pure white and neutral**:

- `Banner.png` cloth and `Flag.png` pennant
- white clothing and flag areas on `Unit_*.png`
- `Unit_Base.png`
- `Hex_Fill.png` and `Hex_Outline.png`

Rules:

- Use `materials.white_cloth()`. Its albedo is exactly 1.0, with no sheen, no colour variation and
  no paint mix. Grey shading in the folds is fine and wanted, but the hue must stay neutral
  (R = G = B: a mean deviation of 1 level or less).
- Render tint plates with view **Standard**. Filmic shifts whites and desaturates.
- Keep the warm key and cool fill off the white cloth: light tintable sprites with
  `lights.rig_sprite(cam, neutral=True)`, and UI tint plates with `lights.rig_ui(..., warm=False)`.
  The warm key tints whites by about +3 R. Check the result with `post.neutral_check(img)`, which
  returns `(mean, p99)` in 8-bit levels and must give a mean of 1 or less and a p99 of 4 or less.
  Measured on a test banner: the neutral rig gives (0.1, 1); the warm rig gives (5.2, 9).
- Do not run Kuwahara with a background behind white tint areas, and do not apply paper grain or
  warmth grading to them.
- Faction colours never appear in art. City sprites use neutral stone and wood.
- Glyph area: write `BannerGlyphArea.txt` from the cloth rectangle that `geometry.banner()`
  returns, projected to pixels with `cameras.world_to_pixel`.

## 9. NPR "paint" shading

`materials.paint(mat, amount=0.35, size=0.85, smooth=0.12)` mixes a Toon BSDF diffuse into any
material, which gives a banded terminator with a soft edge. `paint_all()` applies it to every
material.

| Use | Amount |
|---|---|
| Foliage, terrain props | 0.3 (keeps the trees from looking like soft CG blobs) |
| Architecture | 0.0–0.2 |
| Skin | 0 (use SSS) |

## 10. Sprites: anchoring, shadow and alpha

- **Anchoring.** Anchor to the bottom centre:
  `fit_ortho(cam, [obj], margin_px=1.5, anchor='bottom_center')`. The ground-centre
  alternative is `anchor_world=(0, 0, 0), anchor_px=(48, 92)`. Leave the top of a 96 px city icon
  free for the 32×48 pennant drawn above it.
- **Contact shadow.** Use `post.drop_shadow(img, offset=(2.0, 1.2), blur_px=1.5, opacity=0.35,
  squash=0.5)`, which casts towards the bottom-right. Do not use a shadow catcher: it costs 3× the
  render time and casts long, detached shadows.
- **Alpha.** `post.alpha_cleanup(img, lo=0.03, hi=0.97, bleed=4)` removes dust and bleeds edge
  colour into transparent pixels, so Slate's bilinear filtering never shows dark fringes.
- **Downsampling.** Always use `post.downsample`, which is premultiplied Lanczos.

## 11. Per-family recipes

**World map (2400×1500).**

- Use the `ironart.terrain` recipe from `styleframes/sf_terrain.py`:
  1. Domain-warped land mask
  2. Ridged mountain spines along `meander()` polylines
  3. fbm foothills and hills
  4. Carved river valleys
  5. `paint_albedo` biomes, with thresholds hill 0.10, rock 0.30, snow 0.66 ± 0.05
  6. Coast beach and shallows (shallows width 26 px)
  7. 3D forests via `scatter_forest`: density 0.09, min distance 3.2 px, canopy radius 1.9–2.8 px
- Render the full 2400×1500 map as one 4800×3000 frame, with fields computed at 2× and the mesh at
  1× (`build_terrain(grid_step=2)`). To keep memory low, render it as tiles with camera shift.
- Keep the camera pixel grid identical to the scenario coordinates. Never draw city icons,
  roads or labels into the map.

**City_1 / City_2 / City_3 (96×96).**

- Use `wall_ring`, `gate_tower`, `house`, `hall` and `pagoda`.

| Sprite | Walls | Contents |
|---|---|---|
| City_1 (town) | low palisade or stone ring of about 5 m | 3–4 houses and a small gate |
| City_2 (walled city) | about 6.8×5.6 m | as in the style frame |
| City_3 (great city) | 8.5×7 m, with corner towers | two-storey gate, keep on a podium, and a pagoda for silhouette |

- Use one shared `units_per_px` for all three.

**Banner (64×96) and Flag (32×48).** Use `geometry.banner()` with a `white_cloth` cloth and a dark
wood pole, and the Standard view.

**Sect (64×64).** Use `geometry.pagoda(tiers=3–5)` on a rock with pines.

**Units (96×96).** Build simple figures from the figure kit at small scale (`torso`, `helmet`,
`white_cloth` tabard or flag) on top of `Unit_Base`.

**Hex tiles (128×111).**

- Use r = 1 m, ground hex at 1.12 r, and content inside 0.86 r. Cut the alpha with `post.hex_mask()`.
- Water, Ford and Bridge tiles use `materials.water`. Wall, Gate, Castle and Town reuse the city
  builders at about 0.35 scale.
- `Hex_Fill` and `Hex_Outline` are pure 2D masks: use `post.hex_mask` and an inset difference.

**Battle background, events (640×360), duel background (1280×720), title (1920×1080).**

- Use the map or terrain tools plus architecture. Render at 2× and apply Kuwahara at size 8–10.
- Mist comes from a world gradient plus a compositor blur of a depth-masked layer.

**Portraits (192×240, opaque).**

- Use `ironart.figure`:
  - `head(HeadParams)` is a smooth union of anatomical ellipsoids with lids carved around the
    eyeballs.
  - Then add `ears`, `eyes` (lash line), `eyeballs`, `neck`, and gear: `helmet`, `topknot`,
    `torso`, `pauldrons`, `mirror_plate`, `neck_scarf` and `cape`.
  - Add hair as curves: `beard_strands` (about 10k), `mustache_strands` (900), `brow_strands` (700)
    and `plume_strands` (2.6k).
- Archetype knobs (`HeadParams`):

| Archetype | Settings |
|---|---|
| Warrior | jaw 1.1, brow 1.05, cheekbone 1.15, socket 1.1 |
| Scholar | jaw 0.9, nose_width 0.9, thin `beard_strands(length 0.12, converge 0.9, count 3000)` |
| Elder | age 0.9, `hair_strands(melanin 0.1)` for white hair |
| Female | width 0.142, jaw 0.85, brow 0.6, chin 0.9, lips 1.1, no beard, `topknot` with pins |

- Framing: yaw 20, pitch −4, eye_line 0.38, head_frac 0.6. Use the same lights and background
  recipe for every portrait, so a gallery reads as one set.
- Faces get no ink.

**UI.**

- Build pieces with `geometry.profile_sweep(mb, w, h, r, profile, ...)` from a cross-section
  profile: (inset px, height px) pairs from the outside in, with per-segment materials.
- Keep every ornament inside the 9-slice margins: button 20/16 px, tab the same as the button,
  panel 24 px, scroll 80 px. Check with `post.nine_slice_preview`.
- Lacquer centre fields may use `lacquer(gradient=...)`, which varies only vertically and is
  therefore safe for 9-slicing.
- States:

| State | Change |
|---|---|
| Hover | Lacquer +12 % value |
| Pressed | LacquerDark field, offset 1 px down and right |
| Disabled | desaturated, 60 % value |

- Seals: an extruded square with carved (boolean) glyph faces in Lacquer, with Kuwahara 0 and
  slight paper texture.

## 12. Naming and layout

```
Tools/BlenderArt/
  render.sh                 single entry point
  STYLE.md                  this file
  ironart/                  the library (see the module docstrings)
  styleframes/              the five reference frames + run_all.sh + make_sheet.py
  assets/<family>.py        (to be added by artists) one script per manifest family, e.g.
                            assets/map_cities.py -> Content/Data/Art/Map/City_{1,2,3}.png
```

- Scripts take an optional output directory as their first argument and default to the manifest
  path.
- Intermediates are named `<asset>_raw_<N>x.png` in `$IRONART_OUT/<family>/`.
- Every asset script prints `[ironart] TIMES {...}`.
- Seeds are explicit (`scene.reset(seed=...)`, `random.Random(seed)`), so re-running a script
  gives an identical image.
