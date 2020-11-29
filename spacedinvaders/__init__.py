#! /usr/bin/env python3
# coding=utf-8
"""
A textual, terminal spin on an arcade classic.
"""
# pylint: disable=too-many-lines

# stdlib imports
import argparse
import curses
import locale
import os
import string
import sqlite3
import sys
import time
from collections import deque
from functools import partial
from itertools import cycle
from random import randint
from textwrap import dedent, indent
from typing import Any, List, NamedTuple, Optional, Set, Tuple, TYPE_CHECKING

# local imports
# pylint: disable=import-error
from .constants import Color, Control, Direction, Stage
from .exceptions import SuccessfulInvasion
from .letters import A, C, D, E, G, I, M, N, O, P, R, S, V
from .sounds import Sound
from .units import (
    Barrier,
    Bullet,
    Crab,
    Gestalt,
    Invader,
    Mystery,
    Player,
    Octopus,
    Squid,
    SuperBomb,
)
from .utils import colorize, cursize, fit_within

__version__ = "0.0.4"

locale.setlocale(locale.LC_ALL, "")

CODEC = locale.getpreferredencoding()
FRAMERATE = 60

# Constants that represent the screen dimensions
ARCADE_ASPECT = 256 / 224
PIXEL_ASPECT = 2.0
BARRIER_WIDTH = len(Barrier.ICON.splitlines()[0])
BARRIER_HEIGHT = len(Barrier.ICON.splitlines())
ARENA_WIDTH = BARRIER_WIDTH * 10
ARENA_HEIGHT = round(ARENA_WIDTH * ARCADE_ASPECT / PIXEL_ASPECT)
if ARENA_HEIGHT % 2:
    ARENA_HEIGHT += 1


# aliases for mypy only
if TYPE_CHECKING:
    # in 3.8+ we can import the window directly
    try:
        from curses import window as Window
    except ImportError:
        Window = Any
else:
    Window = Any


class ScoresDB:
    """
    Database for tracking high scores.
    """

    def __init__(self):
        self._leaders: Optional[List[Tuple[str, int]]] = None
        self.path = os.path.join(
            os.path.expandvars(
                os.path.expanduser(
                    os.environ.get(
                        "SPACEDINVADERS_DATA_HOME",
                        os.environ.get("XDG_DATA_HOME", "~/.local/share"),
                    )
                )
            ),
            "spacedinvaders/scores.sqlite",
        )
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        query = dedent(
            """
            CREATE TABLE IF NOT EXISTS scores (
              id INTEGER PRIMARY KEY,
              name TEXT NOT NULL,
              score INTEGER NOT NULL,
              CHECK (
                length(name) == 3
                AND score >= 0
                AND score <= 9999
              )
            );
            """
        ).strip()
        self.con.execute(query)

    @property
    def leaders(self) -> List[Tuple[str, int]]:
        """
        The top 10 current leaders.
        """
        # use cached data if available
        if self._leaders is not None:
            return self._leaders

        query = dedent(
            """
            SELECT
              name, score
            FROM
              scores
            ORDER BY
              score DESC,
              id ASC
            LIMIT 10;
            """
        ).strip()

        self._leaders = [
            (l["name"], l["score"]) for l in self.con.execute(query).fetchall()
        ]
        return self._leaders

    @property
    def high(self) -> int:
        """
        The current high score, or 0 if no score has been set.
        """
        return self.leaders[0][1] if self.leaders else 0

    @property
    def low(self) -> int:
        """
        The current lowest ranked score, or 0 if no score has been set.
        """
        return self.leaders[-1][1] if self.leaders else 0

    def insert(self, name: str, score: int) -> None:
        """
        Records a new score in the database.
        """
        query = dedent(
            """
            INSERT INTO
              scores (name, score)
            VALUES
              (?, ?);
            """
        ).strip()

        with self.con:
            self.con.execute(query, (name, score))

        # clear the cache
        self._leaders = None


DB = ScoresDB()


