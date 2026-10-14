#!/bin/bash
# prev3.sh <out_dir> [--preview] : render the three heroes sequentially + side-by-side sheet
D=$1; shift
for n in hero_warlord hero_scholar hero_elder; do
  blender -b --factory-startup -noaudio -P "$(dirname "$0")/run_portrait.py" -- $n $D "$@" 2>&1 | grep -E "\[B\]|Error:|Traceback|line [0-9]|Exception" | grep -v "Not freed"
done
python3 -c "
from PIL import Image
s=Image.new('RGB',(1152,480))
for i,n in enumerate(['hero_warlord','hero_scholar','hero_elder']): s.paste(Image.open('$D/%s.png'%n),(i*384,0))
s.save('$D/trio.png')"
echo DONE
