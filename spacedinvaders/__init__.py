#! /usr/bin/env python3
# coding=utf-8
"""
A textual, terminal spin on an arcade classic.
"""
# stdlib imports
import argparse
import curses
import locale
import math
import os
import time
from collections import deque
from functools import partial
from random import randint
from textwrap import dedent, indent
from typing import BinaryIO, List, Tuple, Optional

# local imports
from .annotations import Window, Row, Col
from .constants import Color, Control, Direction, Stage
from .exceptions import SuccessfulInvasion
from .letters import A, C, D, E, G, I, M, N, O, P, R, S, V
from .units import *
from .utils import colorize, fit_within

locale.setlocale(locale.LC_ALL, "")

CODEC = locale.getpreferredencoding()
VERSION = "0.0.1"
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


def get_db():
    os.environ.get("SPACEDINVADERS_DATA_HOME")
    os.path.expandvars(
        os.path.expanduser(os.environ.get("XDG_DATA_HOME", "~/.local/share"))
    )


class PlayState:
    """
    Class to track the current game state.
    """

    def __init__(self):
        self._screen: int = 0
        self._frame: int = 0
        self._score: int = 0
        self._high: int = 0
        self._lives: int = 3
        self._stage: Stage = Stage.REDRAW
        self._respawn_delay: int = round(1.5 * FRAMERATE)
        self._credits: int = 0
        self._bullet: Optional[Bullet] = None
        self._bullet_count: int = 0
        self._bullet_delay: int = 0
        self._mystery: Optional[Mystery] = None
        self._mystery_frame: Optional[int] = 35 * FRAMERATE
        self._last_kills: List[Gestalt] = []
        self.last10 = deque(maxlen=10)
        self.egged = False

    @property
    def screen(self) -> int:
        """
        Current screen.
        """
        return self._screen

    @screen.setter
    def screen(self, val: int) -> int:
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
        self._mystery_frame: int = 25 * FRAMERATE
        self._last_kills = []

    @property
    def frame(self) -> int:
        """
        Current frame.
        """
        return self._frame

    @frame.setter
    def frame(self, val: int) -> int:
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
        if old_score <= 1500 <= self._score:
            state.lives += 1
        self.high = max(self.high, self._score)

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
    def credits(self, val: int) -> None:
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
    def bullet(self, fired: Optional[Bullet]) -> None:
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
    def mystery(self, ship: Optional[Mystery]) -> None:
        """
        Update the mystery ship on screen.
        """
        if ship is None:
            self._mystery_frame = FRAMERATE * 25
        else:
            self._mystery_frame = None
        self._mystery = ship

    @property
    def mystery_frame(self) -> int:
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
    def last_kills(self) -> List[Gestalt]:
        """
        Player's last kills, if any.
        """
        return self._last_kills


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
    lives = " ".join(Player.ICON for _ in range(state.lives - 1)).encode(CODEC)
    with colorize(stdscr, Color.YELLOW):
        stdscr.addstr(bar_y, 0, lives)
    label = "CREDITS: "
    creds = f"{state.credits:02d}"
    with colorize(stdscr, Color.WHITE):
        stdscr.addstr(bar_y, width - 1 - len(label + creds), label, curses.A_DIM)
        stdscr.addstr(bar_y, width - 1 - len(creds), creds, curses.A_BOLD)

    debug = f""
    if debug:
        with colorize(stdscr, Color.BLUE):
            stdscr.addstr(
                bar_y,
                width // 2 - len(debug) // 2,
                debug,
                curses.A_BOLD,
            )


Letter = List[str]


def typeon(
    stdscr: Window,
    center_x: int,
    start_y: int,
    message: List[Letter],
    up_to: int,
    *,
    delay: int = 10,
) -> int:
    """
    Type on the given big type message, up to the given character.
    Returns a tuple of the number of letters to display and the number of
    letters actually displayed.
    """
    length = len(message)
    x_pos = center_x - round(sum(len(c[0]) for c in message) / 2)
    for letter_count, letter in enumerate(message[:up_to], start=1):
        for line_idx, line in enumerate(letter):
            with colorize(stdscr, Color.RED if line_idx < 2 else Color.WHITE):
                stdscr.addstr(start_y + line_idx, x_pos, line)
        x_pos += len(line)
        if letter_count == up_to and letter_count != length:
            curses.delay_output(delay)
    return length, letter_count


