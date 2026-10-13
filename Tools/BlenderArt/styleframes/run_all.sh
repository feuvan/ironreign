#!/usr/bin/env bash
# Render every style frame, then build the overview sheet + timings.
#   IRONART_OUT=/some/dir Tools/BlenderArt/styleframes/run_all.sh
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export IRONART_OUT="${IRONART_OUT:-/tmp/ironart}"
OUT="$IRONART_OUT/styleframes"
mkdir -p "$OUT"
: > "$OUT/timings.txt"
fail=0
for sf in sf_terrain sf_city sf_hex_forest sf_portrait sf_ui; do
  start=$(date +%s.%N)
  "$HERE/../render.sh" "$HERE/$sf.py" "$OUT" 2>&1 | grep -E '^\[ironart\] (TIMES|rendered|OK|FAILED)|Error' || true
  st=${PIPESTATUS[0]}
  end=$(date +%s.%N)
  printf '%s exit=%d wall=%.1fs\n' "$sf" "$st" "$(awk -v a="$start" -v b="$end" 'BEGIN{print b-a}')" | tee -a "$OUT/timings.txt"
  [ "$st" -ne 0 ] && fail=1
done
python3 "$HERE/make_sheet.py" "$OUT"
exit $fail
