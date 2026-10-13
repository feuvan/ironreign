# Unreal asset pipeline: ArtSource → /Game/IronReign

This turns the Blender exports in `ArtSource/` into Unreal assets under `/Game/IronReign`: Nanite meshes,
textures, materials and a version marker. The 3D contract is in `docs/DESIGN.md` section 12. The generated
`.uasset` files are build products, so they are never committed. The import is deterministic and keyed to
`ArtSource/manifest.json` `"version"`.

```
Tools/BlenderArt (bpy) ──> ArtSource/  Models/*.glb, Terrain/Albedo.png + Masks.png, Textures/*.png, manifest.json
                                │
Content/Python/ironreign_import.py   (Unreal editor Python)
   started by Content/Python/init_unreal.py on editor start when out of date,
   or by Tools/Unreal/build_assets.sh / build_assets.bat (commandlet -run=pythonscript)
                                │
                                ▼
/Game/IronReign/**   ──>  cooked via DirectoriesToAlwaysCook  ──>  loaded by soft path in Source/IronReign/World
```

| File | Role |
|---|---|
| `Content/Python/ironreign_import.py` | The importer. Its entry point is `build_all(force=False)`. |
| `Content/Python/ironreign_gltf.py` | Pure-Python glTF reader, shared with the CI checker. It reads materials, embedded images and bounds. |
| `Content/Python/init_unreal.py` | Editor startup hook. It imports automatically when the assets are missing or stale. |
| `Tools/Unreal/build_assets.sh`, `build_assets.bat` | Explicit (re)build through `UnrealEditor-Cmd -run=pythonscript`. |
| `Tools/Unreal/run_import.py` | The script the commandlet runs. |
| `Tools/Unreal/check_art_source.py` | Engine-free validation of `ArtSource/` and `Content/Data/Art3D/`. CI runs it. |
| `Source/IronReign/World/IronAssetManifest.h` | `UIronAssetManifest`, the class of the version marker asset. |

## Running it

**Automatically.** Open the project in the editor. On the first Slate tick after the asset registry has
finished scanning, `init_unreal.py` checks the following:

- `ArtSource/manifest.json` exists.
- The marker `/Game/IronReign/IronReignAssetVersion` has the same `ArtVersion` and `PipelineVersion`.
- Every expected asset exists.

If any check fails, it imports and shows a progress dialog. If a build already failed for the same versions,
it does not retry on every start. It logs where to look instead.

**Explicitly** (full rebuild by default):

```bash
Tools/Unreal/build_assets.sh                 # macOS / Linux; --incremental to skip when up to date, --rhi for a GPU RHI
UE_ROOT="/Users/Shared/Epic Games/UE_5.8" Tools/Unreal/build_assets.sh
Tools\Unreal\build_assets.bat                # Windows (UE_ROOT defaults to C:\Program Files\Epic Games\UE_5.8)
```

Build the `IronReignEditor` target first, because the commandlet loads the project module. The scripts look
for the editor in this order:

1. `UE_EDITOR` (the binary itself).
2. `UE_ROOT` (the folder that contains `Engine/`).
3. The usual install locations, such as `/Users/Shared/Epic Games/UE_5.8`, `~/UnrealEngine` and `/home/ue4/UnrealEngine`.

Exit status: 0 = OK, 1 = the import failed, 2 = setup problem (no ArtSource, no editor).

**From the editor's Python console** (Window > Output Log > Python):

```python
import ironreign_import, importlib; importlib.reload(ironreign_import)
ironreign_import.needs_build()          # (bool, reason)
ironreign_import.build_all(force=True)
```

**Results** (every run):

- `Saved/IronReign/asset_version.txt`: a JSON record with versions, every error and warning, the list of
  assets, the engine version, the water shading mode and the scalar parameters of the engine cloud material.
- `Saved/IronReign/asset_build_result.txt`: `OK`, `FAILED` or `SKIPPED`. The build scripts read this file,
  because the commandlet's exit code does not reflect Python errors.

Every log line is prefixed `[IronReign]`.

**Forcing a rebuild / resetting.** Do one of these:

- Run `build_assets.sh` (it forces by default) or `build_all(force=True)`.
- Bump `"version"` in `ArtSource/manifest.json` (every editor re-imports on its next start).
- Bump `PIPELINE_VERSION` in `ironreign_import.py` when you change what the script produces.

