"""Shared plumbing for the Battlefield and Units family (paths, flags, report)."""

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
ART_DIR = os.path.join(REPO_DIR, "Content", "Data", "Art", "Battle")
#: previews, contact sheets, textures, reports (never committed)
SCRATCH = os.environ.get("BATTLE_OUT") or os.path.join(os.environ.get("IRONART_OUT") or "/tmp/ironart", "battle")

TERRAINS = ("Plain", "Forest", "Hill", "Mountain", "Water", "Ford", "Bridge", "Road", "Wall", "Gate", "Town",
            "Castle", "Rubble")
NATURAL = ("Plain", "Forest", "Hill", "Mountain", "Water")
UNITS = ("Infantry", "Cavalry", "Archer")


def out(*parts):
    p = os.path.join(SCRATCH, *parts)
    os.makedirs(p, exist_ok=True)
    return p


def flags(argv=None):
    """``--preview`` (fewer samples, smaller bakes), ``--no-render`` (skip review renders),
    ``--no-verify``, plus positional names (terrains, units, steps)."""
    from ironart import scene
    a = scene.args() if argv is None else argv
    return {"preview": "--preview" in a, "render": "--no-render" not in a, "verify": "--no-verify" not in a,
            "names": [x for x in a if not x.startswith("--")]}


class Report:
    def __init__(self, name="report.json"):
        self.path = os.path.join(out(), name)
        self.rows = {}

    def add(self, key, **kw):
        self.rows.setdefault(key, {}).update(kw)

    def save(self):
        old = {}
        if os.path.isfile(self.path):
            try:
                old = json.load(open(self.path))
            except ValueError:
                old = {}
        old.update(self.rows)
        with open(self.path, "w") as f:
            json.dump(old, f, indent=1, default=str)
        return self.path


class Timer:
    def __init__(self):
        self.t0 = time.time()
        self.marks = {}

    def mark(self, k):
        t = time.time()
        self.marks[k] = round(t - self.t0, 1)
        self.t0 = t
