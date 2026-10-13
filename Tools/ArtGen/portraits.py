#!/usr/bin/env python3
"""Procedural officer portraits for Iron Reign (see docs/DESIGN.md section 8).

Generates Content/Data/Art/Portraits/<id>.png (192x240, opaque) for every
portrait id, plus unknown.png and manifest.json.  Fully deterministic: every
portrait is seeded from a CRC of its id, so re-running reproduces the same
files.

Each portrait is assembled from a seeded parts system (face shape, skin,
eyes, brows, nose, mouth, facial hair, hair, headgear, clothing, accessories)
and painted with numpy: a yawed 3D head model gives a height field that is
lit from the top-left, shapes are shaded with soft "pillow" lighting, ink
outlines are traced from mask edges, and a paper texture and vignette are
applied before downsampling from 3x.

Usage:
    python3 Tools/ArtGen/portraits.py                 # everything
    python3 Tools/ArtGen/portraits.py --only m_warrior_01,f_scholar_03
    python3 Tools/ArtGen/portraits.py --sheet /tmp/sheet.png   # also write a contact sheet
    python3 Tools/ArtGen/portraits.py --jobs 4
"""
import argparse
import json
import os
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from portrait_raster import (Canvas, hexc, ink_outline, poly, ellipse, catmull, blur, grid,  # noqa: E402
                             clamp01, smoothstep, value_noise, W, H, SCALE)
from portrait_head import Head  # noqa: E402
from portrait_face import (render_skin, draw_eyes, draw_brows, draw_nose, draw_mouth, draw_ear,  # noqa: E402
                           draw_wrinkles, INK)
from portrait_dress import (draw_background, finish, Body, draw_robe, hair_colors, draw_hair_cap,  # noqa: E402
                            topknot_point, draw_bun, draw_loose_back, draw_beard, draw_moustache,
                            flow_strands, paint_hair_mass)
import portrait_gear as gear  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
OUT_DIR = os.path.join(REPO, 'Content', 'Data', 'Art', 'Portraits')

ARCHETYPES = [
    ('m', 'warrior', 30),
    ('m', 'scholar', 20),
    ('m', 'elder', 12),
    ('m', 'monk', 6),
    ('m', 'rogue', 10),
    ('f', 'warrior', 10),
    ('f', 'scholar', 10),
    ('f', 'elder', 4),
]

SKINS = ['#DDBC9C', '#D6B190', '#CFA784', '#C79C78', '#BC8F6A', '#AF835E', '#A27654']
SKIN_NAMES = ['fair', 'fair', 'light', 'light', 'tanned', 'tanned', 'bronzed']
HAIR = [('#1B1613', 'black'), ('#211A16', 'black'), ('#2A2019', 'dark brown'), ('#33261D', 'brown')]

ROBES = {
    'indigo': '#2E3F5C', 'slate': '#465666', 'jade': '#3F6E5A', 'pine': '#34503F', 'umber': '#5A3A2E',
    'crimson': '#6E2620', 'plum': '#4E3A56', 'olive': '#5E5A40', 'black': '#24211E', 'ochre': '#86703F',
    'tan': '#8C7A5C', 'grey': '#5C5852', 'teal': '#2F5A5A', 'wine': '#5A2430', 'navy': '#232F45',
}
FEM_ROBES = {
    'rose': '#9A5A56', 'mauve': '#80637A', 'sky': '#62788E', 'sage': '#6E7E62', 'cream': '#D8CDB6',
    'apricot': '#B07A58', 'lilac': '#7A6E92', 'teal': '#3F6E6A', 'crimson': '#7E2A24', 'ivory': '#E2D8C6',
    'peony': '#A8485A', 'jade': '#4F7E68',
}
BANDS = {'black': '#1E1A16', 'gold': '#8E7442', 'white': '#E4DCCB', 'red': '#7E1F17', 'brown': '#4A3324',
         'blue': '#2E3F5C', 'green': '#2F4A3A'}
INNER = ['#E4DCCB', '#D8D0C0', '#E4DCCB', '#E4DCCB']
CLOTH_ACCENT = {'red': '#8A2A1E', 'blue': '#2E3F5C', 'green': '#2F5A44', 'ochre': '#8A6A2E', 'black': '#24201C',
                'purple': '#4E3456', 'white': '#D8D0C0'}


def seeded(pid, salt=''):
    return np.random.default_rng(zlib.crc32((pid + salt).encode('utf-8')))


def deal(name, options, n):
    """Spread options over n slots (repeating, shuffled deterministically)."""
    rng = seeded(name, 'deal')
    out = []
    while len(out) < n:
        block = list(options)
        rng.shuffle(block)
        out.extend(block)
    return out[:n]


# ----------------------------------------------------------------------
# Parameter generation
# ----------------------------------------------------------------------

