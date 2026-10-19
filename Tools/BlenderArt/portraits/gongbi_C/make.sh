#!/usr/bin/env bash
# Render gongbi_C portraits: 3D stage in Blender, 2D stage in python3.
#   portraits/gongbi_C/make.sh <out_dir> <spec> [spec...]
# Writes <out_dir>/<spec>.png (384x480), <spec>_192.png and <spec>_timing.json.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS="$(cd "$HERE/../.." && pwd)"
OUT="$1"; shift
mkdir -p "$OUT/_scenes"
for spec in "$@"; do
  t0=$(date +%s.%N)
  IRONART_OUT="$OUT" "$TOOLS/render.sh" "$HERE/stage3d.py" "$spec" "$OUT/_scenes/$spec" "${SS:-3}" "${SPP:-8}" | grep -E "gongbi_C|FAILED|Error|Traceback|line [0-9]+" || true
  python3 "$HERE/stage2d.py" "$OUT/_scenes/$spec" "$spec" "$OUT/$spec.png" ${DEBUG:+--debug}
  t1=$(date +%s.%N)
  printf '[make] %s wall %.1fs\n' "$spec" "$(awk -v a="$t0" -v b="$t1" 'BEGIN{print b-a}')"
done