class PlayState:
    """
    Class to track the current game state.
    """

    # pylint: disable=too-many-instance-attributes

    def __init__(self, *, demo_mode=False):
        self._screen: int = 2 if demo_mode else 0
        self._frame: int = 0
        self._score: int = 0
        self._high: int = 9999 if demo_mode else DB.high
        self._lives: int = 2 if demo_mode else 3
        self._stage: Stage = Stage.REDRAW
        self._respawn_delay: int = round(1.5 * FRAMERATE)
        self._credits: int = 0
        self._bullet: Optional[Bullet] = None
        self._bullet_count: int = 0
        self._bullet_delay: int = 0
        self._mystery: Optional[Mystery] = None
        self._mystery_frame: Optional[int] = 35 * FRAMERATE
        self._last_kills: List[Invader] = []
        self._demo: bool = demo_mode
        self.last10 = deque(maxlen=10)
        self.egged = False

    @property
    def screen(self) -> int:
        """
        Current screen.
        """
        return self._screen

    @screen.setter
    def screen(self, val: int):
        """
        Update the current screen.
        """
        self._screen = val
        self._frame = 0
        self._stage = Stage.REDRAW
        self._bullet = None
        self._bullet_count = 0
        self._bullet_delay = 0
        self._mystery = None
        self._mystery_frame = 25 * FRAMERATE
        self._last_kills.clear()

    @property
    def frame(self) -> int:
        """
        Current frame.
        """
        return self._frame

    @frame.setter
    def frame(self, val: int):
        """
        Update the current frame.
        """
        if self._mystery_frame is not None:
            self._mystery_frame -= 1
        if self._respawn_delay:
            self._respawn_delay -= 1
        self._bullet_delay = max(0, self._bullet_delay - 1)
        self._frame = val

    @property
    def score(self) -> int:
        """
        Player's current score.
        """
        return self._score

    @score.setter
    def score(self, val: int):
        """
        Update the player's score.
        """
        old_score = self._score
        self._score = val
        if not self._demo:
            if old_score < 1500 <= self._score:
                self.lives += 1
            self.high = max(self.high, self._score)

    @property
    def high(self) -> int:
        """
        The current high score.
        """
        return self._high

    @high.setter
    def high(self, val: int):
        """
        Update the current high score.
        """
        self._high = val

    def has_topped(self) -> bool:
        """
        Check if the player has set a new top / highest score.
        """
        return False if self._demo else self.score > DB.high

    def has_ranked(self) -> bool:
        """
        Check if the player has set a new ranked score.
        """
        return False if self._demo else self.score > DB.low

    @property
    def lives(self) -> int:
        """
        Player's current number of lives.
        """
        return self._lives

    @lives.setter
    def lives(self, val: int):
        """
        Update the player's number of lives.
        Maintains the range 0-3 inclusive.
        """
        if val < self._lives:
            self._handling_death = True
        self._lives = max(0, min(val, 4))

    @property
    def stage(self) -> Stage:
        """
        Current stage in the game.
        """
        return self._stage

    @stage.setter
    def stage(self, new_stage: Stage):
        """
        Update the game stage.
        """
        if new_stage is Stage.SPAWN:
            self._respawn_delay = round(1.5 * FRAMERATE)
        self._stage = new_stage

    def can_spawn(self) -> bool:
        """
        Is the player eligible to respawn?
        """
        return not self._respawn_delay

    @property
    def credits(self) -> int:
        """
        Player's current number of credits.
        """
        return self._credits

    @credits.setter
    def credits(self, val: int):
        """
        Update the player's number of credits.
        Maintains the range 0-99 inclusive.
        """
        self._credits = max(0, min(val, 99))

    @property
    def player_start_x(self) -> int:
        """
        Starting x position for the player, from screen left.
        """
        return 8

    @property
    def player_start_y(self) -> int:
        """
        Starting y offset from screen bottom.
        """
        return 4

    @property
    def invaders_start_x(self) -> int:
        """
        Starting x position for the invaders, from screen left.
        """
        return 12

    @property
    def invaders_start_y(self) -> int:
        """
        Starting y position for the invaders, from screen top.
        """
        return [8, 10, 14, 18, 18, 18, 20, 20, 20][self.screen % 9]

    def can_fire(self) -> bool:
        """
        Check if the player can fire.
        """
        return not self._bullet_delay

    @property
    def bullet(self) -> Optional[Bullet]:
        """
        Player's current bullet, if any.
        """
        return self._bullet

    @bullet.setter
    def bullet(self, fired: Optional[Bullet]):
        """
        Update the player's bullet.
        """
        if fired is None:
            self._bullet_delay += 20
            self._bullet_count += 1
        self._bullet = fired

    @property
    def bullet_count(self) -> int:
        """
        The number of bullets that have been fired.
        """
        return self._bullet_count

    @property
    def mystery(self) -> Optional[Mystery]:
        """
        The mystery ship on screen, if any.
        """
        return self._mystery

    @mystery.setter
    def mystery(self, ship: Optional[Mystery]):
        """
        Update the mystery ship on screen.
        """
        if ship is None:
            self._mystery_frame = FRAMERATE * 25
        else:
            self._mystery_frame = None
        self._mystery = ship

    @property
    def mystery_frame(self) -> Optional[int]:
        """
        Countdown to mystery ship launch.
        """
        if self._mystery_frame is None:
            return 666
        return self._mystery_frame

    @mystery_frame.setter
    def mystery_frame(self, val: Optional[int]):
        """
        Reset (or stop) the countdown.
        """
        self._mystery_frame = val

    @property
    def last_kills(self) -> List[Invader]:
        """
        Player's last kills, if any.
        """
        return self._last_kills


def reflow_max(stdscr: Window) -> None:
    """
    Resize the screen back to current terminal extents.
    """
    # pylint: disable=no-member

    # update curses.LINES and curses.COLS to reflect terminal size
    curses.update_lines_cols()

    # blank the screen
    stdscr.clear()
    stdscr.refresh()

    # reflow back to terminal extents
    stdscr.resize(curses.LINES, curses.COLS)

    # moving back to the origin occasionally fails on floating windows
    # but since this is really just a safety fallback it should be fine
    # to occasionally skip it and let it happen on the next resize
    try:
        stdscr.mvwin(0, 0)
    except curses.error:
        pass


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
        while stdscr.getch() != curses.KEY_RESIZE:
            continue
        stdscr.nodelay(True)
        resize_arena(stdscr, reflow=True)
        return

    # Mark the window for redraw
    stdscr.redrawwin()


