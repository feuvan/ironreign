#!/bin/bash
# full3.sh <out_dir> : full-quality render of the three heroes with CPU timing
D=$1
TIMEFORMAT='TIME %R s wall, %U s user, %S s sys'
for n in hero_elder hero_scholar hero_warlord; do
  echo "== $n"
  { time blender -b --factory-startup -noaudio -P "$(dirname "$0")/run_portrait.py" -- $n $D 2>&1 | grep -E "\[B\]|Error:|Traceback|line [0-9]" | grep -v "Not freed" ; } 2>&1
done
python3 "$(dirname "$0")/make_sheet.py" $D
echo DONE
