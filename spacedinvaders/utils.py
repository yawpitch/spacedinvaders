#! /usr/bin/env python3
# coding=utf-8
"""
Miscellaneous utilities.
"""
# stdlib imports
from contextlib import contextmanager
from curses import color_pair, has_colors
from textwrap import dedent, shorten, wrap
from typing import Generator, List

# local imports
from spacedinvaders.constants import Color
from spacedinvaders.typing import Col, Row, Window


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


def fit_within(text: str, rows: Row, cols: Col) -> List[str]:
    """
    Wrap (and if necessary truncate) text to fit within a box defined by lines
    and cols.
    """
    return wrap(shorten(text, (cols - 2) * (rows - 2)), cols=cols - 2)
