#!/usr/bin/env bash
# Render the whole gongbi_B cast (102 archetype keys + unknown) or a subset.
#   portraits/gongbi_B/render_all.sh <out_dir> [key...]
# The canon gate runs over every key first (any violation stops the batch).  JOBS (default 2)
# Blender processes run side by side, each rendering its share of the keys in one session
# with IRONART_THREADS (default 2) Cycles threads, so the shared 4 cores stay busy without
# starving the other artists.  Then timing.json and a 96 px contact sheet are written.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ART="$(cd "$HERE/../.." && pwd)"
OUT="$(mkdir -p "$1" && cd "$1" && pwd)"; shift
if [ $# -gt 0 ]; then KEYS=("$@"); else read -r -a KEYS <<< "$(cd "$HERE" && python3 cast.py --keys)"; fi
(cd "$HERE" && python3 cast.py --check "${KEYS[@]}")
export IRONART_THREADS="${IRONART_THREADS:-2}"
JOBS="${JOBS:-2}"
start=$(date +%s)
pids=()
for ((j = 0; j < JOBS; j++)); do
  part=()
  for ((i = j; i < ${#KEYS[@]}; i += JOBS)); do part+=("${KEYS[$i]}"); done
  [ ${#part[@]} -eq 0 ] && continue
  "$ART/render.sh" "$HERE/render_cast.py" "$OUT" "${part[@]}" > "$OUT/job$j.log" 2>&1 &
  pids+=($!)
done
status=0
for p in "${pids[@]}"; do wait "$p" || status=1; done
python3 "$HERE/make_sheet.py" --contact "$OUT" "${KEYS[@]}"
echo "[render_all] ${#KEYS[@]} keys in $(( $(date +%s) - start ))s, exit $status"
exit $status
