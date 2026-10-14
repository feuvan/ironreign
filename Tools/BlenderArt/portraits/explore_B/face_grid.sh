#!/bin/bash
# face_grid.sh out.png 'json1' 'json2' ...
OUT=$1; shift
TMP=$(mktemp -d)
i=0
for c in "$@"; do
  blender -b --factory-startup -noaudio -P "$(dirname "$0")/dbg_face.py" -- $TMP/f$i.png "$c" >/dev/null 2>&1 &
  i=$((i+1))
  if (( i % 4 == 0 )); then wait; fi
done
wait
python3 - "$OUT" "$TMP" $i <<'PY'
import sys
from PIL import Image
out, tmp, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
ims = [Image.open("%s/f%d.png" % (tmp, k)).convert("RGB") for k in range(n)]
cols = min(4, n); rows = (n + cols - 1) // cols
s = Image.new("RGB", (240 * cols, 300 * rows))
for k, im in enumerate(ims):
    s.paste(im, ((k % cols) * 240, (k // cols) * 300))
s.save(out)
PY