def draw_hud(stdscr: Window, height: int, width: int, state: PlayState) -> None:
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
    lives = " ".join(Player.ICON for _ in range(state.lives - 1)).encode(CODEC)
    with colorize(stdscr, Color.YELLOW):
        stdscr.addstr(bar_y, 0, lives)
    label = "CREDITS: "
    creds = f"{state.credits:02d}"
    with colorize(stdscr, Color.WHITE):
        stdscr.addstr(bar_y, width - 1 - len(label + creds), label, curses.A_DIM)
        stdscr.addstr(bar_y, width - 1 - len(creds), creds, curses.A_BOLD)


def typeon(
    stdscr: Window,
    center_x: int,
    start_y: int,
    message: List[List[str]],
    up_to: int,
    *,
    delay: int = 10,
) -> Tuple[int, int]:
    """
    Type on the given big type message, up to the given character.
    Returns a tuple of the number of letters to display and the number of
    letters actually displayed.
    """
    length = len(message)
    x_pos = center_x - round(sum(len(c[0]) for c in message) / 2)
    letter_count = 0
    for letter_count, letter in enumerate(message[:up_to], start=1):
        line = ""
        for line_idx, line in enumerate(letter):
            with colorize(stdscr, Color.RED if line_idx < 2 else Color.WHITE):
                stdscr.addstr(start_y + line_idx, x_pos, line)
        x_pos += len(line)
        if letter_count == up_to and letter_count != length:
            curses.delay_output(delay)
    return length, letter_count


def govern(last_time: Optional[float]) -> float:
    """
    Govern a loop to keep it ticking over at FRAMERATE.
    Returns the last time this function returned, which
    should be fed back in with future calls.
    """
    curr_time = time.time()
    last_time = curr_time if last_time is None else curr_time
    delay = 1.0 / FRAMERATE - (curr_time - last_time)
    if delay > 0:
        time.sleep(delay)
    return time.time()


def record(stdscr: Window, score: int, *, is_top: bool = True) -> int:
    """
    Loop for recording a new high score.
    """
    # pylint: disable=too-many-locals, too-many-statements, too-many-branches

    # get the up to date extents
    height, width = stdscr.getmaxyx()

    # calculate the new center points
    center_y, center_x = round(height / 2), round(width / 2)
    half_width = center_x
    quarter_width = round(half_width / 2)

    popup = stdscr.derwin(8, half_width + 2, center_y - 5, center_x - quarter_width - 1)
    # get the popup extents
    height, width = popup.getmaxyx()

    # calculate the new center points
    center_y, center_x = round(height / 2), round(width / 2)

    # clear the popup
    popup.clear()

    # draw the fancy box
    with colorize(popup, Color.WHITE):
        # pylint: disable=invalid-name

        x, y, w, h = 0, 0, width - 1, height - 2
        popup.addstr(y, x, "╭" + ("─" * (w - 1)) + "╮", curses.A_DIM)
        for i in range(y + 1, h):
            popup.addstr(i, x, "│", curses.A_DIM)
            popup.addstr(i, w, "│", curses.A_DIM)

        popup.addstr(h, x, "╰" + ("─" * (w - 1)) + "╯", curses.A_DIM)

    # draw the static lines
    if is_top:
        start, end = "CONGRATULATIONS ON A NEW ", "HIGH SCORE"
    else:
        start, end = "YOU'VE MADE IT ONTO THE ", "LEADER BOARD"
    start_y = center_y - 2
    start_x = center_x - round(len(start + end) / 2)
    with colorize(stdscr, Color.WHITE):
        popup.addstr(start_y, start_x, start, curses.A_DIM)
        start_x += len(start)
        popup.addstr(start_y, start_x, end, curses.A_BOLD)

    valid = string.ascii_uppercase + string.digits + string.punctuation
    convertible = set(ord(c) for c in valid + string.ascii_lowercase)
    chars = ["A", "A", "A"]
    highlight = 0

    label = "PLEASE ENTER YOUR INITIALS: "
    start_y += 1
    start_x = center_x - round((len(label) + len(chars)) / 2)
    selector_y = start_y
    selector_x = start_x + len(label)
    with colorize(stdscr, Color.WHITE):
        popup.addstr(start_y, start_x, label, curses.A_DIM)
        for idx, char in enumerate(chars):
            if idx == highlight:
                popup.addstr(selector_y, selector_x + idx, char, curses.A_STANDOUT)
            else:
                popup.addstr(selector_y, selector_x + idx, char, curses.A_BOLD)

    start = "HIT "
    mid = "ENTER"
    end = " TO COMMIT"
    start_y += 1
    start_x = center_x - round((len(start) + len(mid) + len(end)) / 2)
    with colorize(stdscr, Color.WHITE):
        popup.addstr(start_y, start_x, start, curses.A_DIM)
        start_x += len(start)
        popup.addstr(start_y, start_x, mid, curses.A_BOLD)
        start_x += len(mid)
        popup.addstr(start_y, start_x, end, curses.A_DIM)

    # pylint hasn't quite caught up to the walrus, it seems
    # pylint: disable=used-before-assignment

    # loop where curr_key is the last character pressed or -1 on no input
    while True:

        # get the key pressed
        curr_key = stdscr.getch()

        # handle user exit
        if curr_key == Control.QUIT or Control.is_enter(curr_key):
            break

        if curr_key == Control.LARR:
            highlight = max(0, highlight - 1)
        elif curr_key == Control.RARR:
            highlight = min(len(chars) - 1, highlight + 1)
        elif curr_key == Control.UARR:
            curr = valid.index(chars[highlight])
            chars[highlight] = valid[(curr - 1) % len(valid)]
        elif curr_key == Control.DARR:
            curr = valid.index(chars[highlight])
            chars[highlight] = valid[(curr + 1) % len(valid)]
        elif curr_key in convertible:
            chars[highlight] = chr(curr_key).upper()
            highlight = min(len(chars) - 1, highlight + 1)

        with colorize(stdscr, Color.WHITE):
            for idx, char in enumerate(chars):
                if idx == highlight:
                    popup.addstr(selector_y, selector_x + idx, char, curses.A_STANDOUT)
                else:
                    popup.addstr(selector_y, selector_x + idx, char, curses.A_BOLD)

        popup.refresh()

    # commit the new high score to the database
    if Control.is_enter(curr_key):
        DB.insert("".join(chars), score)

    return curr_key


