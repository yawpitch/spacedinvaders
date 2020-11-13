#! /usr/bin/env python3
# coding=utf-8
"""
A textual, terminal spin on an arcade classic.
"""
# stdlib imports
import curses
import locale
import math
import os
import time
from typing import Tuple, Optional

# local imports
from .constants import Color, Control, Direction
from .units import *
from .utils import colorize, fit_within
from .sounds import Sound
from .typing import Window, Row, Col

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
BARRIER_WIDTH = len(Barrier.ICON.splitlines()[0])
BARRIER_HEIGHT = len(Barrier.ICON.splitlines())
ARENA_WIDTH = BARRIER_WIDTH * 10
ARENA_HEIGHT = round(ARENA_WIDTH * ARCADE_ASPECT / PIXEL_ASPECT)
if ARENA_HEIGHT % 2:
    ARENA_HEIGHT += 1


class PlayState:
    """
    Class to track the current game state.
    """

    def __init__(self):
        self._score: int = 0
        self._high: int = 999
        self._lives: int = 2
        self._credits: int = 0
        self._bullet: Optional[Bullet] = None

    @property
    def score(self) -> int:
        """
        Player's current score.
        """
        return self._score

    @score.setter
    def score(self, val: int) -> int:
        """
        Update the player's score.
        """
        self._score = val

    @property
    def high(self) -> int:
        """
        The current high score.
        """
        return self._high

    @high.setter
    def high(self, val: int) -> int:
        """
        Update the current high score.
        """
        self._high = val

    @property
    def lives(self) -> int:
        """
        Player's current number of lives.
        """
        return self._lives

    @lives.setter
    def lives(self, val: int) -> None:
        """
        Update the player's number of lives.
        Maintains the range 0-3 inclusive.
        """
        self._lives = max(0, min(val, 3))

    @property
    def credits(self) -> int:
        """
        Player's current number of credits.
        """
        return self._credits

    @credits.setter
    def credits(self, val: int) -> None:
        """
        Update the player's number of credits.
        Maintains the range 0-99 inclusive.
        """
        self._credits = max(0, min(val, 99))

    @property
    def bullet(self) -> Optional[Bullet]:
        """
        Player's current bullet, if any.
        """
        return self._bullet

    @bullet.setter
    def bullet(self, fired: Optional[Bullet]) -> None:
        """
        Update the player's bullet.
        """
        self._bullet = fired


def initialize_screen(stdscr: Window) -> None:
    """
    Initialize the main screen state.
    """
    # hide the cursor
    curses.curs_set(0)

    # don't block waiting for user input
    stdscr.nodelay(True)

    # start colors if available
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

    # center the play arena in the terminal
    resize_arena(stdscr)

    # start with a blank canvas
    stdscr.clear()
    stdscr.refresh()


def reflow_max(stdscr: Window) -> None:
    """
    Resize the screen back to current terminal extents.
    """
    # update curses.LINES and curses.COLS to reflect terminal size
    curses.update_lines_cols()

    # blank the screen
    stdscr.clear()
    stdscr.refresh()

    # reflow back to terminal extents
    stdscr.resize(curses.LINES, curses.COLS)
    stdscr.mvwin(0, 0)


def resize_arena(stdscr: Window, *, reflow: bool = False) -> None:
    """
    Resize and center the gameplay arena; also handle resizes that are too small.
    """
    # reflow back to screen extents if terminal has been resized
    if reflow:
        reflow_max(stdscr)

    term_height, term_width = stdscr.getmaxyx()

    # resize the arena and calculate centering
    stdscr.resize(ARENA_HEIGHT, ARENA_WIDTH)
    y_pad = round((term_height - ARENA_HEIGHT) / 2)
    x_pad = round((term_width - ARENA_WIDTH) / 2)

    # perform centering, error means terminal is too small for the arena
    try:
        stdscr.mvwin(y_pad, x_pad)
    except curses.error:
        reflow_max(stdscr)
        height, width = stdscr.getmaxyx()
        msg = (
            f"Terminal must be at least {ARENA_HEIGHT} rows x "
            f"{ARENA_WIDTH} cols. Resize to continue, CTRL+C to exit."
        )
        lines = fit_within(msg, height, width)
        x_pos = round((width - len(max(lines, key=len))) / 2)
        y_start = round(height / 2) - round(len(lines) / 2)
        with colorize(stdscr, Color.RED):
            for y_pos, line in enumerate(lines, start=y_start):
                stdscr.addstr(y_pos, x_pos, line)
        stdscr.refresh()

        # block until a resize or SIGTERM exits
        stdscr.timeout(-1)
        while (curr_key := stdscr.getch()) != curses.KEY_RESIZE:
            continue
        else:
            stdscr.nodelay(True)
            return resize_arena(stdscr, reflow=True)

    # Mark the window for redraw
    stdscr.redrawwin()


