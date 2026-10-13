#!/usr/bin/env bash
# Render every style frame, then build the overview + light-coherence sheets and timings.
#   IRONART_OUT=/some/dir Tools/BlenderArt/styleframes/run_all.sh [frame ...]
# Exit status: non-zero if any frame, its QA asserts, or the sheet builder failed.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export IRONART_OUT="${IRONART_OUT:-/tmp/ironart}"
OUT="$IRONART_OUT/styleframes"
mkdir -p "$OUT"
FRAMES=("$@")
[ ${#FRAMES[@]} -eq 0 ] && FRAMES=(sf_terrain sf_city sf_hex_forest sf_portrait sf_ui)
: > "$OUT/timings.txt"
fail=0
for sf in "${FRAMES[@]}"; do
  start=$(date +%s.%N)
  # no `|| true` / pipeline here: $? must be render.sh's own status
  "$HERE/../render.sh" "$HERE/$sf.py" "$OUT" > "$OUT/$sf.log" 2>&1
  st=$?
  end=$(date +%s.%N)
  grep -E '^\[ironart\] (TIMES|QA|rendered|OK|FAILED)|Traceback|Error:|assert' "$OUT/$sf.log"
  printf '%s exit=%d wall=%.1fs\n' "$sf" "$st" "$(awk -v a="$start" -v b="$end" 'BEGIN{print b-a}')" | tee -a "$OUT/timings.txt"
  [ "$st" -ne 0 ] && fail=1
done
python3 "$HERE/make_sheet.py" "$OUT" || fail=1
echo "run_all exit=$fail"
exit $fail
