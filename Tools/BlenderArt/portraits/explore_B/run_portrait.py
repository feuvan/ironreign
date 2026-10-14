"""CLI: blender -b --factory-startup -noaudio -P run_portrait.py -- <spec> <out_dir> [--preview]"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from explore_B import portrait
portrait.main()
