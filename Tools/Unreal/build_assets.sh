#!/usr/bin/env bash
# Import ArtSource/ into /Game/IronReign with the Unreal editor's Python commandlet (DESIGN.md section 12).
#
#   Tools/Unreal/build_assets.sh [--incremental] [--rhi] [extra editor arguments...]
#
#   --incremental   only rebuild when ArtSource/manifest.json "version" (or the pipeline) changed
#                   (default: force a full rebuild)
#   --rhi           run with a real RHI instead of -nullrhi
#
# Environment
#   UE_EDITOR   editor binary to use (overrides everything below)
#   UE_ROOT     engine root, the folder that contains Engine/ (default: the first of
#               "/Users/Shared/Epic Games/UE_5.8", ~/UnrealEngine, /home/ue4/UnrealEngine, /opt/UnrealEngine)
#
# The IronReign editor module must be built first (IronReignEditor target). Exit status: 0 when
# Saved/IronReign/asset_build_result.txt says OK, 1 on a failed import, 2 on a setup problem.
set -uo pipefail
# (empty arrays are expanded as ${A[@]+"${A[@]}"} below: macOS ships bash 3.2, where "${A[@]}" trips set -u)

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$HERE/../.." && pwd)"
UPROJECT="$PROJECT_DIR/IronReign.uproject"
RESULT_FILE="$PROJECT_DIR/Saved/IronReign/asset_build_result.txt"
STATUS_FILE="$PROJECT_DIR/Saved/IronReign/asset_version.txt"

FORCE=1
RHI_ARGS=(-nullrhi)
EXTRA_ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --incremental) FORCE=0 ;;
    --rhi) RHI_ARGS=() ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) EXTRA_ARGS+=("$1") ;;
  esac
  shift
done

if [ ! -f "$PROJECT_DIR/ArtSource/manifest.json" ]; then
  echo "error: $PROJECT_DIR/ArtSource/manifest.json not found - generate ArtSource with Tools/BlenderArt first." >&2
  exit 2
fi

find_editor() {
  if [ -n "${UE_EDITOR:-}" ]; then
    echo "$UE_EDITOR"
    return
  fi
  local roots=()
  if [ -n "${UE_ROOT:-}" ]; then
    roots+=("$UE_ROOT")
  else
    roots+=("/Users/Shared/Epic Games/UE_5.8" "$HOME/UnrealEngine" "/home/ue4/UnrealEngine" "/opt/UnrealEngine")
  fi
  local root candidate
  for root in "${roots[@]}"; do
    for candidate in \
      "$root/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor-Cmd" \
      "$root/Engine/Binaries/Mac/UnrealEditor-Cmd" \
      "$root/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor" \
      "$root/Engine/Binaries/Linux/UnrealEditor-Cmd" \
      "$root/Engine/Binaries/Linux/UnrealEditor"; do
      if [ -x "$candidate" ]; then
        echo "$candidate"
        return
      fi
    done
  done
}

EDITOR="$(find_editor)"
if [ -z "$EDITOR" ] || [ ! -x "$EDITOR" ]; then
  echo "error: Unreal Editor not found. Set UE_ROOT (folder containing Engine/) or UE_EDITOR (editor binary)." >&2
  exit 2
fi

echo "[build_assets] editor:  $EDITOR"
echo "[build_assets] project: $UPROJECT (force=$FORCE)"
rm -f "$RESULT_FILE"

# IRONREIGN_SKIP_AUTO_IMPORT keeps init_unreal.py from starting a second import inside the commandlet.
IRONREIGN_IMPORT_FORCE="$FORCE" IRONREIGN_SKIP_AUTO_IMPORT=1 "$EDITOR" "$UPROJECT" \
  -run=pythonscript -script="$HERE/run_import.py" \
  -unattended -nopause -nosplash -nosound -stdout -FullStdOutLogOutput \
  ${RHI_ARGS[@]+"${RHI_ARGS[@]}"} ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
EDITOR_STATUS=$?

RESULT="MISSING"
if [ -f "$RESULT_FILE" ]; then
  RESULT="$(head -n 1 "$RESULT_FILE" | tr -d '\r')"
fi
echo "[build_assets] editor exit code $EDITOR_STATUS, import result: $RESULT (details: $STATUS_FILE)"
if [ "$RESULT" = "OK" ]; then
  exit 0
fi
exit 1
