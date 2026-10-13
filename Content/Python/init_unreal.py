"""Iron Reign editor startup hook.

Unreal runs every ``init_unreal.py`` found in a ``Content/Python`` folder when the Python plugin starts. On a normal
editor start this imports ArtSource/ into /Game/IronReign when the assets are missing or stale
(``ironreign_import.should_auto_build()``). The work is deferred to the first Slate tick after the asset registry
finished scanning, so the editor is fully up and a progress dialog can be shown.

Skipped for commandlets (cook, ``-run=pythonscript`` from Tools/Unreal/build_assets.sh, which imports explicitly),
``-game``/``-server`` runs, unattended runs and when ``IRONREIGN_SKIP_AUTO_IMPORT=1`` is set.
"""

import os
import re

import unreal

_ironreign_tick_handle = None


def _ironreign_command_line():
    try:
        return str(unreal.SystemLibrary.get_command_line()).lower()
    except Exception:
        return ""


def _ironreign_skip_reason():
    if os.environ.get("IRONREIGN_SKIP_AUTO_IMPORT", "") not in ("", "0"):
        return "IRONREIGN_SKIP_AUTO_IMPORT is set"
    match = re.search(r"(?:^|\s)(-run=|-game\b|-server\b|-unattended\b|-nullrhi\b)", _ironreign_command_line())
    if match:
        return "the editor was started with %s" % match.group(1)
    try:
        if unreal.SystemLibrary.is_unattended():
            return "unattended run"
    except Exception:
        pass
    if not hasattr(unreal, "EditorAssetLibrary") or not hasattr(unreal, "MaterialEditingLibrary"):
        return "editor scripting is not available (enable PythonScriptPlugin and EditorScriptingUtilities)"
    return None


def _ironreign_unregister():
    global _ironreign_tick_handle
    if _ironreign_tick_handle is not None:
        try:
            unreal.unregister_slate_post_tick_callback(_ironreign_tick_handle)
        except Exception:
            pass
        _ironreign_tick_handle = None


def _ironreign_on_tick(delta_seconds):
    try:
        if unreal.AssetRegistryHelpers.get_asset_registry().is_loading_assets():
            return  # wait until the asset registry knows every existing /Game/IronReign asset
    except Exception:
        pass
    _ironreign_unregister()
    try:
        import ironreign_import

        wanted, reason = ironreign_import.should_auto_build()
        if not wanted:
            unreal.log("[IronReign] 3D asset import not needed: %s" % reason)
            return
        unreal.log("[IronReign] importing ArtSource into /Game/IronReign: %s" % reason)
        ironreign_import.build_all(force=False)
    except Exception as exc:
        unreal.log_error("[IronReign] automatic 3D asset import failed: %s" % exc)


def _ironreign_startup():
    global _ironreign_tick_handle
    reason = _ironreign_skip_reason()
    if reason is not None:
        unreal.log("[IronReign] automatic 3D asset import skipped: %s" % reason)
        return
    try:
        _ironreign_tick_handle = unreal.register_slate_post_tick_callback(_ironreign_on_tick)
    except Exception as exc:
        unreal.log_warning("[IronReign] cannot schedule the 3D asset import: %s" % exc)


try:
    _ironreign_startup()
except Exception as _ironreign_exc:
    unreal.log_error("[IronReign] init_unreal.py failed: %s" % _ironreign_exc)
