"""Commandlet entry point of the Iron Reign asset import (see Tools/Unreal/README.md).

    UnrealEditor-Cmd IronReign.uproject -run=pythonscript -script=<repo>/Tools/Unreal/run_import.py

Environment: IRONREIGN_IMPORT_FORCE=0 imports only when out of date (default 1 = rebuild everything).
The outcome is written to Saved/IronReign/asset_build_result.txt (OK / FAILED / SKIPPED), which
build_assets.sh / build_assets.bat check because the commandlet's exit code does not reflect Python errors.
"""

import os
import sys
import traceback

import unreal


def _ironreign_content_python_dir():
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        return os.path.normpath(os.path.join(here, "..", "..", "Content", "Python"))
    except NameError:
        project = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
        return os.path.normpath(os.path.join(project, "Content", "Python"))


def _ironreign_main():
    content_python = _ironreign_content_python_dir()
    if content_python not in sys.path:
        sys.path.insert(0, content_python)
    import ironreign_import

    force = os.environ.get("IRONREIGN_IMPORT_FORCE", "1") not in ("0", "false", "no")
    ok = ironreign_import.build_all(force=force)
    unreal.log("[IronReign] run_import.py finished: %s" % ("OK" if ok else "FAILED or SKIPPED"))


try:
    _ironreign_main()
except Exception as _ironreign_exc:
    unreal.log_error("[IronReign] run_import.py failed: %s\n%s" % (_ironreign_exc, traceback.format_exc()))
    try:
        _ironreign_saved = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_saved_dir()),
                                        "IronReign")
        os.makedirs(_ironreign_saved, exist_ok=True)
        with open(os.path.join(_ironreign_saved, "asset_build_result.txt"), "w", encoding="utf-8") as _handle:
            _handle.write("FAILED\n")
    except Exception:
        pass
