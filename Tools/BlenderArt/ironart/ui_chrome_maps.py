"""UI chrome family: PBR material layers painted into texel maps (numpy, no bpy).

A :class:`Maps` holds, at the render grid of one piece, everything the generic relief material of
:mod:`ironart.ui_chrome_render` reads:

    base   linear albedo RGB          metal  metallic 0..1          rough  roughness
    coat   clear-coat weight          spec   dielectric specular level (Principled IOR level)
    emit   linear emission RGB        mop    mother-of-pearl weight (iridescent shell, in-shader)
    alpha  coverage                   height relief in mm (= target px) for the displaced mesh

Layers are painted like a painter would: ``m.paint(weight, GOLD)`` lerps every channel the layer
defines towards it by ``weight`` (0..1 arrays, anti-aliased masks from :mod:`ui_chrome_sdf`).

The material library :data:`MATS` holds the family's physically based looks.  Albedos are linear
and *calibrated*: under the family rig a flat, face-up field renders on its palette token
(asserted by the build: Paper, Lacquer, Night within 3 levels).
"""

import numpy as np

from . import palette


def L(hexcol, k=1.0):
    return np.array(palette.lin(hexcol), np.float32) * k


#: PBR layer presets (linear albedo).  'tex' keys are handled by the piece scripts.
MATS = {
    # lacquers: pigment under a glassy clear coat
    # (the gloss of lacquer is its coat; a broad base specular would grey the pigment)
    "cinnabar": dict(base=L("#7E1F17"), metal=0.0, rough=0.42, coat=1.0, spec=0.06),
    "cinnabar_dark": dict(base=L("#4A120D"), metal=0.0, rough=0.45, coat=1.0, spec=0.06),
    "lacquer_black": dict(base=L("#1B1712"), metal=0.0, rough=0.40, coat=1.0, spec=0.05),
    "rosewood": dict(base=L("#3B1D14"), metal=0.0, rough=0.38, coat=0.85, spec=0.15),
    # metals (base = F0 colour of the metal)
    "gold": dict(base=L("#F0C873"), metal=1.0, rough=0.24, coat=0.0, spec=0.5),
    "gold_satin": dict(base=L("#E7BE6A"), metal=1.0, rough=0.38, coat=0.0, spec=0.5),
    "gold_old": dict(base=L("#C99E55"), metal=1.0, rough=0.45, coat=0.0, spec=0.5),
    "bronze_dull": dict(base=L("#8C7A62"), metal=0.55, rough=0.62, coat=0.0, spec=0.4),
    # papers / silk
    "paper": dict(base=L("#E9DCC0"), metal=0.0, rough=0.88, coat=0.0, spec=0.18),
    "silk": dict(base=L("#E6D8B8"), metal=0.0, rough=0.55, coat=0.0, spec=0.35),
    # mother of pearl (base is the body tint; the shader adds the iridescence)
    "pearl": dict(base=L("#B9B4AA"), metal=0.0, rough=0.22, coat=0.8, spec=0.5, mop=1.0),
    # ink / seal paste
    "ink": dict(base=L("#141110"), metal=0.0, rough=0.45, coat=0.0, spec=0.35),
    "seal_paste": dict(base=L("#B0281C"), metal=0.0, rough=0.62, coat=0.0, spec=0.3),
}


class Maps:
    """Texel maps of one piece (``shape`` = (rows, cols) of the render grid)."""

    CHANNELS = {"base": 3, "emit": 3, "metal": 1, "rough": 1, "coat": 1, "spec": 1, "mop": 1,
                "alpha": 1, "height": 1}

    def __init__(self, shape, base="#808080", alpha=1.0):
        h, w = shape
        self.shape = (h, w)
        self.base = np.empty((h, w, 3), np.float32)
        self.base[:] = L(base) if isinstance(base, str) else np.asarray(base, np.float32)
        self.emit = np.zeros((h, w, 3), np.float32)
        self.metal = np.zeros((h, w), np.float32)
        self.rough = np.full((h, w), 0.5, np.float32)
        self.coat = np.zeros((h, w), np.float32)
        self.spec = np.full((h, w), 0.5, np.float32)
        self.mop = np.zeros((h, w), np.float32)
        self.alpha = np.full((h, w), alpha, np.float32)
        self.height = np.zeros((h, w), np.float32)

    def paint(self, weight, layer=None, **chan):
        """Lerp channels towards ``layer`` (a MATS key or dict) and/or keyword values by
        ``weight`` (array or scalar).  Array-valued channels (textures) are allowed."""
        spec = dict(MATS[layer]) if isinstance(layer, str) else dict(layer or {})
        spec.update(chan)
        w = np.asarray(weight, np.float32)
        for k, v in spec.items():
            if k not in self.CHANNELS or k == "height":
                continue
            cur = getattr(self, k)
            v = np.asarray(v, np.float32)
            if self.CHANNELS[k] == 3:
                ww = w[..., None] if w.ndim == 2 else w
                if v.ndim == 1:
                    v = v.reshape(1, 1, 3)
                setattr(self, k, cur + (v - cur) * ww)
            else:
                setattr(self, k, cur + (v - cur) * w)
        return self

    def tint(self, weight, factor):
        """Multiply the albedo by ``factor`` (scalar, RGB or texture array) where ``weight``."""
        w = np.asarray(weight, np.float32)
        f = np.asarray(factor, np.float32)
        if f.ndim == 2:
            f = f[..., None]
        elif f.ndim == 1:
            f = f.reshape(1, 1, 3)
        ww = w[..., None] if w.ndim == 2 else w
        self.base = self.base * (1 + (f - 1) * ww)
        return self

    def crop(self, sl):
        out = Maps.__new__(Maps)
        for k in self.CHANNELS:
            setattr(out, k, getattr(self, k)[sl].copy())
        out.shape = out.alpha.shape
        return out

    def stats(self):
        return {k: (float(getattr(self, k).min()), float(getattr(self, k).max()))
                for k in self.CHANNELS}
