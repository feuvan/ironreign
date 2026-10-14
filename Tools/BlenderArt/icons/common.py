"""Icons family: the shared material set (one look for all 40 icons).

``M()`` returns a lazily-filled dict-like accessor: ``M()["gold"]`` builds the material on first
use and caches it for the scene (``scene.reset`` wipes it between icons).
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from ironart import icons_mats as im  # noqa: E402
from ironart import REPO_DIR  # noqa: E402

FONT_BRUSH = os.path.join(REPO_DIR, "Content", "Data", "Fonts", "Brush.ttf")
FONT_SC = os.path.join(REPO_DIR, "Content", "Data", "Fonts", "CJK-SC-Bold.ttf")

#: material key -> (factory, kwargs)
LIBRARY = {
    "gold": (im.gold, dict(name="I_Gold", color="#F4C25E", rough=0.24)),
    "gold_old": (im.gold, dict(name="I_GoldOld", color="#D9A84E", rough=0.3, worn=0.5)),
    "bronze": (im.bronze, dict(name="I_Bronze", color="#B8894A", patina_amt=0.28)),
    "bronze_clean": (im.bronze, dict(name="I_BronzeClean", color="#C29152", patina_amt=0.08,
                                      rough=0.24)),
    "copper": (im.bronze, dict(name="I_Copper", color="#B87A4A", patina="#3E7A66",
                                patina_amt=0.22, rough=0.32, pscale=9.0)),
    "steel": (im.steel, dict(name="I_Steel", color="#C8CCD2", rough=0.18)),
    "iron": (im.iron, dict(name="I_Iron", color="#60646B", rough=0.4)),
    "iron_dark": (im.iron, dict(name="I_IronDark", color="#3E4248", rough=0.45, rust_amt=0.1)),
    "lacquer_red": (im.lacquer, dict(name="I_LacquerRed", color="#9A2416", rough=0.4)),
    "lacquer_dark": (im.lacquer, dict(name="I_LacquerDark", color="#5A140E", rough=0.4)),
    "lacquer_black": (im.lacquer, dict(name="I_LacquerBlack", color="#1C1612", rough=0.35,
                                        vary=0.02)),
    "wood": (im.wood, dict(name="I_Wood", color="#8A5C36", grain="#55361F", axis="Z")),
    "wood_x": (im.wood, dict(name="I_WoodX", color="#8A5C36", grain="#55361F", axis="X")),
    "wood_y": (im.wood, dict(name="I_WoodY", color="#8A5C36", grain="#55361F", axis="Y")),
    "wood_dark": (im.wood, dict(name="I_WoodDark", color="#5A3A22", grain="#33200F", axis="Z",
                                 coat=0.35)),
    "wood_dark_x": (im.wood, dict(name="I_WoodDarkX", color="#5A3A22", grain="#33200F",
                                   axis="X", coat=0.35)),
    "wood_pale": (im.wood, dict(name="I_WoodPale", color="#B8925E", grain="#8A6436", axis="Z")),
    "wood_pale_x": (im.wood, dict(name="I_WoodPaleX", color="#B8925E", grain="#8A6436",
                                   axis="X")),
    "bamboo": (im.bamboo, dict(name="I_Bamboo", color="#B89A58")),
    "jade": (im.jade, dict(name="I_Jade", color="#4E9A72")),
    "silk_red": (im.silk, dict(name="I_SilkRed", color="#B02A1C")),
    "silk_gold": (im.silk, dict(name="I_SilkGold", color="#D2A23E", sheen=0.7)),
    "silk_blue": (im.silk, dict(name="I_SilkBlue", color="#2E4E86")),
    "silk_green": (im.silk, dict(name="I_SilkGreen", color="#3E7A52")),
    "silk_white": (im.silk, dict(name="I_SilkWhite", color="#ECE6DA", sheen=0.5, sss=0.2)),
    "silk_black": (im.silk, dict(name="I_SilkBlack", color="#26201C", sheen=0.8)),
    "paper": (im.paper, dict(name="I_Paper", color="#EADFC4")),
    "straw": (im.straw, dict(name="I_Straw")),
    "hemp": (im.hemp, dict(name="I_Hemp")),
    "celadon": (im.ceramic, dict(name="I_Celadon", color="#9CBBA0", pool="#5E8A6A",
                                  crackle=0.35)),
    "porcelain": (im.ceramic, dict(name="I_Porcelain", color="#ECE8DE", pool="#B8BCB8")),
    "stoneware": (im.stoneware, dict(name="I_Stoneware")),
    "stone": (im.stone, dict(name="I_Stone")),
    "masonry": (im.masonry, dict(name="I_Masonry")),
    "plaster": (im.plaster, dict(name="I_Plaster")),
    "roof": (im.roof_tile, dict(name="I_Roof")),
    "rope_red": (im.rope, dict(name="I_RopeRed", color="#A42A1C")),
    "rope_straw": (im.rope, dict(name="I_RopeStraw", color="#B89858", sheen=0.2, rough=0.8)),
    "rope_gold": (im.rope, dict(name="I_RopeGold", color="#D0A040", sheen=0.8)),
    "hide": (im.hide, dict(name="I_Hide")),
    "leather": (im.leather, dict(name="I_Leather")),
    "feather": (im.feather, dict(name="I_Feather")),
    "flame": (im.flame, dict(name="I_Flame")),
    "cloud": (im.cloud, dict(name="I_Cloud")),
    "rice": (im.plain, dict(name="I_Rice", color="#F2EEE4", rough=0.45, sss=0.3)),
    "ink": (im.plain, dict(name="I_Ink", color="#1A1410", rough=0.5)),
    "vermilion": (im.plain, dict(name="I_Vermilion", color="#C0301E", rough=0.6)),
}


class _Lib(dict):
    def __missing__(self, key):
        fn, kw = LIBRARY[key]
        m = fn(**kw)
        self[key] = m
        return m


def M():
    return _Lib()
