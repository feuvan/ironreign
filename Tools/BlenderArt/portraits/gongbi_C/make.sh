#!/usr/bin/env bash
# Render gongbi_C portraits: 3D stage in Blender, 2D stage in python3.
#   portraits/gongbi_C/make.sh <out_dir> <spec> [spec...]
# Writes <out_dir>/<spec>.png (384x480), <spec>_192.png and <spec>_timing.json.
# Env: SS (supersample, default 4), SPP (Cycles samples, default 6), DEBUG=1 (master png).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS="$(cd "$HERE/../.." && pwd)"
OUT="$1"; shift
mkdir -p "$OUT/_scenes"
for spec in "$@"; do
  name="$(basename "$spec" .json)"
  t0=$(date +%s.%N)
  IRONART_OUT="$OUT" "$TOOLS/render.sh" "$HERE/stage3d.py" "$spec" "$OUT/_scenes/$name" "${SS:-4}" "${SPP:-6}" \
    | grep -E "gongbi_C\]|FAILED|Error|Traceback|line [0-9]+" || true
  python3 "$HERE/stage2d.py" "$OUT/_scenes/$name" "$OUT/$name.png" ${DEBUG:+--debug}
  t1=$(date +%s.%N)
  printf '[make] %s wall %.1fs\n' "$name" "$(awk -v a="$t0" -v b="$t1" 'BEGIN{print b-a}')"
done
