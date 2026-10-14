#!/usr/bin/env bash
# Fetches the MakeHuman base mesh, morph targets, eyes and skin data (CC0 1.0, see LICENSE.ASSETS.md in the
# MakeHuman repository) used by the portrait generator. Pinned to a fixed commit so portraits are reproducible.
# Output: Tools/BlenderArt/.cache/makehuman/makehuman/data/{3dobjs,targets,eyes,skins}
set -euo pipefail
COMMIT=a8bc2d54ff0ac92e78ff71431b1023eda42bf482
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HERE/.cache/makehuman"
if [ -f "$DEST/.commit" ] && [ "$(cat "$DEST/.commit")" = "$COMMIT" ]; then
  echo "MakeHuman data already at $COMMIT"; exit 0
fi
rm -rf "$DEST"
git clone -q --filter=blob:none --no-checkout https://github.com/makehumancommunity/makehuman.git "$DEST"
cd "$DEST"
git sparse-checkout init --no-cone
git sparse-checkout set /LICENSE.ASSETS.md /makehuman/data/3dobjs/ /makehuman/data/targets/ /makehuman/data/eyes/ /makehuman/data/skins/
git checkout -q "$COMMIT"
echo "$COMMIT" > .commit
echo "MakeHuman data ready in $DEST"