def attract(stdscr: Window, *, use_sound: bool = True) -> int:
    """
    The attraction screen loop, which entices the punters to play.
    """
    # pylint: disable=too-many-statements, too-many-branches, too-many-locals

    # don't block waiting for user input
    stdscr.nodelay(True)

    # get the up to date extents
    height, width = stdscr.getmaxyx()

    # calculate the new center points
    center_y, center_x = round(height / 2), round(width / 2)

    # used to modulate the game loop
    last_time = None

    # we'll use this to schedule events
    frame = 0

    # used to control progressive type on effects
    typeon_spaced = typeon_invaders = 1
    typeon_advance_table = typeon_leaderboard = 0

    # get the current leaderboard
    leaderboard = DB.leaders

    # count the number of times we've displayed all the splash
    splash_count = 0

    # pylint: disable=used-before-assignment

    # loop where curr_key is the last character pressed or -1 on no input
    while True:

        # get the key pressed
        curr_key = stdscr.getch()

        # handle user exit
        if curr_key == Control.QUIT or curr_key == Control.FIRE:
            break

        # modulate the time to keep rhe loop relatively constant
        last_time = govern(last_time)

        # handle terminal resize events
        if curr_key == curses.KEY_RESIZE:
            resize_arena(stdscr, reflow=True)
            height, width = stdscr.getmaxyx()
            center_y, center_x = round(height / 2), round(width / 2)
            stdscr.clear()
            stdscr.refresh()

        # erase the existing screen
        stdscr.erase()

        # if we've gone around enough times, run the demo
        if splash_count == (1 if leaderboard else 2):
            stdscr.refresh()
            curses.delay_output(500)
            if play(stdscr, use_sound=False, demo_mode=True) == Control.QUIT:
                return Control.QUIT
            splash_count = 0
            continue

        start_y = center_y - 12

        if 20 <= frame % FRAMERATE <= 55:
            message = "PRESS SPACE TO PLAY"
            start_x = center_x - round(len(message) / 2)
            with colorize(stdscr, Color.WHITE):
                for word in message.split():
                    attrs = curses.A_BOLD if word == "SPACE" else curses.A_DIM
                    stdscr.addstr(start_y, start_x, word, attrs)
                    start_x += len(word) + 1

        start_y += 2
        spaced = [S, P, A, C, E, D]
        spaced_count, spaced_typed = typeon(
            stdscr, center_x, start_y, spaced, typeon_spaced, delay=50
        )

        if spaced_count == spaced_typed:
            invaders = [I, N, V, A, D, E, R, S]
            typeon(stdscr, center_x, start_y + 3, invaders, typeon_invaders, delay=50)
            typeon_invaders += 1

        typeon_spaced += 1

        if frame == 0:
            typeon_advance_table = typeon_leaderboard = 0

        # draw the score advance table
        splash_on = round(FRAMERATE * 0.65)
        splash_off = splash_on + 6 * FRAMERATE
        if splash_on <= frame <= splash_off:
            start_y += 9
            end_w = 35
            message = "SCORE ADVANCE TABLE".center(end_w)
            start_x = center_x - round(len(message) / 2)
            with colorize(stdscr, Color.WHITE):
                stdscr.addstr(
                    start_y,
                    start_x,
                    message,
                    curses.A_DIM | curses.A_BOLD | curses.A_STANDOUT,
                )

            table = [
                (Mystery.ICON.splitlines(), Mystery.COLOR, "? MYSTERY"),
                (Squid.ICON.splitlines(), Color.WHITE, f"{Squid.POINTS} POINTS"),
                (Crab.ICON.splitlines(), Color.WHITE, f"{Crab.POINTS} POINTS"),
                (
                    Octopus.ICON.splitlines(),
                    Color.YELLOW,
                    f"{Octopus.POINTS} POINTS",
                ),
            ]

            first_entry_delay = splash_on + round(FRAMERATE * 0.20)
            if frame > first_entry_delay and frame % FRAMERATE == 40:
                typeon_advance_table += 1
                if use_sound and typeon_advance_table <= len(table):
                    Sound.INVADER.play()

            start_y += 2
            pad_x = max([len(i[0][0]) for i in table])
            for critter_idx, (icon, color, points) in enumerate(
                table[:typeon_advance_table]
            ):
                for idx, line in enumerate(icon):
                    with colorize(stdscr, color):
                        stdscr.addstr(start_y + idx, start_x + 2, line.center(pad_x))
                    if (critter_idx == 0 and idx == 1) or (critter_idx and idx == 0):
                        with colorize(
                            stdscr, Color.WHITE if color != Color.YELLOW else color
                        ):
                            stdscr.addstr(
                                start_y + idx,
                                start_x + end_w - len(points) - 2,
                                points,
                            )
                start_y += len(icon)
                if critter_idx > 0:
                    start_y += 1

            # increment the splash screen counter when fully drawn
            if typeon_advance_table == len(table):
                typeon_advance_table += 1

        if leaderboard:
            splash_on = splash_off + splash_on
            splash_off = splash_on + max(
                FRAMERATE * 6, FRAMERATE * (len(leaderboard) + 1)
            )
        if leaderboard and splash_on <= frame <= splash_off:

            start_y += 9
            end_w = 35
            message = "HIGH SCORES".center(end_w)
            start_x = center_x - round(len(message) / 2)
            with colorize(stdscr, Color.WHITE):
                stdscr.addstr(
                    start_y,
                    start_x,
                    message,
                    curses.A_DIM | curses.A_BOLD | curses.A_STANDOUT,
                )

            first_entry_delay = splash_on + round(FRAMERATE * 0.20)
            if frame > first_entry_delay and frame % FRAMERATE == 20:
                typeon_leaderboard += 1
                if use_sound and typeon_leaderboard <= len(leaderboard):
                    Sound.INVADER.play()

            start_y += 1
            for idx, (name, score) in enumerate(leaderboard[:typeon_leaderboard]):

                start_y += 1
                name_str = f"{idx + 1:2d}: {name}"
                name_x = start_x + 2
                score_str = f"{score:4d} POINTS"
                score_x = start_x + end_w - 3 - len(score_str)
                with colorize(stdscr, Color.YELLOW if not idx else Color.WHITE):
                    # distinguish alternating lines
                    if idx % 2:
                        stdscr.addstr(start_y, name_x, name_str, curses.A_DIM)
                        stdscr.addstr(start_y, score_x, score_str, curses.A_DIM)
                    else:
                        stdscr.addstr(start_y, name_x, name_str)
                        stdscr.addstr(start_y, score_x, score_str)

            # increment the splash screen counter when fully drawn
            if typeon_leaderboard == len(leaderboard):
                typeon_leaderboard += 1

        stdscr.refresh()
        frame = (frame + 1) % (splash_off + round(FRAMERATE * 0.25))
        if frame == 0:
            splash_count += 1

    # return the keycode that exited
    return curr_key