For a clean slate, close the editor, then delete `Content/IronReign/` and `Saved/IronReign/`.

## Inputs (`ArtSource/`)

| Path | Notes |
|---|---|
| `manifest.json` | `{"version": N}`. Optional `"normalMapConvention": "opengl"` (default: Blender/glTF; green is flipped on import) or `"directx"`. |
| `Terrain/Albedo.png` | 4800×3000 sRGB, map-aligned. It is stretched to a power of two on import (8192×4096) so it gets mips. Address mode is clamp. |
| `Terrain/Masks.png` | Same size, linear RGBA: R water, G forest floor, B rock/snow altitude, A road (TC_Masks). |
| `Textures/<Name>.png` | Becomes `T_<Name>`. Names ending in `Normal` are normal maps, names ending in `Mask(s)`/`ORM`/`Roughness`/`AO`/`Height` are linear masks, and everything else is sRGB colour. `Water_Normal.png` feeds `M_IronWater`. |
| `Models/<Name>.glb` | One joined mesh object per file, metres, +Z up (exported "+Y up"), origin at the base centre, embedded images, no Draco/meshopt compression. |

Run `python3 Tools/Unreal/check_art_source.py` before importing. It reports these problems without Unreal:

- Missing models.
- Wrong sizes or units.
- Origins away from the base.
- Missing `Tint` slots.
- Untextured (flat-colour) exports.
- Double-sided closed meshes.
- Multi-object files.
- Terrain texture sizes.
- A heightmap that does not match `Terrain.json`.

## Outputs: asset paths for runtime code

Load everything by soft path (`LoadObject` / `FSoftObjectPath`) and null-check it. When the import has not
run, nothing here exists and the game falls back to 2D. Object paths are `<package>.<name>`, for example
`/Game/IronReign/Models/SM_City_2.SM_City_2`.

| Asset | Path |
|---|---|
| Models | `/Game/IronReign/Models/SM_<Name>` for each `ArtSource/Models/<Name>.glb`: `SM_City_1..3`, `SM_Sect`, `SM_Banner`, `SM_Flag`, `SM_Tree_Pine/Broad/Bamboo`, `SM_Unit_Infantry/Cavalry/Archer`, `SM_Unit_Base`, `SM_Hex_<Terrain>` |
| Model materials/textures | `/Game/IronReign/Models/<Name>/MI_<Name>_<glTF material>` and `T_<Name>_<image>` (already assigned to the mesh slots) |
| Plane | `/Game/IronReign/Models/SM_IronPlane` (copy of `/Engine/BasicShapes/Plane`: 1 m × 1 m, UV 0..1, +Z normal) |
| Terrain | `/Game/IronReign/Materials/M_IronTerrain`, `MI_IronTerrain` |
| Water | `/Game/IronReign/Materials/M_IronWater`, `MI_IronWater` |
| Faction tint | `/Game/IronReign/Materials/M_IronTint`, `MI_IronTintInstanced` |
| Selection rings | `/Game/IronReign/Materials/M_IronHighlight`, `MI_IronHighlightHex` |
| Ink post-process | `/Game/IronReign/Materials/M_IronInk` |
| Model masters | `/Game/IronReign/Materials/M_IronModel`, `M_IronModelTwoSided`, `M_IronModelMasked` |
| Seasons | `/Game/IronReign/Materials/MPC_IronSeason` |
| Clouds | `/Game/IronReign/Materials/MI_IronClouds` (parented to `/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud_Inst`, or the plain material if the instance is missing) |
| Textures | `/Game/IronReign/Textures/T_Terrain_Albedo`, `T_Terrain_Masks`, `T_<Name>` (e.g. `T_Water_Normal`), plus the generated defaults `T_IronWhite`, `T_IronWhiteLinear`, `T_IronFlatNormal` |
| Version marker | `/Game/IronReign/IronReignAssetVersion` (`UIronAssetManifest`: `ArtVersion`, `PipelineVersion`, `BuiltAtUtc`, `EngineVersion`, `Models`). It is written last, so its presence means the import completed. |

### Material parameters

