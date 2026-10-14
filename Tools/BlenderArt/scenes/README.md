# Illustrated Scenes family

Painted-realism key art for the title screen, the 12 event illustrations and the duel background,
rendered in Cycles from fully procedural 3D scenes (no image textures, no downloads).

```
Tools/BlenderArt/render.sh Tools/BlenderArt/scenes/build.py                 # everything (final)
Tools/BlenderArt/render.sh Tools/BlenderArt/scenes/build.py --only Court    # one scene
Tools/BlenderArt/render.sh Tools/BlenderArt/scenes/build.py --only Title --preview --scale 0.25
python3 Tools/BlenderArt/scenes/make_sheet.py $IRONART_OUT/scenes/preview   # contact sheet
```

| Output | Size | Master |
|---|---|---|
| `Content/Data/Art/UI/Title_Background.png` | 1920x1080 | `ArtSource/UI/Title_Background@2x.png` 3840x2160 |
| `Content/Data/Art/Events/<Name>.png` (12) | 640x360 | `ArtSource/Events/<Name>@2x.png` 1280x720 |
| `Content/Data/Art/Duel/Background.png` | 1280x720 | none |

## Pipeline (per scene, `build.py`)

1. `sc_<name>.py: build(r)` builds the scene with the family kit:
   * `ironart/scenes_sky.py` - art-directed sky dome (gradient, sun/moon glows and discs, perspective
     cloud decks, stars, comet) and `IR_Fog`: exponential height haze coloured by the sky along the
     view ray + low valley mist, inserted in front of every material (camera and glossy rays only).
   * `ironart/scenes_terrain.py` - coordinate noise (one height function shared by several meshes),
     heightfield meshes, terrain / rock / water materials in world space, mist cards.
   * `ironart/scenes_flora.py` - leaf-cluster broadleaf trees, Chinese pines (instanced) and the
     close-up `fine_pine` (needle-tuft "cloud" pads), weeping willows (hanging leaf strands), firs,
     bamboo, plum in blossom, dead trees, grass; geometry-nodes instancing with per-instance
     kind / rotation / scale.
   * `ironart/scenes_people.py` - posable figures (robes draped over the posed legs, hanging sleeves,
     armour, capes, hats, weapons, banners, torches, lanterns), horses, riders.
   * `ironart/scenes_arch.py` + the World Models kit `ironart/world_kit.py` / `world_mats.py`
     (halls with brackets, gate towers, walls, pagodas, houses) at real scale.  `wk_build` maps the
     kit's bake-suffixed slots (`W_Lacquer~d`, `W_Tile~row`) to their base materials.
2. Cycles CPU, Filmic / Medium Contrast (Title: Medium High Contrast), adaptive sampling (0.02);
   beauty + albedo/normal/depth to EXR.  Samples per scene (`SPEC["spp"]`): Court / Festival 32,
   the night and storm scenes 28, daylight events 20, Duel 24, Title 8 (at 3840x2160).
3. Edge-avoiding a-trous denoise (`scenes_look.denoise`; this Blender build has no OIDN).
4. Post compositor scene: sun beams from the light source, fog glow, anisotropic Kuwahara brush
   (strokes grow with depth: painters simplify the distance).
5. numpy finish (`scenes_look.finish`): split-tone grade, clarity, vignette, canvas grain, sharpen,
   dithered 8-bit; 1x = Lanczos downsample of the master; saved through `post.save_asset`.

Masters are registered in `ArtSource/manifest.json` (`files`, version bumped under a lock).