def mainloop(
    stdscr: Window, *, use_sound: bool = True, dump_file: Optional[BinaryIO] = None
) -> None:
    """
    The main game loop; prepares the screen and coordinates play stages.
    """

    # prepare the screen
    initialize_screen(stdscr)

    # get the up to date extents
    height, width = stdscr.getmaxyx()

    # calculate the new center points
    center_y, center_x = round(height / 2), round(width / 2)

    # track the play state
    state = PlayState()

    last_time = None
    redraw_ranks_below = 4
    attract_frame = 0
    typeon_spaced = typeon_invaders = 1
    typeon_advance_table = 0
    typeon_game_over = 1

    # spawn the player
    player = Player(
        state.player_start_x,
        height - state.player_start_y,
        speed=0,
        use_sound=use_sound,
    )

    # loop where curr_key is the last character pressed or -1 on no input
    while (curr_key := stdscr.getch()) != Control.QUIT:

        # modulate the time to keep rhe loop relatively constant
        curr_time = time.time()
        delay = 1.0 / FRAMERATE - (curr_time - (last_time or curr_time))
        if delay > 0:
            time.sleep(delay)
        last_time = time.time()

        if False:

            stdscr.erase()
            start_y = center_y - 12

            if 20 <= attract_frame % FRAMERATE <= 55:
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
                invaders_count, invaders_typed = typeon(
                    stdscr, center_x, start_y + 3, invaders, typeon_invaders, delay=50
                )
                typeon_invaders += 1

            typeon_spaced += 1

            if attract_frame == 0:
                typeon_advance_table = 0

            if attract_frame > round(FRAMERATE * 0.65):
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

                if (
                    attract_frame > round(FRAMERATE * 0.85)
                    and attract_frame % FRAMERATE == 40
                ):
                    typeon_advance_table += 1

                start_y += 2
                pad_x = max([len(i[0][0]) for i in table])
                for critter_idx, (icon, color, points) in enumerate(
                    table[:typeon_advance_table]
                ):
                    for idx, line in enumerate(icon):
                        with colorize(stdscr, color):
                            stdscr.addstr(
                                start_y + idx, start_x + 2, line.center(pad_x)
                            )
                        if (critter_idx == 0 and idx == 1) or (
                            critter_idx and idx == 0
                        ):
                            with colorize(
                                stdscr, Color.WHITE if color != Color.YELLOW else color
                            ):
                                stdscr.addstr(
                                    start_y + idx,
                                    start_x + end_w - len(points) - 2,
                                    points,
                                )
                    start_y += len(icon)
                    if 0 < critter_idx:
                        start_y += 1

            stdscr.refresh()
            attract_frame = (attract_frame + 1) % (FRAMERATE * 30)
            continue

        # handle terminal resize events
        if curr_key == curses.KEY_RESIZE:
            resize_arena(stdscr, reflow=True)
            height, width = stdscr.getmaxyx()
            center_y, center_x = round(height / 2), round(width / 2)
            stdscr.clear()
            stdscr.refresh()

        # update the last 10
        if not state.egged and curr_key != Control.NULL:
            state.last10.append(curr_key)
            if curr_key == Control.LKEY:
                if Control.has_komando(state.last10):
                    state.credits += 10
                    state.egged = True

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

            if letter_count == letters_typed:
                curses.flushinp()
                stdscr.refresh()
                curses.delay_output(1000)
                stdscr.timeout(-1)
                while stdscr.getch():
                    raise SystemExit("Game Over")
            else:
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

        # if we're runing after player respawn, handle player actions
        if state.stage is Stage.RUNNING:
            if curr_key == Control.FIRE and state.bullet is None:
                if state.can_fire():
                    state.bullet = player.fire()
                    state.bullet.render(stdscr)
            elif Control.is_left(curr_key):
                player.x = max(1, player.x - 1)
            elif Control.is_right(curr_key):
                player.x = min(width - player.w - 1, player.x + 1)

            # move the player
            player.move(stdscr, state.frame, width, height)

        # aliens move even if the player is spawning, but pause for death, etc
        if state.stage in Stage.SPAWN | Stage.RUNNING:
            # launch the mystery ship
            if state.mystery_frame <= 0 and not Gestalt.superboom():
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
            has_kill = Gestalt.find_collision(state.bullet) if state.bullet else None
            if has_kill:
                state.score += has_kill.points(state.bullet_count)
                state.last_kills.append(has_kill)
                state.bullet = None

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

    # hidden option to dump out play state to file
    # necessary for recording a new demo
    parser.add_argument(
        "--dump",
        type=argparse.FileType("wb"),
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "-q",
        "--quiet",
        dest="use_sound",
        action="store_false",
        help="disable game sounds",
    )
    parser.add_argument(
        "-V", "--version", action="version", version="%(prog)s " + VERSION
    )

    opts = parser.parse_args()

    # start the game and clean up the screen on errors
    curses.wrapper(partial(mainloop, use_sound=opts.use_sound, dump_file=opts.dump))


if __name__ == "__main__":
    main()