| Material | Parameters (default) |
|---|---|
| `M_IronTerrain` | `Albedo`, `Masks` (textures). `MapOrigin` (0,0) and `MapSize` (240000,150000) in cm: the UV comes from world position, not mesh UVs. `Snow`, `Autumn`, `Wetness` (0): the effective value is `max(param, MPC_IronSeason)`. Also `DetailStrength` 0.06, `Roughness` 0.85, `RockRoughness` 0.75, `WetRoughness` 0.45, `SnowRoughness` 0.6, `WaterRoughness` 0.08, `WaterSpecular` 0.6, `WaterDarken` 0.8. |
| `M_IronWater` | Opaque, Single Layer Water shading (default-lit fallback). `NormalA`/`NormalB` (Water_Normal) at `NormalScaleA` 3200 / `NormalScaleB` 1100 cm, panning. `NormalStrength` 0.4, `NormalFadeDistance` 250000. `WaterColor`, `Roughness` 0.05, `Specular` 0.6. `Scattering`, `Absorption`, `DepthFade` 1 (scales the absorption: 0 = clear, >1 = murkier). `PhaseG` 0.1, `ColorScaleBehindWater` 0.9, `SurfaceCoverage` 0 (Opacity = foam coverage). The water shades the scene depth behind it, so put a dark floor under the open sea. |
| `M_IronTint` | `Tint` (white), `Roughness` 0.6, `Metallic` 0, `BaseTex` (white). `UseInstanceColor` 0: when 1 (`MI_IronTintInstanced`), the colour comes from per-instance custom data 0..2 (RGB) of an ISM/HISM, so one component can draw many armies. Two-sided. |
| `M_IronHighlight` | Unlit, translucent, two-sided. `Color` (RGBA; A scales opacity), `Intensity` 4, `RingRadius` 0.82, `RingWidth` 0.1, `FillOpacity` 0.18, `PulseSpeed` 1.2 Hz, `PulseMin` 0.65. `HexShape` 0 is a circle on a UV quad; 1 is a flat-top hex when the quad spans the hex bounding box (8 m × 6.93 m). |
| `M_IronInk` | Post-process, blendable location "Scene Color Before DOF". The tilt-shift blur softens far lines and TSR anti-aliases them. `Strength` 0.6, `Thickness` 1 px at 1080p, `DepthSensitivity` 80, `NormalSensitivity` 1.2, `Threshold` 0.18, `Sharpness` 2.5, `FadeStart` 300000 / `FadeRange` 900000 cm, `InkTone`, `GrainStrength` 0.035, `GrainSize` 2 px. A plain material blendable is not faded by its weight, so fade it with a dynamic instance's `Strength` instead. |
| `M_IronModel*` | Driven per instance from the glTF material: `BaseColorTex`, `BaseColorFactor`, `MetalRoughTex` (G roughness, B metal), `RoughnessFactor`, `MetallicFactor`, `OcclusionTex`/`OcclusionStrength`, `NormalTex`/`NormalStrength`, `EmissiveTex`/`EmissiveFactor`, `AlphaCutoff` (masked). Seasons: `SnowAffect`, `AutumnAffect`, `WetAffect`. Trees and hexes take autumn; units take little snow. |
| `MPC_IronSeason` | `Snow`, `Autumn`, `Wetness` (0..1), `SnowColor`, `AutumnTint`. Set once per world through `UMaterialParameterCollectionInstance`. Every model and the terrain follow it. |

## What the import does with a model

1. It imports the `.glb` with the engine's glTF importer (Interchange) into `/Game/IronReign/Import/<Name>/`,
   then moves the static mesh to `/Game/IronReign/Models/SM_<Name>`. Everything else Interchange made is
   deleted once nothing references it.
2. It reads the `.glb` itself: it extracts the embedded images and imports them with the right colour space
   (base colour/emissive sRGB, metallic-roughness/occlusion TC_Masks, normal TC_Normalmap with green flipped).
   It also builds a `MI_<Name>_<Material>` per glTF material:
   - `alphaMode` MASK/BLEND → `M_IronModelMasked`
   - `doubleSided` → `M_IronModelTwoSided`
   - otherwise → `M_IronModel`

   These masters carry the Nanite and instanced-static-mesh usage flags. Without those flags, a cooked game
   renders HISM trees and Nanite meshes with the default material.
3. It assigns those instances to the mesh slots by glTF material name. Slots named `Tint…` get `M_IronTint`,
   or a `MI_<Name>_Tint` whose `BaseTex` is the glTF base colour texture when the Tint material had one.
   Runtime code tints any slot whose name starts with `Tint` (`IronWorld::ApplyTint`).
