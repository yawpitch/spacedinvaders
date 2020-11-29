#! /usr/bin/env python3
# coding=utf-8
"""
Miscellaneous utilities.
"""
# stdlib imports
from contextlib import contextmanager
from curses import color_pair, has_colors
from textwrap import dedent, shorten, wrap
from typing import Any, Generator, List, TYPE_CHECKING

# local imports
from spacedinvaders.constants import Color


# aliases for mypy only
if TYPE_CHECKING:
    # in 3.8+ we can import the window directly
    try:
        from curses import window as Window
    except ImportError:
        Window = Any
else:
    Window = Any


def regularize(string: str) -> str:
    """
    Regularizes a string, intended for multiline literals.
    Removes leading and trailing blank lines, and ensures that all lines with
    content have the same leading and trailing whitespace.
    """
    lines = [l.rstrip() for l in string.splitlines() if l.strip()]
    width = len(max(lines, key=len))
    return dedent("\n".join(l.ljust(width) for l in lines))


@contextmanager
def colorize(stdscr: Window, color: Color) -> Generator[Window, None, None]:
    """
    Context manager to make colorizing operations easier.
    """
    pair = color_pair(color) if has_colors() else None
    if pair is not None:
        stdscr.attron(pair)
    yield stdscr
    if pair is not None:
        stdscr.attroff(pair)


def fit_within(text: str, rows: int, cols: int) -> List[str]:
    """
    Wrap (and if necessary truncate) text to fit within a box defined by lines
    and cols.
    """
    # shorten can fail if the length is smaller than the default placeholder
    # and wrap can fail if the width ever gets <= 0 ... in either case there
    # is no remaining room to display any text, so return the empty string
    try:
        return wrap(shorten(text, (cols - 2) * (rows - 2)), width=cols - 2)
    except ValueError:
        return [""]


def cursize(rgb: int) -> int:
    """
    Normalize an 8bit RGB value (ie 0-255) to a curses 0-1000 range for curses
    with curses.init_color.
    """
    return round(rgb / 255 * 1000)
