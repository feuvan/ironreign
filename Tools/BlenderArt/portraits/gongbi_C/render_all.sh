#!/usr/bin/env bash
# Render the whole gongbi_C cast (102 archetype keys + unknown) or a subset.
#   portraits/gongbi_C/render_all.sh <out_dir> [key...]
# Keys default to `python3 cast.py --keys` (m_warrior_01..30, m_scholar_01..20, ...).
# JOBS (default 2) portraits run side by side: Cycles is multi-threaded, the 2D stage is
# single-threaded, so two jobs keep the shared 4 cores busy without starving other artists.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT="$1"; shift
mkdir -p "$OUT"
if [ $# -gt 0 ]; then KEYS="$*"; else KEYS="$(cd "$HERE" && python3 cast.py --keys)"; fi
export IRONART_THREADS="${IRONART_THREADS:-2}"
printf '%s\n' $KEYS | xargs -P "${JOBS:-2}" -I{} "$HERE/make.sh" "$OUT" {}
python3 "$HERE/make_sheet.py" cast "$OUT" "$OUT/cast_sheet.png" 10 --thumb 96