def play(stdscr: Window, use_sound: bool, demo_mode: bool = False) -> int:
    """
    The play loop, which presents the actual game.
    """
    # pylint: disable=too-many-nested-blocks, too-many-statements, too-many-branches, too-many-locals

    # don't block waiting for user input
    stdscr.nodelay(True)

    # get the up to date extents
    height, width = stdscr.getmaxyx()

    # calculate the new center x point
    center_x = round(width / 2)

    # track the play state
    state = PlayState(demo_mode=demo_mode)

    # used to modulate the play loop timing
    last_time = None

    # track some progressively drawn on elemnts
    redraw_ranks_below = 4
    typeon_game_over = 1

    # spawn the player
    player = Player(
        state.player_start_x,
        height - state.player_start_y,
        speed=0,
        use_sound=use_sound,
    )

    # demo "AI" directions from like 1F74:
    # https://www.computerarcheology.com/Arcade/SpaceInvaders/Code.html
    demo_commands = cycle(
        [
            Control.RARR,
            Control.RARR,
            Control.NULL,
            Control.NULL,
            Control.RARR,
            Control.NULL,
            Control.LARR,
            Control.RARR,
            Control.NULL,
            Control.LARR,
            Control.RARR,
            Control.NULL,
        ]
    )

    # track the victims of the rare and powerful hadouken
    wave_kills: List[Set[Invader]] = []

    # tracks the current player movement command in demo mode
    demo_cmd = next(demo_commands)

    # in demo mode only we'll exit on SPACE press
    exit_inputs = set([Control.QUIT])
    if demo_mode:
        exit_inputs.add(Control.FIRE)

    # loop where curr_key is the last character pressed or -1 on no input
    while True:

        # get the key pressed
        curr_key = stdscr.getch()

        # handle user exit
        if curr_key in exit_inputs:
            break

        # modulate the time to keep rhe loop relatively constant
        last_time = govern(last_time)

        # handle terminal resize events
        if curr_key == curses.KEY_RESIZE:
            resize_arena(stdscr, reflow=True)
            height, width = stdscr.getmaxyx()
            center_x = round(width / 2)
            stdscr.clear()
            stdscr.refresh()

        # update the last 10
        if not state.egged and curr_key != Control.NULL:
            state.last10.append(curr_key)
            if curr_key == Control.LKEY:
                if Control.has_komando(state.last10):
                    state.credits += 1
                    state.egged = True
                    Sound.COIN.play()

        # if we're currently handling a player win, pause and level up
        if state.stage is Stage.WIN and state.bullet is None:
            curr_key = Control.NULL
            curses.delay_output(1250)
            player.x = state.player_start_x
            stdscr.clear()
            stdscr.refresh()
            state.screen += 1
            redraw_ranks_below = 4
            state.stage = Stage.REDRAW

        # if we're currently handling a player death, pause everything
        if state.stage is Stage.DEATH and state.bullet is None:
            curr_key = Control.NULL
            if state.lives:
                delay = 0
                while not player.reap():
                    curses.delay_output(1)
                    delay += 1
                stdscr.refresh()
                curses.delay_output(850 - delay)
                player.resurrect(state.player_start_x)
                state.stage = Stage.SPAWN
            else:
                state.stage = Stage.GAME_OVER

        # if we're currently at game over, start typing...
        if state.stage is Stage.GAME_OVER and state.bullet is None:
            if state.mystery:
                state.mystery.silence()
                state.mystery = None

            message = [G, A, M, E, ["  ", "  ", "  "], O, V, E, R]
            letter_count, letters_typed = typeon(
                stdscr, center_x, 4, message, typeon_game_over, delay=50
            )

            # if we've finished typing on
            if letter_count == letters_typed:
                curses.flushinp()
                stdscr.refresh()
                if state.has_topped():
                    curses.delay_output(1000)
                    return record(stdscr, state.score)
                if state.has_ranked():
                    curses.delay_output(1000)
                    return record(stdscr, state.score, is_top=False)
                if demo_mode:
                    curses.delay_output(1500)
                    return Control.NULL
                stdscr.timeout(1500)
                pressed = stdscr.getch()
                stdscr.nodelay(True)
                return pressed

            # otherwise keep typing on
            typeon_game_over += 1

        # erase the screen for redraw
        if state.stage is not Stage.GAME_OVER:
            stdscr.erase()

        # if we're starting a new screen, redraw everything
        if state.stage is Stage.REDRAW:

            # blank the screen to simulate a CRT redraw
            if redraw_ranks_below == 4:
                stdscr.clear()
                stdscr.refresh()
                curses.delay_output(18)
            elif redraw_ranks_below == 3:
                curses.delay_output(5)

            # place the barriers
            barriers = []
            barrier_x = round(BARRIER_WIDTH * 1.5)
            barrier_y = player.y - player.h - BARRIER_HEIGHT
            for idx in range(4):
                barriers.append(Barrier(barrier_x, barrier_y))
                barrier_x += BARRIER_WIDTH * 2

            # place the vaders
            if redraw_ranks_below == 4:
                Gestalt.populate(
                    state.invaders_start_x, state.invaders_start_y, use_sound=use_sound
                )
            elif redraw_ranks_below == 0:
                state.stage = Stage.SPAWN

        # don't move to running state during spawn delay
        if state.stage is Stage.SPAWN and state.can_spawn():
            state.stage = Stage.RUNNING

        # if we're running after player respawn, handle player actions
        if state.stage is Stage.RUNNING:
            # player firing might follow demo logic
            if demo_mode and state.frame % 2:
                # in the arcade game the demo player fires whenever possible
                # but we're going to be a wee bit more modern AI about it
                beam_path = round((2 * player.x + player.w) / 2)

                # for preference, pursue the mystery ship
                if state.mystery:
                    x_lim = state.mystery.x - 3
                    w_lim = state.mystery.x + state.mystery.w + 3

                # otherwise concentrate on the invader ranks
                else:
                    # search for the left rank
                    x_lim = 0
                    for col in Gestalt.hive_members:
                        for member in col:
                            if member is not None:
                                x_lim = max(1, member.x - 3)
                                break
                        if x_lim > 0:
                            break
                    x_lim = max(1, x_lim)

                    # search for the right rank
                    w_lim = width
                    for col in reversed(Gestalt.hive_members):
                        for member in col:
                            if member is not None:
                                w_lim = min(width - 2, member.x + member.w + 3)
                                break
                        if w_lim < width:
                            break
                    w_lim = min(width - 2, w_lim)

                # if we're under the basterds, and we can, fire!
                if x_lim <= beam_path <= w_lim:
                    under_barrier = any(
                        (b.x <= beam_path <= b.x + b.w) for b in barriers
                    )
                    if (
                        state.bullet is None
                        and state.can_fire()
                        and (not under_barrier or randint(0, 8) == 0)
                    ):
                        state.bullet = player.fire()
                        state.bullet.render(stdscr)
                        # rack up the next player movement
                        demo_cmd = next(demo_commands)
                # otherwise move towards those alien scum!
                elif round((x_lim + w_lim) / 2) < beam_path:
                    while not Control.is_left(demo_cmd):
                        demo_cmd = next(demo_commands)
                else:
                    while not Control.is_right(demo_cmd):
                        demo_cmd = next(demo_commands)

                # in the arcade game there's no obvious attempt to react
                # to the demo player hitting a wall, so here we're just going
                # to keep the player from lurking at the edges too long
                if Control.is_left(demo_cmd) or demo_cmd == Control.NULL:
                    if player.x - 1 <= 1:
                        demo_cmd = next(demo_commands)
                elif Control.is_right(demo_cmd) or demo_cmd == Control.NULL:
                    if player.x + player.w + 1 >= width - 2:
                        demo_cmd = next(demo_commands)

                # demo player moves according to the current demo_cmd value
                curr_key = demo_cmd

            # ... or player inputs
            elif curr_key == Control.FIRE and state.bullet is None:
                if state.can_fire():
                    hadouken = bool(state.credits)
                    state.bullet = player.fire(hadouken=hadouken)
                    if hadouken:
                        state.credits -= 1
                    state.bullet.render(stdscr)

            # update the player's position on directional input
            if Control.is_left(curr_key):
                player.x = max(1, player.x - 1)
            elif Control.is_right(curr_key):
                player.x = min(width - player.w - 2, player.x + 1)

            # move the player; this is really just to handle wall collision
            # player.move(stdscr, state.frame, width, height)

        # aliens move even if the player is spawning, but pause for death, etc
        if state.stage in Stage.SPAWN | Stage.RUNNING:
            # launch the mystery ship
            if (
                state.mystery_frame is not None
                and state.mystery_frame <= 0
                and not Gestalt.superboom()
            ):
                if Gestalt.remaining() <= 8:
                    state.mystery_frame = None
                else:
                    state.mystery = Mystery.spawn(
                        1, 3, width, state.bullet_count, use_sound=use_sound
                    )

            # move the mystery ship, if any has been launched
            if state.mystery and not state.mystery.is_dead():
                state.mystery.move(stdscr, state.frame, width, height)

            # move the invaders
            try:
                Gestalt.lockstep(
                    stdscr, state.frame, width, height, player.x, state.score
                )
            except SuccessfulInvasion:
                player.die()
                state.lives = 0
                state.stage = Stage.DEATH

        # the bullet will carry on its merry way even during death handling
        if state.bullet and not state.bullet.is_dead():
            state.bullet.move(stdscr, state.frame, width, height)

        # clear bombs from previous frames on redraw
        if state.stage is Stage.REDRAW:
            Gestalt.hive_dropped.clear()

        # during spawn the gestalt can't fire on or near the player
        if state.stage is Stage.SPAWN:
            Gestalt.hive_dropped = [
                b
                for b in Gestalt.hive_dropped
                if b.x >= player.x + round(2.5 * player.w)
            ]

        # bombs will fall except in death
        if state.stage not in Stage.DEATH | Stage.GAME_OVER:
            for bomb in Gestalt.hive_dropped:
                bomb.move(stdscr, state.frame, width, height)

        # all collisions end during death throes
        if state.stage not in Stage.DEATH | Stage.GAME_OVER:

            # handle successful player shots
            has_kill, hit_col, hit_row = (
                Gestalt.find_collision(state.bullet)
                if state.bullet
                else (None, None, None)
            )
            if has_kill and (state.bullet and state.bullet.is_hadouken()):
                # this check is primarily for typing, neither can be None here
                assert hit_col is not None
                assert hit_row is not None
                for look_col, look_row in [(-1, 0), (0, +1), (+1, 0), (0, -1)]:
                    magnitude = 1
                    while True:
                        check_col = hit_col + look_col * magnitude
                        check_row = hit_row + look_row * magnitude
                        wave_hit = None
                        try:
                            wave_hit = Gestalt.hive_members[check_col][check_row]
                        except IndexError:
                            break
                        if wave_hit is None:
                            break

                        while len(wave_kills) < magnitude:
                            wave_kills.append(set())
                        wave_kills[magnitude - 1].add(wave_hit)
                        magnitude += 1

            # score a successful shot
            if has_kill:
                if state.bullet and state.bullet.is_hadouken():
                    has_kill.color = Color.MAGENTA
                state.score += has_kill.points(state.bullet_count)
                state.last_kills.append(has_kill)
                state.bullet = None

            # score a previous hadouken's wave
            if wave_kills:
                for kill in Gestalt.process_wavelet(wave_kills.pop(0)):
                    state.score += kill.points(state.bullet_count)
                    state.last_kills.append(kill)

            # handle end of the gestalt
            if Gestalt.remaining() == 0:
                state.stage = Stage.WIN

            # handle bomb interactions with the player
            # note that bombs don't effect the player below the "invasion" row
            for bomb in Gestalt.hive_dropped:
                if bomb.dropped_from >= barrier_y + BARRIER_HEIGHT - 3:
                    continue
                if state.bullet and bomb.impacted_by(state.bullet):
                    bomb.die()
                    # player laser's damage on first hit, kill on second
                    if isinstance(bomb, SuperBomb):
                        state.bullet.die()
                    # player laser's kill but pass through other bombs
                    else:
                        state.bullet.impacted = False
                if not bomb.is_dead() and player.impacted_by(bomb):
                    player.die()
                    state.lives -= 1
                    state.stage = Stage.DEATH

            # handle the mystery ship's collisions
            if state.mystery:
                if state.mystery.reached_wall():
                    state.mystery = None
                elif state.bullet and state.mystery.impacted_by(state.bullet):
                    state.mystery.die()
                    state.bullet = None
                    state.score += state.mystery.points(state.bullet_count)

        # ... except for collisions with landscape
        struck = set()

        # update the barriers on screen
        for idx, barrier in enumerate(barriers):

            # if the bullet could hit a barrier, check for an impact
            if state.bullet and barrier.impacted_by(state.bullet):
                struck.add(idx)

            for column in Gestalt.hive_members:
                for member in reversed(column):
                    if member is None:
                        continue
                    if member.y + member.h < barrier.y:
                        continue
                    if barrier.impacted_by(member):
                        struck.add(idx)
                        break

            for bomb in Gestalt.hive_dropped:
                if bomb.y + bomb.h < barrier.y:
                    continue
                if barrier.impacted_by(bomb):
                    struck.add(idx)
                    break

        for idx in sorted(struck, reverse=True):
            barrier = barriers[idx]
            barrier.degrade()
            # the barrier may have been eliminated from play
            if barrier.is_devastated():
                barriers.pop(idx)

        # reap a dead bullet
        if state.bullet and (state.bullet.impacted or state.bullet.reap()):
            state.bullet = None

        # reap any killed invaders
        while state.last_kills and state.last_kills[0].reap():
            state.last_kills.pop(0)

        # reap any killed bombs
        bombs = Gestalt.hive_dropped
        while bombs and (bombs[-1].impacted or bombs[-1].reap()):
            Gestalt.hive_dropped.pop()

        # reap the mystery ship, if any
        if state.mystery and state.mystery.reap():
            state.mystery = None

        # render the mystery ship, if any
        if state.mystery:
            state.mystery.render(stdscr)

        # render the barriers
        for barrier in barriers:
            barrier.render(stdscr)

        # render any remaining bombs
        # if not rendered after the barriers the bomb's disappear
        # when travelling through destroyed sections
        for bomb in Gestalt.hive_dropped:
            if bomb.y > barrier_y - 1:
                bomb.color = Color.GREEN
            bomb.render(stdscr)

        # render the bullet, if any
        if state.bullet:
            state.bullet.render(stdscr)

        # render the gestalt, so they cover the barriers if wiping
        if state.stage is Stage.REDRAW:
            Gestalt.render_all(stdscr, ranks_below=redraw_ranks_below)
            if state.frame % 2:
                redraw_ranks_below -= 1
        else:
            Gestalt.render_all(stdscr)

        for kill in state.last_kills:
            kill.render(stdscr)

        # render the player, if not respawning
        if state.stage not in Stage.REDRAW | Stage.SPAWN:
            player.render(stdscr)

        # update the HUD
        draw_hud(stdscr, height, width, state)

        # refresh the screen
        stdscr.refresh()
        state.frame += 1

    # return the last key (which will be CTRL + Q here
    return curr_key


