"""Headless entry point: runs an asset script inside Blender with consistent setup.

Never call this directly - use ``Tools/BlenderArt/render.sh <script.py> [args...]`` which invokes::

    blender -b --factory-startup -noaudio --python-exit-code 1 \\
            -P Tools/BlenderArt/ironart/run.py -- <script.py> [args...]

What it does
* puts ``Tools/BlenderArt`` on ``sys.path`` (so ``import ironart`` works) and the script's folder
* rewrites ``sys.argv`` so ``ironart.scene.args()`` returns only the script's own arguments
* runs the script as ``__main__`` and times it
* on any exception prints the traceback and exits with status 1 (render.sh reports FAILED);
  ``SystemExit`` codes are propagated
"""

import os
import runpy
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)


def main():
    argv = sys.argv
    rest = argv[argv.index("--") + 1:] if "--" in argv else []
    if not rest:
        print("[ironart] usage: render.sh <script.py> [args...]")
        sys.exit(2)
    script = os.path.abspath(rest[0])
    script_args = rest[1:]
    if TOOLS not in sys.path:
        sys.path.insert(0, TOOLS)
    sdir = os.path.dirname(script)
    if sdir not in sys.path:
        sys.path.insert(0, sdir)
    os.environ.setdefault("IRONART_OUT", "/tmp/ironart")
    sys.argv = [argv[0], "--"] + script_args
    import bpy
    print("[ironart] Blender %s | python %s | script %s %s" % (
        bpy.app.version_string, sys.version.split()[0], os.path.relpath(script), " ".join(script_args)))
    t0 = time.time()
    code = 0
    try:
        runpy.run_path(script, run_name="__main__")
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception:
        traceback.print_exc()
        code = 1
    dt = time.time() - t0
    print("[ironart] %s %s in %.1fs" % ("OK" if code == 0 else "FAILED", os.path.basename(script), dt))
    sys.stdout.flush()
    if code:
        # os._exit: Blender would otherwise keep going / return 0 after a -P script
        os._exit(code)


main()
