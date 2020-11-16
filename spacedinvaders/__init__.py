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
from collections import deque
from random import randint
from typing import List, Tuple, Optional

# local imports
from .constants import Color, Control, Direction
from .units import *
from .utils import colorize, fit_within
from .sounds import Sound
from .annotations import Window, Row, Col

locale.setlocale(locale.LC_ALL, "")

CODEC = locale.getpreferredencoding()
FRAMERATE = 60

# Constnats that represent the screen dimensions
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
        self._screen: int = 0
        self._frame: int = 0
        self._score: int = 0
        self._high: int = 0
        self._lives: int = 3
        self._handling_death: bool = False
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
            self.lives += 1
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
    def handling_death(self) -> bool:
        """
        Are we currently handling a death?
        """
        return self._handling_death

    @handling_death.setter
    def handling_death(self, new: bool):
        """
        Reset the death handling flag.
        """
        if not new:
            self._respawn_delay += round(1.5 * FRAMERATE)
        self._handling_death = False

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
        return [8, 10, 14, 18, 18, 18, 20, 20, 20][self.screen % 10]

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

    with colorize(stdscr, Color.BLUE):
        stdscr.addstr(
            bar_y,
            width // 2,
            str(state.mystery_frame),
            curses.A_BOLD,
        )


def game_loop(stdscr: Window) -> None:

    # prepare the screen
    initialize_screen(stdscr)

    # get the up to date extents
    height, width = stdscr.getmaxyx()

    # calculate the new center points
    center_y, center_x = round(height / 2), round(width / 2)

    # track the play state
    state = PlayState()

    last_time = None
    last_screen = None

    # loop where curr_key is the last character pressed or -1 on no input
    while (curr_key := stdscr.getch()) != Control.QUIT:

        # modulate the time to keep rhe loop relatively constant
        curr_time = time.time()
        delay = 1.0 / FRAMERATE - (curr_time - (last_time or curr_time))
        if delay > 0:
            time.sleep(delay)
        last_time = time.time()

        # update the last 10
        if not state.egged and curr_key != Control.NULL:
            state.last10.append(curr_key)
            if curr_key == Control.LKEY and Control.has_komando(state.last10):
                state.credits += 10
                state.egged = True

        # handle terminal resize events
        if curr_key == curses.KEY_RESIZE:
            resize_arena(stdscr, reflow=True)
            height, width = stdscr.getmaxyx()
            center_y, center_x = round(height / 2), round(width / 2)
            stdscr.clear()
            stdscr.refresh()

        # erase the screen for redraw
        stdscr.erase()

        # starting a new screen
        if last_screen is None or state.screen != last_screen:

            # spawn the player
            player = Player(
                state.player_start_x, height - state.player_start_y, speed=0
            )
            # place the barriers
            barriers = []
            barrier_x = round(BARRIER_WIDTH * 1.5)
            barrier_y = height - BARRIER_HEIGHT - state.player_start_y - 1
            for idx in range(4):
                barriers.append(Barrier(barrier_x, barrier_y))
                barrier_x += BARRIER_WIDTH * 2

            # place the vaders
            Gestalt.populate(state.invaders_start_x, state.invaders_start_y)
            last_screen = state.screen

        # handle player actions; delay for respawn
        player.speed = 0
        if state.can_spawn() and not state.handling_death:
            if curr_key == Control.FIRE and state.bullet is None:
                if state.can_fire():
                    state.bullet = player.fire()
                    state.bullet.render(stdscr)
            elif Control.is_left(curr_key):
                player.x = max(1, player.x - 1)
            elif Control.is_right(curr_key):
                player.x = min(width - player.w - 1, player.x + 1)

        # pause invader and player movements during death
        if not state.handling_death:
            # launch the mystery ship
            if state.mystery_frame <= 0 and not Gestalt.superboom():
                if Gestalt.remaining() <= 8:
                    state.mystery_frame = None
                else:
                    state.mystery = Mystery.spawn(1, 3, width, state.bullet_count)

            # move the player
            player.move(stdscr, state.frame, width, height)

            # move the invaders
            Gestalt.lockstep(stdscr, state.frame, width, height, player.x, state.score)
            # move the mystery ship, if any
            if state.mystery and not state.mystery.is_dead():
                state.mystery.move(stdscr, state.frame, width, height)

        # projectiles carry on their merry way during death handling

        # move the bullet, if any
        if state.bullet and not state.bullet.is_dead():
            state.bullet.move(stdscr, state.frame, width, height)

        # move any bombs dropped by the gestalt
        for bomb in Gestalt.hive_dropped:
            bomb.move(stdscr, state.frame, width, height)

        # however collisions end during death throes

        if not state.handling_death:

            # handle bomb interactions with the player
            # note that bombs don't effect the player below the "invasion" row
            for bomb in Gestalt.hive_dropped:
                # don't effect the player during respawn
                if state.handling_death or not state.can_spawn():
                    break
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

            # handle succesful player shots
            has_kill = Gestalt.find_collision(state.bullet) if state.bullet else None
            if has_kill:
                state.score += has_kill.points(state.bullet_count)
                state.last_kills.append(has_kill)
                state.bullet = None

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

            # render the barrier if it's had no collisions this round
            if not barrier.struck:
                barrier.render(stdscr)

        for idx in sorted(struck, reverse=True):
            barrier = barriers[idx]
            barrier.degrade()
            # the barrier may have been eliminated from play
            if barrier.is_devastated():
                barriers.pop(idx)
            else:
                # render the barrier
                barrier.render(stdscr)

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

        # reap the player and resurrect
        if player.is_dead() and player.reap():
            player.resurrect(state.player_start_x)

        # render the mystery ship, if any
        if state.mystery:
            state.mystery.render(stdscr)

        # render any remaining bombs
        for bomb in Gestalt.hive_dropped:
            if bomb.y > barrier_y - 1:
                bomb.color = Color.GREEN
            bomb.render(stdscr)

        # render the bullet, if any
        if state.bullet:
            state.bullet.render(stdscr)

        # render the gestalt, so they cover the barriers if wiping
        Gestalt.render_all(stdscr)

        for kill in state.last_kills:
            kill.render(stdscr)

        # render the player, if not respawning
        if player.is_dead() or state.can_spawn():
            player.render(stdscr)

        # update the HUD
        draw_hud(stdscr, height, width, state)

        # refresh the screen
        stdscr.refresh()

        # pause everything on death
        if state.handling_death:
            curses.delay_output(850)
            state.handling_death = False
        state.frame += 1


def main() -> None:
    curses.wrapper(game_loop)


if __name__ == "__main__":
    main()