def face_params(rng, gender, age, archetype):
    u = rng.uniform
    male = gender == 'm'
    p = dict(ye=91.0, yaw=27.0)
    if male:
        p['hu'] = u(59.5, 61.5)
        p['w_cran'] = u(0.74, 0.78)
        p['w_zyg'] = u(0.73, 0.78)
        p['w_cheek'] = p['w_zyg'] - u(0.02, 0.06)
        strong = archetype in ('warrior', 'rogue')
        p['w_jaw'] = u(0.6, 0.69) if strong else u(0.55, 0.64)
        p['w_chin'] = u(0.26, 0.33) if strong else u(0.22, 0.29)
        p['vshape'] = u(0.7, 1.1) if strong else u(0.9, 1.3)
        p['chin_f'] = u(-0.02, 0.05)
        p['eye_w'] = u(0.13, 0.155)
        p['eye_h'] = u(0.058, 0.08)
        p['eye_tilt'] = u(-0.005, 0.045)
        p['lid_w'] = u(1.1, 1.4)
        p['brow_t'] = u(0.075, 0.11) if strong else u(0.06, 0.09)
        p['brow_arch'] = u(0.015, 0.05)
        p['brow_tilt'] = u(0.0, 0.09) if strong else u(-0.02, 0.05)
        p['nose_p'] = u(0.15, 0.21)
        p['nose_w'] = u(0.12, 0.16)
        p['mouth_u'] = u(0.26, 0.32)
        p['lip_full'] = u(0.75, 1.1)
        p['rosy'] = u(0.25, 0.55)
        p['crease'] = u(0.0, 0.7)
    else:
        p['hu'] = u(56.5, 58.5)
        p['w_cran'] = u(0.74, 0.77)
        p['w_zyg'] = u(0.71, 0.75)
        p['w_cheek'] = p['w_zyg'] - u(0.03, 0.06)
        p['w_jaw'] = u(0.52, 0.58)
        p['w_chin'] = u(0.19, 0.24)
        p['vshape'] = u(1.15, 1.5)
        p['chin_f'] = u(-0.03, 0.02)
        p['eye_w'] = u(0.15, 0.17)
        p['eye_h'] = u(0.072, 0.09)
        p['eye_tilt'] = u(0.025, 0.06)
        p['lid_w'] = u(1.35, 1.6)
        p['lid_flick'] = -u(0.01, 0.03)
        p['brow_t'] = u(0.035, 0.05)
        p['brow_arch'] = u(0.04, 0.07)
        p['brow_tilt'] = u(-0.01, 0.03)
        p['brow_len'] = u(1.0, 1.15)
        p['nose_p'] = u(0.12, 0.15)
        p['nose_w'] = u(0.1, 0.12)
        p['mouth_u'] = u(0.21, 0.25)
        p['lip_full'] = u(1.1, 1.35)
        p['rosy'] = u(0.6, 0.9)
        p['crease'] = u(0.3, 0.9)
        p['lip'] = ['#9E4A44', '#A8524A', '#94403C', '#B05A50'][int(u(0, 4))]
    p['xc'] = 92.0 + u(-1.5, 1.5)
    p['jaw_y'] = u(0.58, 0.66)
    p['front'] = u(0.62, 0.66)
    p['chin'] = u(0.96, 1.04) if male else u(0.95, 1.0)
    p['eye_u'] = u(0.42, 0.46)
    p['brow_y'] = u(-0.24, -0.19)
    p['nose_y'] = u(0.36, 0.42) if male else u(0.35, 0.39)
    p['mouth_y'] = p['nose_y'] + u(0.24, 0.29)
    p['mouth_curve'] = u(-0.015, 0.02)
    p['gaze'] = u(-0.35, 0.05)
    p['iris'] = ['#2B1D14', '#33231A', '#261A12', '#3A2A1C'][int(u(0, 4))]
    p['iris_r'] = u(0.45, 0.52)
    if age == 'young':
        p['age'] = u(0.0, 0.1)
    elif age == 'adult':
        p['age'] = u(0.2, 0.42)
    else:
        p['age'] = u(0.65, 1.0)
        p['hollow'] = u(0.4, 1.0)
        p['nasolabial'] = u(0.8, 1.4)
        p['mouth_curve'] = u(-0.03, 0.0)
        p['eye_h'] *= 0.85
    if 'nasolabial' not in p:
        p['nasolabial'] = 0.2 + 0.6 * p['age']
    return p


def pick(rng, seq):
    return seq[int(rng.integers(0, len(seq)))]


def skin_for(rng, gender, archetype):
    if gender == 'f':
        i = int(np.clip(rng.normal(1.5, 1.2), 0, 4))
    elif archetype in ('warrior', 'rogue'):
        i = int(np.clip(rng.normal(3.6, 1.4), 0, 6))
    else:
        i = int(np.clip(rng.normal(2.6, 1.4), 0, 6))
    return SKINS[i], SKIN_NAMES[i]


def make_params(pid, gender, arch, idx, slots):
    """Build the full parameter set for one portrait.  `slots` holds the
    pre-dealt major visual choices for this index."""
    rng = seeded(pid)
    s = slots
    age = s['age']
    fp = face_params(rng, gender, age, arch)
    skin, skin_name = skin_for(rng, gender, arch)
    fp['skin'] = skin
    hair_hex, hair_name = pick(rng, HAIR)
    grey = 0.0
    if age == 'old':
        grey = rng.uniform(0.75, 1.0) if arch != 'warrior' else rng.uniform(0.6, 1.0)
        hair_name = 'white' if grey > 0.88 else 'grey'
    elif age == 'adult' and rng.uniform() < 0.12 and gender == 'm':
        grey = rng.uniform(0.25, 0.4)
        hair_name = 'greying'
    p = dict(id=pid, gender=gender, archetype=arch, age=age, face=fp, skin_name=skin_name,
             hair_hex=hair_hex, hair_name=hair_name, grey=grey)
    p.update({k: v for k, v in s.items() if k != 'age'})
    p['hair'] = dict(hairline=rng.uniform(-0.66, -0.58), recede=0.0, sideburn=rng.uniform(0.0, 0.12),
                     thick=rng.uniform(2.0, 3.0), knot_y=rng.uniform(-1.02, -0.94), knot_z=rng.uniform(-0.5, -0.36))
    if age == 'old' and gender == 'm':
        p['hair']['recede'] = rng.uniform(0.3, 1.0)
        p['hair']['hairline'] = rng.uniform(-0.62, -0.52)
    # clothing colours
    if gender == 'f':
        outer = pick(rng, list(FEM_ROBES))
        p['robe_name'] = outer
        mid_c = pick(rng, ['#E4DCCB', '#7E1F17', '#C9A24A', '#3F6E5A', '#2E3F5C', '#A8485A'])
        band = pick(rng, ['#3A2A24', '#7E1F17', '#C9A24A', '#E4DCCB', '#2E3F5C', '#5A2430'])
        p['layers'] = [('#E8E0D0', '#E8E0D0'), (mid_c, mid_c), (FEM_ROBES[outer], band)]
    else:
        outer = pick(rng, list(ROBES))
        p['robe_name'] = outer
        mid_c = pick(rng, ['#E4DCCB', '#7E1F17', '#2E3F5C', '#3F5A4A', '#C9A24A', '#5A3A2E'])
        band = BANDS[pick(rng, ['black', 'black', 'gold', 'white', 'red', 'brown', 'blue', 'green'])]
        if band == ROBES[outer]:
            band = BANDS['black']
        p['layers'] = [('#E4DCCB', '#E4DCCB'), (mid_c, mid_c), (ROBES[outer], band)]
    p['seed_extra'] = int(rng.integers(0, 2 ** 31))
    finalize_specific(p, rng)
    return p


