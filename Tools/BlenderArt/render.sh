#!/usr/bin/env bash
# Run an ironart asset script headless in Blender with the studio flags.
#
#   Tools/BlenderArt/render.sh <script.py> [script args...]
#
# Environment
#   BLENDER          blender binary (default: blender on PATH, i.e. /usr/bin/blender 4.0.2)
#   IRONART_OUT      scratch/preview output root (default /tmp/ironart)
#   IRONART_THREADS  fixed Cycles thread count (default: all cores)
#   IRONART_NICE     scheduling niceness (default 10: the 4 cores are shared; 0 = normal)
#   IRONART_VERBOSE  1 = show Blender's per-sample progress spam
#   IRONART_LOG      also append the full log to this file
#
# Exit status is the script's (non-zero on any Python exception or crash). Cycles CPU only -
# EEVEE and Workbench crash on this headless machine, and OpenImageDenoise is not available.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BLENDER="${BLENDER:-blender}"
if [ $# -lt 1 ]; then
  sed -n '2,15p' "$0"
  exit 2
fi
SCRIPT="$1"; shift
if [ ! -f "$SCRIPT" ]; then
  echo "[render.sh] no such script: $SCRIPT" >&2
  exit 1
fi
export IRONART_OUT="${IRONART_OUT:-/tmp/ironart}"
mkdir -p "$IRONART_OUT"
NICE="${IRONART_NICE:-10}"

start=$(date +%s.%N)
filter() {
  if [ "${IRONART_VERBOSE:-0}" = "1" ]; then cat; else
    # Blender noise: progress lines, prefs, OIIO debug, mesh validation chatter and Freestyle's
    # harmless "strokes set empty" message for line sets that select nothing, and Blender's
    # end-of-run "Not freed memory blocks" leak report.
    grep --line-buffered -v -E '^(Fra:[0-9]+ |Blender quit$|Read prefs:|OIIO DEBUG|Warning: (degenerated|edge [0-9]+ - [0-9]+ appears)|Error: strokes set empty$|Error: Not freed memory blocks|$)' || true
  fi
}
run() { nice -n "$NICE" "$BLENDER" -b --factory-startup -noaudio --python-exit-code 1 \
          -P "$HERE/ironart/run.py" -- "$SCRIPT" "$@" 2>&1; }
if [ -n "${IRONART_LOG:-}" ]; then
  run "$@" | tee -a "$IRONART_LOG" | filter
else
  run "$@" | filter
fi
status=${PIPESTATUS[0]}
end=$(date +%s.%N)
printf '[render.sh] %s exit=%d wall=%.1fs\n' "$(basename "$SCRIPT")" "$status" "$(awk -v a="$start" -v b="$end" 'BEGIN{print b-a}')"
exit "$status"
