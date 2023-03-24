#!/usr/bin/env python3
import re
import os
import sys
sys.path.append(rf"{os.environ['HOME']}/install/lib/include")
from myPython.common import cmd

CSOURCE = sys.argv[1]
NAME = os.path.splitext(CSOURCE.replace('source/', ''))[0]
print(NAME)
# Main
cmd(f'cppcheck {CSOURCE}')
cmd(f"gcc {CSOURCE} -o bin/{NAME}")