def finalize_specific(p, rng):
    """Archetype-specific refinements (armour colours, helmets, ornaments)."""
    arch, gender = p['archetype'], p['gender']
    u = rng.uniform
    fp = p['face']
    if p.get('armour'):
        a = dict(metal=p['armour'], trim=pick(rng, ['gold', 'gold', 'bronze', 'steel']),
                 cord=CLOTH_ACCENT[p.get('accent', 'red')], mirror=bool(p.get('mirror', False)),
                 open_depth=u(0.55, 0.7), rivets=bool(u() < 0.4))
        if p['armour'] in ('bronze', 'gold'):
            a['trim'] = 'steel' if u() < 0.5 else 'gold'
        if p['armour'] in ('redlac', 'leather', 'black'):
            a['cord'] = pick(rng, ['#C9A24A', '#2E3F5C', '#8A2A1E'])
        if gender == 'f':
            a['lames'] = 2
            a['pw'] = 0.085
            a['ph'] = 0.11
        a['gorget'] = 'cloth' if u() < 0.35 else 'trim'
        a['cloth'] = CLOTH_ACCENT[p.get('accent', 'red')]
        p['armour_p'] = a
        acc = CLOTH_ACCENT[p.get('accent', 'red')]
        p['layers'] = [('#E4DCCB', '#E4DCCB'), (acc, acc), (acc, acc)]
    hg = p.get('headgear', 'topknot')
    if hg.startswith('helmet'):
        p['helmet_p'] = dict(metal=p.get('helmet_metal', p.get('armour', 'iron')), trim=p.get('armour_p', {}).get('trim', 'gold'),
                             plume={'helmet_tassel': 'tassel', 'helmet_feathers': 'feathers', 'helmet_plain': None}[hg],
                             plume_col=pick(rng, ['#9A2A1E', '#9A2A1E', '#7E1F17', '#B0402A', '#2A2622']),
                             flap_style=pick(rng, ['lamellar', 'lamellar', 'cloth']),
                             flap_col=CLOTH_ACCENT[p.get('accent', 'red')],
                             ribs=pick(rng, [0, 0, 6, 8]), crest=bool(u() < 0.7),
                             brim=u(-0.52, -0.46))
        if p['helmet_p']['metal'] in ('leather', 'redlac'):
            p['helmet_p']['metal'] = pick(rng, ['iron', 'steel', 'black'])
    if hg in ('headband', 'headband_jewel'):
        p['band_p'] = dict(band_col=pick(rng, ['#8E2A20', '#7E1F17', '#24201C', '#2E3F5C', '#D8D0C0', '#3F5A4A', '#8A6A2E']),
                           band_y=u(-0.56, -0.48), band_h=u(0.09, 0.12), band_jewel=(hg == 'headband_jewel'),
                           jewel_col=pick(rng, ['#3F6E5A', '#B03A2E', '#2E3F5C']), tails=bool(u() < 0.8))
    if hg in ('guan_black', 'guan_gold'):
        p['guan_p'] = dict(guan_col='black' if hg == 'guan_black' else 'gold',
                           guan_trim=pick(rng, ['gold', 'bronze', 'black']), pin_jewel=pick(rng, [None, '#3F6E5A', '#B03A2E']))
    if hg in ('cloth_cap', 'headscarf'):
        cols = ['#2E3F5C', '#24201C', '#3F5A4A', '#D8D0C0', '#5A3A2E', '#465666'] if hg == 'cloth_cap' else \
            ['#5A3A2E', '#3A3530', '#6A2A22', '#4A4A3A', '#2E3F5C']
        p['cap_p'] = dict(cap_col=pick(rng, cols), cap_edge=u(-0.55, -0.45), cap_ties=bool(u() < 0.85))
    if hg == 'tall_hat':
        p['hat_p'] = dict(hat_h=u(0.6, 0.85), hat_trim=pick(rng, [None, 'gold']))
    if hg == 'hood':
        p['hood_p'] = dict(hood_col=pick(rng, ['#4A3A2E', '#3A3A34', '#2E3A44', '#5A4A38', '#2A2622', '#4A3030']),
                           hood_top=u(-0.5, -0.42))
    # female hair & ornaments
    if gender == 'f':
        hs = p.get('hairstyle', 'high_bun')
        hp = p['hair']
        hp['style'] = hs
        hp['sideburn'] = u(0.0, 0.08)
        hp['hairline'] = u(-0.64, -0.6)
        if hs in ('high_bun', 'double_bun'):
            hp['knot_y'], hp['knot_z'] = u(-1.12, -1.05), u(-0.42, -0.3)
        elif hs == 'low_bun':
            hp['knot_y'], hp['knot_z'] = u(-0.25, -0.12), u(-1.08, -1.0)
        elif hs == 'ponytail':
            hp['knot_y'], hp['knot_z'] = u(-0.98, -0.9), u(-0.75, -0.6)
            hp['ribbon'] = pick(rng, ['#8E2A20', '#2E3F5C', '#D8D0C0', '#3F5A4A'])
        else:
            hp['knot_y'], hp['knot_z'] = u(-0.95, -0.85), u(-0.7, -0.55)
            hp['length'] = u(0.9, 1.3)
        hp['orn_metal'] = pick(rng, ['gold', 'gold', 'bronze', 'steel'])
        hp['jewel'] = pick(rng, ['#3F6E5A', '#A8423A', '#2E3F5C', '#C9A24A'])
        hp['flower_col'] = pick(rng, ['#B5524A', '#C98A8A', '#D8C8B8', '#A8485A'])
        hp['flower_col2'] = pick(rng, ['#E0D2C0', '#C98A8A', '#D9B54A'])
        hp['band_col'] = pick(rng, ['#7E1F17', '#2E3F5C', '#24201C'])
        hp['ornaments'] = p.get('ornaments', [])
    if p['archetype'] == 'monk':
        p['bead_p'] = dict(bead_col=pick(rng, ['#4A2E1C', '#3A2418', '#6A4A2A', '#2A1E16']), bead_r=u(0.065, 0.085),
                           tassel_col=pick(rng, ['#8A2A1E', '#C9A24A', '#3F6E5A']))
        p['kasaya_p'] = dict(kasaya_col=pick(rng, ['#8A3A1E', '#9A5A24', '#7A2A20', '#A0702E']))
    if p.get('scar'):
        p['scar_p'] = dict(scar=p['scar'], stitches=bool(u() < 0.3))
    fp['stubble'] = p.get('stubble', 0.0)


