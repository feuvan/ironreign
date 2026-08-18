# Iron Reign

Iron Reign is a single-player wuxia/warlord RPG built with Unreal Engine 5.8 for PC and macOS.

The first milestone is a small vertical slice: one town, one wilderness area, one faction, one school, a recruitable character, a data-driven event, a tactical encounter, and save/load.

## Getting started

1. Install Unreal Engine 5.8 with the C++ toolchain for the target platform.
2. Open `IronReign.uproject` in Unreal Editor. Allow the editor to generate project files if prompted.
3. Create `/Game/Maps/L_Main` in the editor, or temporarily change the default map in `Config/DefaultEngine.ini`.
4. Enable the included Enhanced Input, Gameplay Tags, Gameplay Ability System, and Gameplay Tasks plugins.

For a source build, generate project files from the context menu for `IronReign.uproject`, then build the `IronReignEditor` target for the chosen platform. The target files are shared by Windows and macOS; platform-specific packaging settings should be added only when the first playable slice is ready.

The repository intentionally starts without generated `Binaries`, `Intermediate`, `DerivedDataCache`, or `Saved` directories.

## Targets

- Desktop: PC and macOS
- Game type: single-player, systems-driven RPG
- Initial combat direction: small-scale tactical encounters

## Project layout

```text
Source/IronReign/
  Characters/                  Data assets for actors and future progression
  IronReignGameMode.*           Default runtime game mode
  IronReignWorldStateSubsystem.*
                               World time and simulation entry point
```
