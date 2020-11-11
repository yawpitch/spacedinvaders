#! /usr/bin/env python3
# coding=utf-8
"""
Various constants used by the game.
"""
# stdlib imports
import curses
import curses.ascii
from enum import IntFlag, auto


class Color(IntFlag):
    """
    The various colors for display.
    """

    RED = auto()
    YELLOW = auto()
    GREEN = auto()
    MAGENTA = auto()
    BLUE = auto()
    CYAN = auto()
    BLACK_ON_WHITE = auto()


class Control(IntFlag):
    """
    The valid keyboard controls.
    """

    NULL = -1
    QUIT = ord(curses.ascii.ctrl("q"))
    UARR = curses.KEY_UP
    UKEY = ord("w")
    DARR = curses.KEY_DOWN
    DKEY = ord("s")
    LARR = curses.KEY_LEFT
    LKEY = ord("a")
    RARR = curses.KEY_RIGHT
    RKEY = ord("d")
    FIRE = curses.ascii.SP


class Direction(IntFlag):
    """
    Screen directions.
    """
    NORTH = auto()
    EAST = auto()
    SOUTH = auto()
    WEST = auto()
