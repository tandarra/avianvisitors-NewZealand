#!/usr/bin/env python3
"""Old name, kept so existing launchers keep working. The script is now bird_illustrations.py."""
import runpy, sys
from pathlib import Path
sys.argv[0] = str(Path(__file__).with_name("bird_illustrations.py"))
runpy.run_path(sys.argv[0], run_name="__main__")