def mainloop(stdscr: Window, *, use_sound: bool = True) -> None:
    """
    The main game loop; prepares the screen and coordinates play stages.
    """
    # hide the cursor
    curses.curs_set(0)

    # start colors if available
    if curses.has_colors():
        curses.start_color()

        curses.init_pair(Color.RED, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(Color.YELLOW, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(Color.GREEN, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(Color.MAGENTA, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(Color.BLUE, curses.COLOR_BLUE, curses.COLOR_BLACK)
        curses.init_pair(Color.CYAN, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(Color.WHITE, curses.COLOR_WHITE, curses.COLOR_BLACK)

        if curses.can_change_color():
            # color values from schemcoloer:
            # https://www.schemecolor.com/classic-space-invaders.php
            # coral red
            curses.init_color(curses.COLOR_RED, cursize(248), cursize(59), cursize(58))
            # arylide yellow
            curses.init_color(
                curses.COLOR_YELLOW, cursize(235), cursize(223), cursize(100)
            )

            # pastel green
            curses.init_color(
                curses.COLOR_GREEN, cursize(98), cursize(222), cursize(109)
            )

            # orchid
            curses.init_color(
                curses.COLOR_MAGENTA, cursize(219), cursize(85), cursize(221)
            )

            # majorelle blue
            curses.init_color(curses.COLOR_BLUE, cursize(83), cursize(83), cursize(241))

            # turquoise
            curses.init_color(
                curses.COLOR_CYAN, cursize(66), cursize(233), cursize(244)
            )

    # center the play arena in the terminal
    resize_arena(stdscr)

    # start with a blank canvas
    stdscr.clear()
    stdscr.refresh()

    while attract(stdscr) != Control.QUIT:
        if play(stdscr, use_sound) == Control.QUIT:
            return


def main() -> None:
    """
    CLI to the Spaced Invaders game.
    """
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=dedent(
            """
        Play a game of Spaced Invaders.

        Your console and font must support unicode characters.
        If the following doesn't look like a UFO, then it is
        unlikely the game is going to work.

        {icon}

        Controls are pretty self-explanatory:

            Move Left    A KEY or LEFT ARROW
            Move Right   D KEY or RIGHT ARROW
            Fire         SPACE
            Quit         CTRL + Q
    """
        ).format(icon=indent(Mystery.ICON, " " * 8)),
    )

    parser.add_argument(
        "-q",
        "--quiet",
        dest="use_sound",
        action="store_false",
        help="disable game sounds",
    )

    parser.add_argument(
        "-V", "--version", action="version", version="%(prog)s " + __version__
    )

    opts = parser.parse_args()

    try:
        # start the game and clean up the screen on errors
        curses.wrapper(partial(mainloop, use_sound=opts.use_sound))
    except KeyboardInterrupt:
        # exit on error
        sys.exit(1)
    else:
        # exit on success
        sys.exit(0)


if __name__ == "__main__":
    main()
