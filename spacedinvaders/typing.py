#! /usr/bin/env python3
# coding=utf-8
"""
Types for use throughout the codebase.
"""
# stdlib imports
import curses
from typing import NewType

# type alias just to keep signatures cleaner
Window = curses.window

# types for fundamental values
Row = NewType("Row", int)
Col = NewType("Col", int)
