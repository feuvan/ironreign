#!/usr/bin/env python3
"""Builds the CJK fonts shipped in Content/Data/Fonts.

Downloads Noto Serif SC/TC/JP/KR (SIL OFL) from github.com/google/fonts into a cache, instances the
Regular (400) and Bold (700) weights and subsets each font to the characters used by the game's text
(all string tables + scenarios + ASCII), producing:

  Content/Data/Fonts/CJK-SC-Regular.ttf, CJK-SC-Bold.ttf   (Simplified Chinese; also the English-mode CJK fallback)
  Content/Data/Fonts/CJK-TC-*.ttf, CJK-JP-*.ttf, CJK-KR-*.ttf

Re-run after adding or changing text:  python3 Tools/Localization/build_fonts.py
Requires: pip install fonttools brotli
"""
import io
import pathlib
import sys
import urllib.request

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

from loclib import DATA_DIR, LOC_DIR, ROOT, SCENARIO_DIR

CACHE = ROOT / "Tools" / "Localization" / ".cache"
FONTS_DIR = DATA_DIR / "Fonts"
BASE_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
FAMILIES = {
    # tag: (google fonts path, cultures whose text must be covered)
    "SC": ("notoserifsc/NotoSerifSC%5Bwght%5D.ttf", ["zh-Hans", "en"]),
    "TC": ("notoseriftc/NotoSerifTC%5Bwght%5D.ttf", ["zh-Hant"]),
    "JP": ("notoserifjp/NotoSerifJP%5Bwght%5D.ttf", ["ja"]),
    "KR": ("notoserifkr/NotoSerifKR%5Bwght%5D.ttf", ["ko"]),
}
LICENSE_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/notoserifsc/OFL.txt"

# Always included: printable ASCII, Latin-1, general and CJK punctuation, full-width forms, digits.
BASE_RANGES = [(0x20, 0x7E), (0xA0, 0xFF), (0x2000, 0x206F), (0x3000, 0x303F), (0xFF00, 0xFFEF), (0x2190, 0x21FF), (0x25A0, 0x25FF)]


def download(relative: str) -> pathlib.Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    target = CACHE / relative.split("/")[-1].replace("%5B", "[").replace("%5D", "]")
    if not target.exists():
        print(f"downloading {relative} ...")
        with urllib.request.urlopen(BASE_URL + relative) as response:
            target.write_bytes(response.read())
    return target


def collect_text(cultures) -> str:
    chunks = []
    for culture in cultures:
        folder = LOC_DIR / culture
        if folder.exists():
            for path in folder.glob("*.json"):
                chunks.append(path.read_text(encoding="utf-8"))
    # Scenario files carry nameZh fields and glyphs shown as decoration in every language.
    for path in SCENARIO_DIR.glob("*.json"):
        chunks.append(path.read_text(encoding="utf-8"))
    return "".join(chunks)


def build(tag: str, relative: str, cultures) -> None:
    source = download(relative)
    text = collect_text(cultures)
    codepoints = {ord(ch) for ch in text if ord(ch) >= 0x20}
    for low, high in BASE_RANGES:
        codepoints.update(range(low, high + 1))
    for weight, style in ((400, "Regular"), (700, "Bold")):
        font = TTFont(source)
        static = instancer.instantiateVariableFont(font, {"wght": weight})
        options = subset.Options()
        options.layout_features = ["*"]
        options.name_IDs = ["*"]
        options.name_languages = ["*"]
        options.notdef_outline = True
        options.hinting = False
        subsetter = subset.Subsetter(options)
        subsetter.populate(unicodes=sorted(codepoints))
        subsetter.subset(static)
        output = FONTS_DIR / f"CJK-{tag}-{style}.ttf"
        FONTS_DIR.mkdir(parents=True, exist_ok=True)
        buffer = io.BytesIO()
        static.save(buffer)
        output.write_bytes(buffer.getvalue())
        print(f"{output.relative_to(ROOT)}: {len(codepoints)} code points, {output.stat().st_size // 1024} KiB")


def main() -> int:
    for tag, (relative, cultures) in FAMILIES.items():
        build(tag, relative, cultures)
    license_path = FONTS_DIR / "OFL-NotoSerifCJK.txt"
    if not license_path.exists():
        with urllib.request.urlopen(LICENSE_URL) as response:
            license_path.write_bytes(response.read())
    return 0


if __name__ == "__main__":
    sys.exit(main())
