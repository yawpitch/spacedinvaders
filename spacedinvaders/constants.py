#! /usr/bin/env python3
# coding=utf-8
"""
Various constants used by the game.
"""
from __future__ import annotations

# stdlib imports
import curses
import curses.ascii
from collections import deque
from enum import IntEnum, IntFlag, auto
from typing import Deque


class Color(IntEnum):
    """
    The various colors for display.
    """

    RED = auto()
    YELLOW = auto()
    GREEN = auto()
    MAGENTA = auto()
    BLUE = auto()
    CYAN = auto()
    WHITE = auto()


class Control(IntEnum):
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
    BKEY = ord("b")
    ENTR = curses.KEY_ENTER
    NEWL = ord("\n")
    RETN = ord("\r")

    @classmethod
    def is_left(cls, command: int) -> bool:
        """
        Check if a valid left control has been issued.
        """
        return command in set([cls.LARR, cls.LKEY])

    @classmethod
    def is_right(cls, command: int) -> bool:
        """
        Check if a valid left control has been issued.
        """
        return command in set([cls.RARR, cls.RKEY])

    @classmethod
    def is_up(cls, command: int) -> bool:
        """
        Check if a valid up control has been issued.
        """
        return command in set([cls.UARR, cls.UKEY])

    @classmethod
    def is_down(cls, command: int) -> bool:
        """
        Check if a valid left control has been issued.
        """
        return command in set([cls.DARR, cls.DKEY])

    @classmethod
    def is_enter(cls, command: int) -> bool:
        """
        Check if a valid Enter / Return key has been hit.
        """
        return command in set([cls.ENTR, cls.NEWL, cls.RETN])

    @staticmethod
    def has_komando(last10: Deque[Control]) -> bool:
        """
        Check if the player has komando'd.
        """
        return last10 == KOMANDO


KOMANDO = deque(
    [Control.UARR] * 2
    + [Control.DARR] * 2
    + [Control.LARR, Control.RARR] * 2
    + [Control.BKEY, Control.LKEY]
)


class Direction(IntFlag):
    """
    Screen directions.
    """

    NORTH = auto()
    EAST = auto()
    SOUTH = auto()
    WEST = auto()


class Stage(IntFlag):
    """
    Stages of play.
    """

    REDRAW = auto()
    SPAWN = auto()
    RUNNING = auto()
    DEATH = auto()
    WIN = auto()
    GAME_OVER = auto()