def draw_hud(stdscr: Window, height: Row, width: Col, state: PlayState) -> None:
    """
    Render the Player's status to the arena HUD.
    """
    # render top status bar
    bar_y = 1
    label = "SCORE: "
    score = f"{state.score:04d}"
    with colorize(stdscr, Color.BLUE):
        stdscr.addstr(bar_y, 0, label, curses.A_DIM)
        stdscr.addstr(bar_y, len(label), score, curses.A_BOLD)

    label = "HIGH SCORE: "
    high = f"{state.high:04d}"
    with colorize(stdscr, Color.BLUE):
        stdscr.addstr(bar_y, width - 1 - len(label + high), label, curses.A_DIM)
        stdscr.addstr(bar_y, width - 1 - len(high), high, curses.A_BOLD)

    # render arena bottom
    floor_y = height - 2
    with colorize(stdscr, Color.GREEN):
        stdscr.addstr(floor_y, 0, ("▀" * (width - 1)).encode(CODEC))  # "━"

    # render bottom status bar
    bar_y = height - 1
    lives = " ".join(Player.ICON for _ in range(state.lives)).encode(CODEC)
    with colorize(stdscr, Color.YELLOW):
        stdscr.addstr(bar_y, 0, lives)
    label = "CREDITS: "
    creds = f"{state.credits:02d}"
    with colorize(stdscr, Color.WHITE):
        stdscr.addstr(bar_y, width - 1 - len(label + creds), label, curses.A_DIM)
        stdscr.addstr(bar_y, width - 1 - len(creds), creds, curses.A_BOLD)


def game_loop(stdscr: Window) -> None:

    # prepare the screen
    initialize_screen(stdscr)

    # get the up to date extents
    height, width = stdscr.getmaxyx()

    # calculate the new center points
    center_y, center_x = round(height / 2), round(width / 2)

    player = Player(center_x, height - 4, speed=0)
    state = PlayState()

    last_time = None

    units = [player]

    # place the barriers
    barrier_x = round(BARRIER_WIDTH * 1.5)
    barrier_y = player.y - player.h - BARRIER_HEIGHT
    for idx in range(4):
        units.append(Barrier(barrier_x, barrier_y))
        barrier_x += BARRIER_WIDTH * 2

    # loop where curr_key is the last character pressed or -1 on no input
    while (curr_key := stdscr.getch()) != Control.QUIT:

        # modulate the time to keep rhe loop relatively constant
        curr_time = time.time()
        delay = 1.0 / FRAMERATE - (curr_time - (last_time or curr_time))
        if delay > 0:
            time.sleep(delay)
        last_time = time.time()

        # handle terminal resize events
        if curr_key == curses.KEY_RESIZE:
            resize_arena(stdscr, reflow=True)
            height, width = stdscr.getmaxyx()
            center_y, center_x = round(height / 2), round(width / 2)
            stdscr.clear()
            stdscr.refresh()

        # erase the screen for redraw
        stdscr.erase()

        from curses.ascii import ctrl

        if curr_key == ord(ctrl("d")):
            state.lives -= 1
            state.credits -= 1

        if curr_key == ord(ctrl("a")):
            state.lives += 1
            state.credits += 1

        # handle player actions
        if curr_key == Control.FIRE:
            state.bullet = player.fire()
            if state.bullet:
                units.append(state.bullet)
        elif curr_key in STOP_INPUTS:
            player.speed = 0
        elif curr_key in LEFT_INPUTS:
            player.speed = 1
            player.turn(Direction.WEST)
        elif curr_key in RIGHT_INPUTS:
            player.speed = 1
            player.turn(Direction.EAST)

        # render HUD information
        draw_hud(stdscr, height, width, state)

        def _reap(unit: Renderable) -> bool:
            if isinstance(unit, Killable) and unit.is_dead():
                if (time.time() - unit.time_of_death) > REAP_DELAY:
                    return False
            return True

        # reap anything that's died
        units = [u for u in units if _reap(u)]

        # update the units on screen
        for unit in units:
            if isinstance(unit, Moveable):
                unit.move(stdscr)
            if state.bullet and unit is not player and unit is not state.bullet:
                if (
                    (state.bullet.x + state.bullet.w > unit.x)
                    and (state.bullet.x < unit.x + unit.w)
                    and (state.bullet.y + state.bullet.h >= unit.y)
                    and (state.bullet.y <= unit.y + unit.h)
                ):
                    if isinstance(unit, Barrier):
                        icon = [list(r) for r in unit.icon.splitlines()]
                        hit_x = state.bullet.x - unit.x
                        hit_y = state.bullet.y - unit.y
                        while hit_y >= 0 and icon[hit_y][hit_x] == " ":
                            hit_y -= 1
                        if hit_y < 0:
                            continue
                        icon[hit_y][hit_x] = " "
                        unit.icon = "\n".join("".join(i) for i in icon)
                        state.bullet.die()
                        state.bullet = None

        if state.bullet is None and not Bullet.in_flight():
            units = [u for u in units if not isinstance(u, Bullet)]

        for unit in units:
            unit.render(stdscr)

        # refresh the screen
        stdscr.refresh()


def main() -> None:
    curses.wrapper(game_loop)


if __name__ == "__main__":
    main()
