#! /usr/bin/env python3
# coding=utf-8
"""
A textual, terminal spin on an arcade classic.
"""
# stdlib imports
import curses
import locale
import math
import time

# local imports
from .constants import Color, Control, Direction
from .units import Player, Moveable, Killable, Renderable
from .utils import colorize
from .sounds import Sound

locale.setlocale(locale.LC_ALL, "")
CODEC = locale.getpreferredencoding()

FRAMERATE = 30
REAP_DELAY = 0.4

LEFT_INPUTS = set([Control.LARR, Control.LKEY])
RIGHT_INPUTS = set([Control.RARR, Control.RKEY])
UP_INPUTS = set([Control.UARR, Control.UKEY])
DOWN_INPUTS = set([Control.DARR, Control.DKEY])
STOP_INPUTS = UP_INPUTS | DOWN_INPUTS

ARCADE_ASPECT = 256 / 224
PIXEL_ASPECT = 2.0


def init(stdscr):
    """
    Initialize the main screen state.
    """
    # Hide the cursor
    curses.curs_set(0)

    # Don't block waiting for user input
    stdscr.nodelay(True)

    # Start colors if available
    if curses.has_colors:
        curses.start_color()

        curses.init_pair(Color.RED, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(Color.YELLOW, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(Color.GREEN, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(Color.MAGENTA, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(Color.BLUE, curses.COLOR_BLUE, curses.COLOR_BLACK)
        curses.init_pair(Color.CYAN, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(Color.WHITE, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(Color.BLACK_ON_WHITE, curses.COLOR_BLACK, curses.COLOR_WHITE)


def game(stdscr):

    height, term_width = stdscr.getmaxyx()
    play_width = math.ceil(height / ARCADE_ASPECT * PIXEL_ASPECT)
    if play_width % 2:
        play_width += 1
    padding = (term_width - play_width) // 2

    stdscr.resize(height, play_width)
    stdscr.mvwin(0, padding)

    init(stdscr)

    # Centering calculations
    height, width = stdscr.getmaxyx()

    center_x = int(width // 2)
    center_y = int(height // 2)

    player = Player(center_x, height - 4, speed=0)
    lives = 2
    points = 0
    credits = 0

    last_time = None

    units = [player]

    # Start with a blank canvas
    stdscr.clear()
    stdscr.refresh()

    # Loop where curr_key is the last character pressed
    while (curr_key := stdscr.getch()) != Control.QUIT:

        if curr_key == curses.KEY_RESIZE:
            pass

        # Modulate the time
        curr_time = time.time()
        if last_time is None:
            last_time = curr_time
        delta = curr_time - last_time
        delay = 1.0 / FRAMERATE - delta
        if delay > 0:
            time.sleep(delay)

        last_time = time.time()

        # Initialization
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        center_x = int(width // 2)
        center_y = int(height // 2)

        from curses.ascii import ctrl

        if curr_key == ord(ctrl("d")):
            lives = max(0, lives - 1)
            credits = max(0, credits - 1)

        if curr_key == ord(ctrl("a")):
            lives = min(3, lives + 1)
            credits = min(99, credits + 1)

        # Handle player actions
        if curr_key == Control.FIRE:
            bullet = player.fire()
            if bullet:
                units.append(bullet)
        elif curr_key in STOP_INPUTS:
            player.speed = 0
        elif curr_key in LEFT_INPUTS:
            player.speed = 1
            player.turn(Direction.WEST)
        elif curr_key in RIGHT_INPUTS:
            player.speed = 1
            player.turn(Direction.EAST)

        # Render lives and credits

        with colorize(stdscr, Color.GREEN):
            # stdscr.hline(height - 2, 0, curses.ACS_HLINE, width)
            stdscr.addstr(height - 2, 0, ("━" * (width - 1)).encode(CODEC))

        lives_icons = " ".join(Player.ICON for _ in range(lives))
        with colorize(stdscr, Color.YELLOW):
            stdscr.addstr(height - 1, 0, lives_icons.encode(CODEC))
        credits_digits = f"CREDITS: {credits:02d}".rjust(
            width - len(lives_icons) - 1, " "
        )
        with colorize(stdscr, Color.WHITE):
            stdscr.addstr(height - 1, len(lives_icons), credits_digits)

        def _reap(unit: Renderable) -> bool:
            if isinstance(unit, Killable) and unit.is_dead():
                if (time.time() - unit.time_of_death) > REAP_DELAY:
                    return False
            return True

        # Reap anything that's died
        units = [u for u in units if _reap(u)]

        # Update the units on screen
        for unit in units:
            if isinstance(unit, Moveable):
                unit.move(stdscr)
            unit.render(stdscr)

        # Refresh the screen
        stdscr.refresh()


def main():
    curses.wrapper(game)


if __name__ == "__main__":
    main()
