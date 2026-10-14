"""Shared plumbing for the World Models scripts (output folders, flags, timing, reporting)."""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from ironart import REPO_DIR  # noqa: E402

MODELS_DIR = os.path.join(REPO_DIR, "ArtSource", "Models")
#: previews, contact sheets and intermediate textures (never committed)
SCRATCH = os.environ.get("WORLD_MODELS_OUT") or os.path.join(
    os.environ.get("IRONART_OUT") or "/tmp/ironart", "world_models")


def out(*parts):
    p = os.path.join(SCRATCH, *parts)
    os.makedirs(p, exist_ok=True)
    return p


def flags(argv=None):
    """``--preview`` (fast: smaller bakes, fewer samples), ``--no-render`` (skip review renders),
    plus positional model names."""
    from ironart import scene
    a = scene.args() if argv is None else argv
    return {"preview": "--preview" in a, "render": "--no-render" not in a,
            "names": [x for x in a if not x.startswith("--")]}


class Report:
    """Collects per-model facts and writes ``report.json`` next to the previews."""

    def __init__(self):
        self.rows = {}
        self.t0 = time.time()

    def add(self, name, **kw):
        self.rows.setdefault(name, {}).update(kw)

    def save(self):
        p = os.path.join(out(), "report.json")
        old = {}
        if os.path.isfile(p):
            try:
                old = json.load(open(p))
            except ValueError:
                old = {}
        old.update(self.rows)
        with open(p, "w") as f:
            json.dump(old, f, indent=1, default=str)
        return p
