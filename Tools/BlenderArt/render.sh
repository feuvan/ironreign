#!/usr/bin/env bash
# Run an ironart asset script headless in Blender with the studio flags.
#
#   Tools/BlenderArt/render.sh <script.py> [script args...]
#
# Environment
#   BLENDER          blender binary (default: blender on PATH, i.e. /usr/bin/blender 4.0.2)
#   IRONART_OUT      scratch/preview output root (default /tmp/ironart)
#   IRONART_THREADS  fixed Cycles thread count (default: all cores)
#   IRONART_VERBOSE  1 = show Blender's per-sample progress spam
#   IRONART_LOG      also append the full log to this file
#
# Exit status is the script's (non-zero on any Python exception). Cycles CPU only - EEVEE and
# Workbench crash on this headless machine, and OpenImageDenoise is not available.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BLENDER="${BLENDER:-blender}"
if [ $# -lt 1 ]; then
  sed -n '2,15p' "$0"
  exit 2
fi
SCRIPT="$1"; shift
export IRONART_OUT="${IRONART_OUT:-/tmp/ironart}"
mkdir -p "$IRONART_OUT"

start=$(date +%s.%N)
filter() {
  if [ "${IRONART_VERBOSE:-0}" = "1" ]; then cat; else
    grep --line-buffered -v -E '^(Fra:[0-9]+ |Blender quit$|Read prefs:|OIIO DEBUG|Warning: (degenerated|edge [0-9]+ - [0-9]+ appears)|$)' || true
  fi
}
if [ -n "${IRONART_LOG:-}" ]; then
  "$BLENDER" -b --factory-startup -noaudio --python-exit-code 1 \
      -P "$HERE/ironart/run.py" -- "$SCRIPT" "$@" 2>&1 | tee -a "$IRONART_LOG" | filter
else
  "$BLENDER" -b --factory-startup -noaudio --python-exit-code 1 \
      -P "$HERE/ironart/run.py" -- "$SCRIPT" "$@" 2>&1 | filter
fi
status=${PIPESTATUS[0]}
end=$(date +%s.%N)
printf '[render.sh] %s exit=%d wall=%.1fs\n' "$(basename "$SCRIPT")" "$status" "$(awk -v a="$start" -v b="$end" 'BEGIN{print b-a}')"
exit "$status"
