#! /usr/bin/env python3
# coding=utf-8
"""
Miscellaneous utilities.
"""
# stdlib imports
import curses
from contextlib import contextmanager
from textwrap import dedent
from typing import Generator, Optional

# local imports
from spacedinvaders.constants import Color

# type alias just to keep signatures cleaner
Window = curses.window

HAS_COLORS: Optional[bool] = None


def regularize(string: str) -> str:
    """
    Regularizes a string, intended for multiline literals.
    Removes leading and trailing blank lines, and ensures
    all lines with content have the same leading and trailing
    whitespace.
    """
    lines = [l.rstrip() for l in string.splitlines() if l.strip()]
    width = len(max(lines, key=len))
    return dedent("\n".join(l.ljust(width) for l in lines))


@contextmanager
def colorize(stdscr: Window, color: Color) -> Generator[Window, None, None]:
    """
    Context manager to make colorizing operations easier.
    """
    # never a fan of global variables, but hate to keep inspecting
    # a constant value
    global HAS_COLORS
    if HAS_COLORS is None:
        HAS_COLORS = curses.has_colors()

    pair = curses.color_pair(color)
    if HAS_COLORS:
        stdscr.attron(pair)
    yield stdscr
    if HAS_COLORS:
        stdscr.attroff(pair)