# ----------------------------------------------------------------------
# Archetype tables
# ----------------------------------------------------------------------

def build_all():
    plans = []
    # --- male warriors ---------------------------------------------------
    n = 30
    hg = deal('mw_hg', ['helmet_tassel'] * 3 + ['helmet_feathers', 'helmet_plain'] + ['headband'] * 2 +
              ['headband_jewel', 'topknot', 'topknot'], n)
    beard = deal('mw_beard', ['none', 'stubble', 'goatee', 'moustache', 'full', 'full', 'long', 'mous_goatee'], n)
    armour = deal('mw_arm', ['iron', 'steel', 'bronze', 'black', 'redlac', 'leather', 'iron'], n)
    accent = deal('mw_acc', ['red', 'blue', 'green', 'ochre', 'black', 'purple', 'red'], n)
    ages = deal('mw_age', ['young', 'adult', 'adult'], n)
    scar = deal('mw_scar', [None] * 5 + ['cheek', 'brow', 'nose'], n)
    mirror = deal('mw_mirror', [True, False, False], n)
    for i in range(n):
        s = dict(age=ages[i], headgear=hg[i], beard=beard[i], armour=armour[i], accent=accent[i],
                 mirror=mirror[i], scar=scar[i])
        if i == 17:
            s['eyepatch'] = True
        if beard[i] in ('none', 'moustache'):
            s['stubble'] = 0.25
        elif beard[i] == 'stubble':
            s['stubble'] = 0.75
        else:
            s['stubble'] = 0.4
        plans.append(('m', 'warrior', i, s))
    # --- male scholars ---------------------------------------------------
    n = 20
    hg = deal('ms_hg', ['guan_black', 'guan_black', 'guan_gold', 'cloth_cap', 'cloth_cap', 'tall_hat', 'tall_hat',
                        'topknot'], n)
    beard = deal('ms_beard', ['none', 'mous_goatee', 'mous_goatee', 'goatee', 'thin_long', 'moustache'], n)
    ages = deal('ms_age', ['young', 'adult', 'adult'], n)
    fan = deal('ms_fan', [True, False, False], n)
    for i in range(n):
        s = dict(age=ages[i], headgear=hg[i], beard=beard[i], fan=fan[i],
                 stubble=0.15 if beard[i] == 'none' else 0.25)
        plans.append(('m', 'scholar', i, s))
    # --- male elders -----------------------------------------------------
    n = 12
    hg = deal('me_hg', ['guan_black', 'cloth_cap', 'tall_hat', 'topknot', 'guan_gold', 'cloth_cap'], n)
    beard = deal('me_beard', ['long', 'long', 'full', 'thin_long', 'mous_goatee', 'goatee'], n)
    for i in range(n):
        s = dict(age='old', headgear=hg[i], beard=beard[i], stubble=0.2)
        if i in (2, 7, 10):     # veteran generals
            s['armour'] = ['iron', 'bronze', 'black'][(i // 3) % 3]
            s['accent'] = ['red', 'blue', 'green'][(i // 3) % 3]
            s['headgear'] = ['helmet_tassel', 'headband', 'topknot'][(i // 3) % 3]
        if i == 5:
            s['fan'] = True
        plans.append(('m', 'elder', i, s))
    # --- monks -----------------------------------------------------------
    n = 6
    monk_cfg = [
        dict(age='young', beard='none', dots=True, beads=True, kasaya=True),
        dict(age='adult', beard='stubble', dots=False, beads=True, kasaya=False, stubble=0.8),
        dict(age='old', beard='long', dots=True, beads=True, kasaya=True),
        dict(age='adult', beard='none', dots=True, beads=False, kasaya=True, scar='brow'),
        dict(age='old', beard='none', dots=False, beads=True, kasaya=False),
        dict(age='adult', beard='full', dots=False, beads=True, kasaya=True),
    ]
    robes = ['#86703F', '#5C5852', '#6A4A2E', '#4A4A44', '#8C6A3A', '#3A3A34']
    for i in range(n):
        s = dict(monk_cfg[i])
        s['headgear'] = 'bald'
        s['monk_robe'] = robes[i]
        s.setdefault('stubble', 0.3)
        plans.append(('m', 'monk', i, s))
    # --- rogues ----------------------------------------------------------
    n = 10
    hg = deal('mr_hg', ['hood', 'headscarf', 'messy', 'messy_band', 'hood', 'messy'], n)
    beard = deal('mr_beard', ['stubble', 'stubble', 'goatee', 'full', 'moustache', 'none'], n)
    ages = deal('mr_age', ['young', 'adult', 'adult'], n)
    scar = deal('mr_scar', ['cheek', 'brow', 'nose', 'chin', None, 'cheek'], n)
    extra = deal('mr_extra', ['scarf', 'earring', None, 'scarf', 'earring', None], n)
    for i in range(n):
        s = dict(age=ages[i], headgear=hg[i], beard=beard[i], scar=scar[i],
                 neck_scarf=extra[i] == 'scarf', earring=extra[i] == 'earring',
                 stubble=0.8 if beard[i] == 'stubble' else 0.45)
        if i == 6:
            s['eyepatch'] = True
        if hg[i] == 'messy_band':
            s['headgear'] = 'messy'
            s['messy_band'] = True
        plans.append(('m', 'rogue', i, s))
    # --- female warriors -------------------------------------------------
    n = 10
    hs = deal('fw_hs', ['high_bun', 'ponytail', 'high_bun', 'ponytail', 'double_bun', 'half_up'], n)
    armour = deal('fw_arm', ['iron', 'redlac', 'leather', 'bronze', 'steel', 'black'], n)
    accent = deal('fw_acc', ['red', 'blue', 'green', 'purple', 'white', 'red'], n)
    band = deal('fw_band', [True, False, False], n)
    ages = deal('fw_age', ['young', 'young', 'adult'], n)
    for i in range(n):
        orn = ['pins'] if hs[i] in ('high_bun', 'double_bun') else []
        if band[i]:
            orn.append('band')
        s = dict(age=ages[i], hairstyle=hs[i], armour=armour[i], accent=accent[i], ornaments=orn,
                 mirror=False, headgear='female')
        if i == 4:
            s['scar'] = 'brow'
        plans.append(('f', 'warrior', i, s))
    # --- female scholars -------------------------------------------------
    n = 10
    hs = deal('fs_hs', ['high_bun', 'double_bun', 'half_up', 'low_bun', 'high_bun'], n)
    orn = deal('fs_orn', [['pins', 'flower'], ['comb', 'buyao'], ['pins', 'buyao'], ['flower', 'comb'],
                          ['pins'], ['buyao', 'flower']], n)
    mark = deal('fs_mark', [True, False, False], n)
    ear = deal('fs_ear', [True, False], n)
    ages = deal('fs_age', ['young', 'young', 'adult'], n)
    for i in range(n):
        s = dict(age=ages[i], hairstyle=hs[i], ornaments=list(orn[i]), forehead_mark=mark[i],
                 earring=ear[i], headgear='female')
        plans.append(('f', 'scholar', i, s))
    # --- female elders ---------------------------------------------------
    n = 4
    cfg = [dict(hairstyle='low_bun', ornaments=['pins'], forehead_band=True),
           dict(hairstyle='high_bun', ornaments=['comb']),
           dict(hairstyle='low_bun', ornaments=['pins', 'band']),
           dict(hairstyle='high_bun', ornaments=['pins'])]
    for i in range(n):
        s = dict(cfg[i])
        s['age'] = 'old'
        s['headgear'] = 'female'
        plans.append(('f', 'elder', i, s))

    out = []
    for gender, arch, i, s in plans:
        pid = '%s_%s_%02d' % (gender, arch, i + 1)
        out.append(make_params(pid, gender, arch, i, s))
    return out


# ----------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------

def beard_kind(b):
    return {
        'none': (None, None), 'stubble': (None, None), 'goatee': ('goatee', None),
        'moustache': (None, 'full'), 'mous_goatee': ('goatee', 'thin'), 'full': ('full', 'full'),
        'long': ('long', 'droop'), 'thin_long': ('long_thin', 'thin'),
    }[b]


def draw_messy_strands(cv, head, rng, colors):
    """A few loose locks falling over the forehead."""
    from portrait_raster import StrokeLayer
    hu = head.hu
    lay = StrokeLayer()
    for k in range(7):
        u0 = rng.uniform(-0.55, 0.35)
        top = head.pt(u0, -0.66, 3.0)
        mid = head.pt(u0 + rng.uniform(-0.1, 0.12), -0.5 + rng.uniform(-0.04, 0.04), 2.0)
        end = head.pt(u0 + rng.uniform(-0.05, 0.25), -0.36 + rng.uniform(-0.06, 0.08), 1.0)
        pts = catmull([top, mid, end], 6)
        lay.add(pts, [1.6, 1.4, 1.0, 0.6, 0.2], 1.0)
    m = lay.result()
    cv.paint(m, colors[1] * 0.9, 0.95)
    cv.paint(ink_outline(m, 0.3, None, 0, 0.6), INK, 0.4)


def render(p):
    rng = np.random.default_rng(p['seed_extra'])
    fp = p['face']
    gender, arch = p['gender'], p['archetype']
    hg = p.get('headgear', 'topknot')
    cv = Canvas()
    draw_background(cv, rng)
    head = Head(fp)
    body_p = dict(shoulder=1.05 if gender == 'm' else 0.9, neck_w=1.0 if gender == 'm' else 0.85,
                  slope=1.0 if gender == 'm' else 1.15)
    if arch == 'scholar' or arch == 'elder':
        body_p['shoulder'] = 0.98 if gender == 'm' else 0.88
    body = Body(head, body_p)
    hc = hair_colors(p['hair_hex'], p['grey'])
    hp = p['hair']

    # ---- behind the body
    if hg == 'hood':
        gear.draw_hood(cv, head, body, p['hood_p'], rng, front=False)
    if gender == 'f':
        gear.draw_female_hair(cv, head, body, hp, rng, hc, 'back')
    if hg == 'messy':
        draw_loose_back(cv, head, body, hp, rng, hc, length=0.15, spread=1.0)

    # ---- body
    layers = p['layers']
    if arch == 'monk':
        mr = p['monk_robe']
        layers = [('#E4DCCB', '#E4DCCB'), (mr, mr), (mr, '#3A2E24')]
    dp = dict(layers=layers, face=fp, spread=1.0)
    draw_robe(cv, head, body, dp, rng)
    if p.get('armour_p'):
        gear.draw_armour(cv, head, body, p['armour_p'], rng)
    if arch == 'monk':
        if p.get('kasaya'):
            gear.draw_kasaya(cv, head, body, p['kasaya_p'], rng)
        if p.get('beads'):
            gear.draw_beads(cv, head, body, p['bead_p'], rng)
    if p.get('neck_scarf'):
        gear.draw_neck_scarf(cv, head, body, dict(scarf_col=pick(np.random.default_rng(p['seed_extra'] + 1),
                                                                 ['#6A2A22', '#4A4A3A', '#2E3F5C', '#5A4A38'])), rng)

    # ---- head
    mask, lit, hf, surf = render_skin(cv, head, fp, rng)
    if hg == 'bald':
        gear.scalp_stubble(cv, head, surf, hp, rng, 0.45 if p['age'] != 'old' else 0.15)
    cv.paint(ink_outline(mask, 0.65, rng, 0.3), INK, 0.85)
    draw_eyes(cv, head, fp, lit, rng)
    brow_col = hc[1] * 0.75 if p['grey'] < 0.5 else mix_brow(hc)
    draw_brows(cv, head, fp, rng, brow_col)
    draw_nose(cv, head, fp, lit)
    bk, mk = beard_kind(p.get('beard', 'none'))
    if bk:
        style = 'long' if bk == 'long_thin' else bk
        length = {'goatee': 0.45, 'full': 0.5, 'long': 1.25}.get(style, 0.5)
        if bk == 'long_thin':
            length = 0.9
        if bk == 'long' and p['archetype'] == 'elder':
            length = 1.4
        draw_beard(cv, head, fp, surf, rng, hc, style, length, thin=(bk == 'long_thin'))
    draw_mouth(cv, head, fp, lit, female=(gender == 'f'))
    if mk:
        draw_moustache(cv, head, fp, rng, hc, mk)
    draw_wrinkles(cv, head, fp, rng)
    if p.get('scar_p'):
        gear.draw_scar(cv, head, fp, p['scar_p'], rng)
    if p.get('forehead_mark'):
        gear.draw_forehead_mark(cv, head, rng)
    if hg == 'bald' and p.get('dots'):
        gear.ordination_dots(cv, head, rng)

    # ---- hair & headgear
    if gender == 'f':
        gear.draw_female_hair(cv, head, body, hp, rng, hc, 'front')
        draw_ear(cv, head, fp, rng, fp['skin'])
        if p.get('earring'):
            gear.draw_earring(cv, head, rng)
        if hp['style'] in ('high_bun', 'low_bun', 'half_up', 'double_bun') and p['archetype'] != 'warrior':
            gear.draw_side_lock(cv, head, hc, rng, hp)
        if p.get('forehead_band'):
            gear.draw_headband(cv, head, dict(band_col='#24201C', band_y=-0.6, band_h=0.1, tails=False,
                                              band_jewel=True, jewel_col='#3F6E5A', grow=0.07 * head.hu), rng)
        gear.draw_hair_ornaments(cv, head, hp, rng)
    elif hg == 'bald':
        draw_ear(cv, head, fp, rng, fp['skin'])
    elif hg == 'hood':
        hp2 = dict(hp, hairline=-0.6)
        draw_hair_cap(cv, head, hp2, rng, hc)
        gear.draw_hood(cv, head, body, p['hood_p'], rng, front=True)
    elif hg.startswith('helmet'):
        draw_hair_cap(cv, head, hp, rng, hc)
        draw_ear(cv, head, fp, rng, fp['skin'])
        gear.draw_helmet(cv, head, p['helmet_p'], rng)
    else:
        draw_hair_cap(cv, head, hp, rng, hc)
        if hg in ('topknot', 'headband', 'headband_jewel', 'guan_black', 'guan_gold', 'messy'):
            kx, ky = topknot_point(head, hp)
            if hg == 'messy':
                draw_bun(cv, head, kx - 0.05 * head.hu, ky + 0.05 * head.hu, 0.16 * head.hu, 0.13 * head.hu, hc, rng)
            else:
                draw_bun(cv, head, kx, ky, 0.2 * head.hu, 0.17 * head.hu, hc, rng)
            if hg in ('topknot', 'headband', 'headband_jewel'):
                tie_col = hexc(pick(np.random.default_rng(p['seed_extra'] + 2), ['#7E1F17', '#24201C', '#2E3F5C', '#C9A24A']))
                tie = ellipse(kx + 0.02 * head.hu, ky + 0.12 * head.hu, 0.16 * head.hu, 0.055 * head.hu, -0.1)
                from portrait_dress import paint_shaded
                from portrait_raster import pillow
                paint_shaded(cv, tie, tie_col, pillow(tie, 0.04 * head.hu, 1.0), rng, outline=0.4)
        draw_ear(cv, head, fp, rng, fp['skin'])
        if p.get('earring'):
            gear.draw_earring(cv, head, rng)
        if hg == 'messy':
            draw_messy_strands(cv, head, rng, hc)
            if p.get('messy_band'):
                gear.draw_headband(cv, head, dict(band_col='#6A2A22', band_y=-0.52, band_h=0.09, tails=True), rng)
        if hg in ('headband', 'headband_jewel'):
            gear.draw_headband(cv, head, p['band_p'], rng)
        if hg in ('guan_black', 'guan_gold'):
            gear.draw_guan(cv, head, dict(p['guan_p'], **hp), rng)
        if hg in ('cloth_cap', 'headscarf'):
            gear.draw_cloth_cap(cv, head, dict(p['cap_p'], **hp), rng)
        if hg == 'tall_hat':
            gear.draw_tall_hat(cv, head, p['hat_p'], rng)
    if p.get('eyepatch'):
        gear.draw_eyepatch(cv, head, fp, rng)
    if p.get('fan'):
        gear.draw_fan(cv, head, body, {}, rng)
    finish(cv, rng)
    return cv.image()


def mix_brow(hc):
    dark, mid, lite = hc
    return mid * 0.85


# ----------------------------------------------------------------------
# Notes
# ----------------------------------------------------------------------

def notes_for(p):
    parts = []
    g = p['gender']
    arch = p['archetype']
    hg = p.get('headgear')
    hair = p['hair_name']
    fp = p['face']
    if fp['w_jaw'] > 0.65 and g == 'm':
        parts.append('square jaw')
    elif fp['w_jaw'] < 0.57 and g == 'm':
        parts.append('narrow face')
    parts.append('%s skin' % p['skin_name'])
    hgn = {
        'helmet_tassel': '%s helmet with %s tassel',
        'helmet_feathers': '%s helmet with pheasant feathers',
        'helmet_plain': 'plain %s helmet',
    }
    if hg in hgn:
        hm = p['helmet_p']['metal']
        mname = {'redlac': 'red lacquer', 'black': 'black lacquer'}.get(hm, hm)
        if hg == 'helmet_tassel':
            col = {'#9A2A1E': 'red', '#7E1F17': 'crimson', '#B0402A': 'vermilion', '#2A2622': 'black'}[p['helmet_p']['plume_col']]
            parts.append(hgn[hg] % (mname, col))
        else:
            parts.append(hgn[hg] % mname)
    elif hg in ('headband', 'headband_jewel'):
        parts.append('%s topknot, %s headband%s' % (hair, colour_name(p['band_p']['band_col']),
                                                   ' with jade' if hg == 'headband_jewel' else ''))
    elif hg == 'topknot':
        parts.append('%s hair in a topknot' % hair)
    elif hg in ('guan_black', 'guan_gold'):
        parts.append('%s topknot under a small %s crown' % (hair, 'black' if hg == 'guan_black' else 'gold'))
    elif hg == 'cloth_cap':
        parts.append('%s scholar cap' % colour_name(p['cap_p']['cap_col']))
    elif hg == 'headscarf':
        parts.append('%s headscarf' % colour_name(p['cap_p']['cap_col']))
    elif hg == 'tall_hat':
        parts.append('tall black official hat')
    elif hg == 'hood':
        parts.append('%s hood' % colour_name(p['hood_p']['hood_col']))
    elif hg == 'messy':
        parts.append('messy %s hair%s' % (hair, ', red headband' if p.get('messy_band') else ''))
    elif hg == 'bald':
        parts.append('shaved head' + (', ordination marks' if p.get('dots') else ''))
    elif hg == 'female':
        hs = p['hair']['style']
        parts.append('%s hair, %s' % (hair, {'high_bun': 'high bun', 'double_bun': 'twin buns', 'low_bun': 'low bun',
                                              'ponytail': 'high ponytail', 'half_up': 'long hair half up',
                                              'loose': 'long loose hair'}[hs]))
        orn = p['hair'].get('ornaments', [])
        on = {'pins': 'hairpins', 'comb': 'gold comb', 'flower': 'flowers', 'buyao': 'dangling hair ornament',
              'band': 'forehead band'}
        if orn:
            parts.append(', '.join(on[o] for o in orn))
        if p.get('forehead_band'):
            parts.append('black forehead band')
    b = p.get('beard', 'none')
    bn = {'none': 'clean-shaven', 'stubble': 'stubble', 'goatee': 'goatee', 'moustache': 'moustache',
          'mous_goatee': 'thin moustache and goatee', 'full': 'full beard', 'long': 'long flowing beard',
          'thin_long': 'long thin beard'}
    if g == 'm':
        bh = 'white' if p['grey'] > 0.88 else ('grey' if p['grey'] > 0.5 else hair.split()[-1] if hair != 'black' else 'black')
        if b in ('none', 'stubble'):
            parts.append(bn[b])
        else:
            parts.append('%s %s' % (bh, bn[b]))
    if p.get('armour_p'):
        a = p['armour_p']
        mname = {'redlac': 'red lacquer', 'black': 'black lacquer', 'leather': 'leather'}.get(a['metal'], a['metal'])
        parts.append('%s lamellar armour%s' % (mname, ', bronze chest mirror' if a.get('mirror') else ''))
    elif arch == 'monk':
        parts.append('plain robe' + (', kasaya sash' if p.get('kasaya') else '') + (', prayer beads' if p.get('beads') else ''))
    else:
        parts.append('%s robe' % p['robe_name'])
    if p.get('scar'):
        parts.append({'cheek': 'scar on left cheek', 'brow': 'scar through right brow', 'nose': 'scar across nose',
                      'chin': 'scar on chin'}[p['scar']])
    if p.get('eyepatch'):
        parts.append('eyepatch')
    if p.get('neck_scarf'):
        parts.append('neck scarf')
    if p.get('earring'):
        parts.append('gold earring')
    if p.get('fan'):
        parts.append('feather fan')
    if p.get('forehead_mark'):
        parts.append('red forehead mark')
    return ', '.join(parts)


def colour_name(hx):
    names = {'#8E2A20': 'red', '#7E1F17': 'crimson', '#24201C': 'black', '#2E3F5C': 'indigo', '#D8D0C0': 'white',
             '#3F5A4A': 'green', '#8A6A2E': 'ochre', '#5A3A2E': 'brown', '#465666': 'slate', '#3A3530': 'dark grey',
             '#6A2A22': 'rust', '#4A4A3A': 'olive', '#4A3A2E': 'brown', '#3A3A34': 'grey', '#2E3A44': 'blue-grey',
             '#5A4A38': 'dun', '#2A2622': 'black', '#4A3030': 'maroon'}
    return names.get(hx, 'dark')


# ----------------------------------------------------------------------
# Unknown silhouette
# ----------------------------------------------------------------------

def render_unknown():
    rng = np.random.default_rng(zlib.crc32(b'unknown'))
    cv = Canvas()
    draw_background(cv, rng)
    fp = face_params(np.random.default_rng(7), 'm', 'adult', 'warrior')
    fp['skin'] = SKINS[3]
    head = Head(fp)
    body = Body(head, dict(shoulder=1.05))
    surf = head.surface(grow=2.5)
    m = surf['mask']
    m = np.maximum(m, poly(body.torso_poly()))
    m = np.maximum(m, poly(body.neck_poly(0.5 * head.hu)))
    kx, ky = topknot_point(head, dict(knot_y=-0.98, knot_z=-0.42))
    m = np.maximum(m, ellipse(kx, ky, 0.21 * head.hu, 0.18 * head.hu))
    from portrait_face import ear_anchor
    (tx, ty), (bx, by) = ear_anchor(head)
    m = np.maximum(m, ellipse(tx - 0.08 * head.hu, (ty + by) / 2, 0.11 * head.hu, 0.26 * head.hu))
    m = clamp01(m)
    # rim light from the top-left
    sh = np.roll(np.roll(m, 4, 0), 4, 1)
    rim = clamp01(m - sh) * 0.6
    base = hexc('#16110D')
    cv.paint(blur(m, 3.0), hexc('#0E0B08'), 0.35)
    cv.paint(m, base)
    cv.paint(blur(rim, 0.6), hexc('#6A5440'), 0.55)
    # soft inner glow suggesting a face
    X, Y = grid()
    glow = np.exp(-(((X - head.midline_x(0.2)) / 26.0) ** 2 + ((Y - 105) / 34.0) ** 2)) * m
    cv.paint(glow, hexc('#2A2018'), 0.5)
    cv.paint(ink_outline(m, 0.8, rng, 0.3), hexc('#0A0806'), 0.9)
    finish(cv, rng)
    return cv.image()


# ----------------------------------------------------------------------
# Driver
# ----------------------------------------------------------------------

def _work(p):
    im = render(p)
    path = os.path.join(OUT_DIR, p['id'] + '.png')
    save_png(im, path)
    return p['id']


def save_png(im, path):
    im = im.convert('RGB')
    im.save(path, optimize=True)


def contact_sheet(ids, path, cols=10, scale=0.5):
    tw, th = int(W * scale), int(H * scale)
    rows = (len(ids) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * tw, rows * th), (20, 16, 12))
    for i, pid in enumerate(ids):
        im = Image.open(os.path.join(OUT_DIR, pid + '.png')).convert('RGB').resize((tw, th), Image.LANCZOS)
        sheet.paste(im, ((i % cols) * tw, (i // cols) * th))
    sheet.save(path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', default='', help='comma separated ids (or prefixes) to render')
    ap.add_argument('--jobs', type=int, default=os.cpu_count() or 1)
    ap.add_argument('--sheet', default='', help='write a contact sheet of the rendered ids to this path')
    ap.add_argument('--sheet-scale', type=float, default=0.5)
    args = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    plans = build_all()
    sel = plans
    if args.only:
        keys = [k.strip() for k in args.only.split(',') if k.strip()]
        sel = [p for p in plans if any(p['id'] == k or p['id'].startswith(k) for k in keys)]
    if args.jobs > 1 and len(sel) > 1:
        from multiprocessing import Pool
        with Pool(args.jobs) as pool:
            for pid in pool.imap_unordered(_work, sel):
                print('wrote', pid)
    else:
        for p in sel:
            print('wrote', _work(p))
    if not args.only or 'unknown' in args.only:
        save_png(render_unknown(), os.path.join(OUT_DIR, 'unknown.png'))
        print('wrote unknown')
    # manifest always describes the full set
    manifest = [dict(id=p['id'], gender=p['gender'], archetype=p['archetype'], age=p['age'], notes=notes_for(p))
                for p in plans]
    with open(os.path.join(OUT_DIR, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write('\n')
    if args.sheet:
        contact_sheet([p['id'] for p in sel], args.sheet, scale=args.sheet_scale)
        print('sheet', args.sheet)


if __name__ == '__main__':
    main()
