"""Scratch compositions used while tuning the family look (not part of the build)."""

from ironart import icons_kit as K
from ironart import icons_props as P


def Gold(M, cam):
    objs = []
    kw = dict(rim=0.2, wing=0.24, trough=0.12, dome=(0.3, 0.25, 0.3), flare=0.14, W=0.7)
    objs += P.group("ingotA", P.yuanbao("ingA", M["gold"], **kw), (-0.52, 0.32, 0.0), (0, 0, -18))
    objs += P.group("ingotB", P.yuanbao("ingB", M["gold"], **kw), (0.52, 0.38, 0.0), (0, 0, 16))
    objs += P.group("ingotC", P.yuanbao("ingC", M["gold"], **kw), (0.02, -0.32, 0.0), (0, 0, 4),
                    1.12)
    return dict(objs=objs, fill=1.0)


def Food(M, cam):
    kw = dict(rim=0.2, wing=0.24, trough=0.12, dome=(0.3, 0.25, 0.3), flare=0.14, W=0.7)
    return dict(objs=P.yuanbao("ingC", M["gold"], **kw), fill=1.0)