4. It checks the size against the glTF bounds (expects ×100, metres → cm) and applies a build scale of 100
   if the importer kept metres.
5. It enables Nanite (preserve area for `Tree_*`) and removes collision. Picking happens in map space;
   set `STRIP_MODEL_COLLISION = False` if you need traces against models.

## Continuous integration

The Unreal Engine job was removed from `.github/workflows/ci.yml`, so the engine is only built locally. The
`data` job compiles these scripts and runs `check_art_source.py`. If an engine job comes back, run the import
after building the editor and before the automation tests and the cook:

```yaml
      - name: Import 3D assets (ArtSource -> /Game/IronReign)
        if: env.HAS_UE_CREDENTIALS == 'true' && hashFiles('ArtSource/manifest.json') != ''
        run: |
          docker run --rm -v "$GITHUB_WORKSPACE:/project" -w /project \
            -e IRONREIGN_IMPORT_FORCE=1 -e IRONREIGN_SKIP_AUTO_IMPORT=1 "$UE_IMAGE" \
            "$UE_ROOT/Engine/Binaries/Linux/UnrealEditor-Cmd" /project/IronReign.uproject \
            -run=pythonscript -script=/project/Tools/Unreal/run_import.py \
            -unattended -nopause -nullrhi -nosplash -nosound -stdout -FullStdOutLogOutput
          test "$(head -n1 Saved/IronReign/asset_build_result.txt)" = OK || { cat Saved/IronReign/asset_version.txt; exit 1; }
```

Also pass `-e IRONREIGN_SKIP_AUTO_IMPORT=1` to the automation-test and cook containers.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Imported models face the wrong way | Set `frontYaw` in `Content/Data/Art3D/Models.json`: the yaw in degrees that turns the model's front towards UE +Y (default 90; try 0, 180 or -90). It is read at runtime, so no re-import is needed. Blender models must face -Y. |
| Models tiny or 100× too big | Export in metres with unit scale 1. The import corrects a metres-for-centimetres glTF import (see the warning `applied a build scale of 100`). Anything else is reported as a size warning. |
| Models are flat-coloured | The Blender materials were not baked to images, so glTF carries only factors. `check_art_source.py` warns about this. |
| Models render grey/checkered in a packaged build but fine in the editor | A slot kept an Interchange material, which has no Nanite/ISM usage flags. Look for `matches no glTF material` in `asset_version.txt` and make the slot names equal to the glTF material names. |
| Bumps look inverted | The normal map is DirectX-style. Set `"normalMapConvention": "directx"` in `manifest.json` and re-import. |
| `N mesh objects` warning, parts missing | Join the objects in Blender (Ctrl+J). The import keeps only the largest static mesh. |
| Startup log: `the last import of ArtSource version N failed` | Read `Saved/IronReign/asset_version.txt` (`errors`), fix them, then run `build_assets.sh` or `build_all(force=True)`. |
| `no ArtSource` / `SKIPPED` | `ArtSource/manifest.json` is missing. Generate it with `Tools/BlenderArt`. The game keeps working in 2D. |
| `UIronAssetManifest is not loaded` | The editor binaries are older than `Source/IronReign/World/IronAssetManifest.h`. Rebuild `IronReignEditor`. Until then the version is kept in `Saved/IronReign/asset_version.txt` only. |
| `the import produced no static mesh` | The glTF importer is disabled. Enable Interchange (default since 5.4) or the GLTFImporter plugin, then re-run. |
| Water looks like flat paint | Single Layer Water needs something underneath to absorb (sea floor). To switch to a plain opaque surface, set `WATER_SHADING = "default_lit"` in `ironreign_import.py` and rebuild. |
| Clouds ignore the coverage parameter | `asset_version.txt` → `notes.cloudScalarParameters` lists the parameter names of the engine cloud material. Use one of them at runtime. |
| A material reports `graph problem(s)` | An engine API or pin name changed. The warnings name the node and pin. Fix `ironreign_import.py` and bump `PIPELINE_VERSION`. |
| Nanite/Lumen missing on Mac | The project targets `SF_METAL_SM6` (Apple silicon, macOS 14+). See `Config/DefaultEngine.ini`. |
