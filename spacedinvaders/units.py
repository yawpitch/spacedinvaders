#! /usr/bin/env python3
# coding=utf-8
"""
A textual, terminal spin on an arcade classic.
"""
from __future__ import annotations

# stdlib imports
import curses
import locale
import time
from random import choice
from typing import Any, ByteString, Dict, List, Optional, Set, Tuple, Type, TYPE_CHECKING

# local imports
from spacedinvaders.constants import Color, Direction
from spacedinvaders.exceptions import SuccessfulInvasion
from spacedinvaders.utils import regularize, colorize
from spacedinvaders.sounds import Sound

CODEC = locale.getpreferredencoding()

# aliases for mypy only
if TYPE_CHECKING:
    # in 3.8+ we can import the window directly
    try:
        from curses import window as Window
    except ImportError:
        Window = Any
else:
    Window = Any

Icon = str

# pylint: disable=too-many-lines, too-many-ancestors


def make_icon(icon: Icon) -> Icon:
    """
    Convert an icon to a regularized form.
    """
    return regularize(icon)


class Renderable:
    """
    Superclass for all Renderable units.
    """

    # pylint: disable=invalid-name, too-many-instance-attributes
    # the color this unit will be drawn in (if colors are available)
    COLOR: Color
    # the icon that will be drawn for this unit
    ICON: Icon

    def __init__(self, x: int, y: int, *args, **kwargs):
        # pylint: disable=unused-argument
        self._x: int = x
        self._y: int = y
        split = self.ICON.splitlines()
        self._w: int = len(split[0])
        self._h: int = len(split)
        self._icon: Icon = self.ICON
        self._color: Color = self.COLOR
        # this is where we'll cache the converted bytes
        self._lines: List[ByteString] = []
        self._dirty: bool = True

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(x={self.x}, y={self.y})"

    @property
    def x(self) -> int:
        """
        The left-most extent of this unit.
        """
        return self._x

    @x.setter
    def x(self, val: int):
        """
        Updates the x position and dirties this unit.
        """
        self._dirty = True
        self._x = val

    @property
    def y(self) -> int:
        """
        The top-most extent of this unit.
        """
        return self._y

    @y.setter
    def y(self, val: int):
        """
        Updates the y position and dirties this unit.
        """
        self._dirty = True
        self._y = val

    @property
    def w(self) -> int:
        """
        The right-most extent of this unit.
        """
        return self._w

    @property
    def h(self) -> int:
        """
        The bottom-most extent of this unit.
        """
        return self._h

    @property
    def icon(self) -> Icon:
        """
        The icon that will be drawn for this unit.
        """
        return self._icon

    @icon.setter
    def icon(self, new: Icon):
        """
        Updates the icon and dirties this unit.
        """
        split = new.splitlines()
        new_w = len(split[0])
        new_h = len(split)
        if new_w != self._w:
            self.x += self._w - new_w
        if new_h != self._h:
            self.y += self._h - new_h
        self._w = new_w
        self._h = new_h
        self._dirty = True
        self._lines.clear()
        self._icon = new

    @property
    def color(self) -> Color:
        """
        The color of this unit.
        """
        return self._color

    @color.setter
    def color(self, new: Color):
        """
        Updates the color and dirties this unit.
        """
        self._dirty = True
        self._lines.clear()
        self._color = new

    @property
    def dirty(self) -> bool:
        """
        True if this unit requires a redraw.
        """
        return self._dirty

    def render(self, stdscr: Window) -> None:
        """
        Render the unit to screen.
        """
        # Cache the encoded lines, no sense redoing the work
        if not self._lines:
            lines = self.icon.splitlines()
            self._lines = [l.encode(CODEC) for l in lines]

        with colorize(stdscr, self.color):
            for offset_y, line in enumerate(self._lines):
                try:
                    stdscr.addstr(self.y + offset_y, self.x, line)
                except curses.error as err:
                    raise ValueError(f"y={self.y}, x={self.x}: {line}") from err

        # Unit is no longer dirty
        self._dirty = False


class Audible(Renderable):
    """
    Mixin that allows units to have sounds.
    """

    def __init__(self, *args, use_sound: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._use_sound = use_sound

    @property
    def use_sound(self) -> bool:
        """
        Check if the unit's sounds should play.
        """
        return self._use_sound


class Reskinable(Renderable):
    """
    Mixin that allows a unit to be reskinned on move.
    """

    # pylint: disable=no-member

    ALT: Icon

    def flip(self) -> None:
        """
        Flips the unit's icon.
        """
        if isinstance(self, Killable) and self.is_dead():
            return
        if self.icon is self.ICON:
            self.icon = self.ALT
        else:
            self.icon = self.ICON


class Killable(Renderable):
    """
    Mixin to allow a Renderable to be killed.
    """

    # time to wait before reaping
    REAP_DELAY = 0.4
    # icon to present on death
    DEATH: Icon

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._time_of_death: Optional[float] = None

    @property
    def time_of_death(self) -> Optional[float]:
        """
        Time since the unit died.
        """
        return self._time_of_death

    @time_of_death.setter
    def time_of_death(self, time_of_death: float):
        """
        Updates the time of death and dirties this unit.
        """
        self._dirty = True
        self._time_of_death = time_of_death

    def is_dead(self) -> bool:
        """
        Test if this unit is currently dead.
        """
        return bool(self._time_of_death)

    def die(self) -> None:
        """
        Kill this unit.
        """
        self.icon = self.DEATH
        self.time_of_death = time.time()

    def reap(self) -> bool:
        """
        Check if the unit should be reaped and removed from the render queue.
        """
        if self.is_dead() and self.time_of_death is not None:
            return time.time() - self.time_of_death > self.REAP_DELAY
        return False


class Moveable(Renderable):
    """
    Mixin to allow a Renderable to be moved.
    """

    # pylint: disable=no-member

    WALL_BUFFER = 5

    def __init__(self, *args, speed: int = 1, **kwargs):
        super().__init__(*args, **kwargs)
        self._direction = Direction.EAST
        self._speed = speed

    @property
    def speed(self) -> int:
        """
        The speed at which the unit is moving.
        """
        return self._speed

    @speed.setter
    def speed(self, val: int):
        """
        Updates the speed the unit is moving.
        """
        self._speed = val

    def on_every(self, frame: int) -> bool:
        """
        Used to limit on what frames movement will occur.
        Subclasses can use this to slow movement, or perform periodic actions.
        """
        # pylint: disable=unused-argument, no-self-use
        return True

    @property
    def direction(self) -> Direction:
        """
        The direction in which the unit is moving.
        """
        return self._direction

    @direction.setter
    def direction(self, val: Direction):
        """
        Updates the direction in which the unit is moving.
        """
        self._direction = val

    def move(self, stdscr: Window, frame: int, width: int, height: int) -> None:
        """
        Moves the unit in the direction it's facing.
        Calls Moveable.wall(new_position, limit) near wall collisions.
        """
        # pylint: disable=unused-argument, too-many-branches

        # only move on every scheduled frame
        if not self.on_every(frame):
            return

        if self.direction is Direction.NORTH:
            new_y = self.y - self.speed
            if new_y > self.WALL_BUFFER:
                self.y = new_y
            else:
                self.y = self.wall(new_y, 0)

        elif self.direction is Direction.WEST:
            new_x = self.x - self.speed
            if new_x > self.WALL_BUFFER:
                self.x = new_x
            else:
                self.x = self.wall(new_x, 0)

        elif self.direction is Direction.SOUTH:
            new_y = self.y + self.speed
            if new_y + self.h < height - self.WALL_BUFFER:
                self.y = new_y
            else:
                self.y = self.wall(new_y, height)

        else:
            new_x = self.x + self.speed
            if new_x + self.w < width - self.WALL_BUFFER:
                self.x = new_x
            else:
                self.x = self.wall(new_x, width)

        if isinstance(self, Reskinable):
            self.flip()

    def wall(self, new_position: int, limit: int) -> int:
        """
        Handle wall impact in the direction just moved.
        """
        raise NotImplementedError("Subclass must implement")


class Gestalt(Moveable, Audible):
    """
    Moveables that act as one.
    """

    SIGHT = None
    WALL_BUFFER: int = 1
    TURN_BUFFER: int = 2
    COLUMNS: int = 11
    ROWS: int = 5
    hive_members: List[List[Optional[Invader]]] = []
    hive_moves: int = 0
    hive_direction: Direction = Direction.EAST
    hive_aboutface: Direction = Direction.WEST
    hive_speed: int = 1
    hive_turned: bool = False
    hive_dropped: List[Bomb] = []
    hive_use_sound: bool = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        row, col = divmod(
            sum(sum(1 for i in l if i) for l in Gestalt.hive_members), Gestalt.COLUMNS
        )
        assert (row, col) != (Gestalt.ROWS, 1)
        Gestalt.hive_members[col][row] = self

    @classmethod
    def populate(
        cls, x: int, y: int, *, x_sep: int = 2, y_sep: int = 1, use_sound: bool = True
    ) -> None:
        """
        Populate the Gestalt.
        """
        # pylint: disable=invalid-name

        # optionally turn off hive audio
        Gestalt.hive_use_sound = use_sound

        # clear any existing hive
        for col in Gestalt.hive_members:
            col.clear()
        Gestalt.hive_members = [[None] * cls.ROWS for _ in range(cls.COLUMNS)]

        # place the invaders
        y_pos = y
        for row in range(Gestalt.ROWS):
            x_pos = x
            species = Squid if row < 1 else Crab if row < 3 else Octopus
            for _ in range(cls.COLUMNS):
                vader = species(x_pos, y_pos, speed=1, use_sound=use_sound)
                x_pos += vader.w + x_sep
            y_pos += vader.h + y_sep

    @property
    def speed(self) -> int:
        """
        The speed at which the unit is moving.
        """
        return Gestalt.hive_speed

    @speed.setter
    def speed(self, val: int):
        """
        Updates the speed the unit is moving.
        """
        Gestalt.hive_speed = val

    @classmethod
    def on_every(cls, frame: int) -> bool:
        """
        Speed up as invaders get killed.
        """
        return frame % max(1, cls.remaining()) == 0

    @property
    def direction(self) -> Direction:
        """
        The direction in which the unit is moving.
        """
        return Gestalt.hive_direction

    @direction.setter
    def direction(self, new: Direction):
        """
        Updates the direction in which the unit is moving.
        """
        assert new is not Direction.NORTH
        Gestalt.hive_turned = False
        if new is Direction.WEST:
            Gestalt.hive_aboutface = Direction.EAST
        elif new is Direction.EAST:
            Gestalt.hive_aboutface = Direction.WEST
        else:
            Gestalt.hive_turned = True
        Gestalt.hive_direction = new

    @classmethod
    def remaining(cls) -> int:
        """
        The number of remaining invaders.
        """
        return sum(sum(1 for v in c if v) for c in cls.hive_members)

    @classmethod
    def lockstep(
        cls,
        stdscr: Window,
        frame: int,
        width: int,
        height: int,
        player_x: int,
        player_score: int,
    ) -> None:
        """
        Move as one. Fight as one. Die as one?
        """
        # pylint: disable=too-many-locals, too-many-branches, too-many-statements, too-many-arguments

        assert cls.hive_direction is not Direction.NORTH

        flip = cls.on_every(frame)
        if not flip:
            return

        members = Gestalt.hive_members
        have_invaded = False

        no_turn = True
        # by default search west to east
        columns = list(range(len(members)))
        # reverse the search if the gestalt is moving east
        if cls.hive_direction is Direction.EAST:
            columns = sorted(columns, reverse=True)

        count = cls.remaining()

        bomb = sight = None
        # narrow the search to the columns with a surviving member
        can_sight = [c for c in columns if any(members[c])]

        # load a weapon, if we can fire
        if cls.hive_moves > 3 and can_sight and cls.can_drop(player_score):
            # determine what weapon to drop
            arsenal: List[Type[Bomb]] = [Seeker]
            if not any(isinstance(b, SuperBomb) for b in cls.hive_dropped):
                arsenal.append(SuperBomb)
            if count > 8:
                arsenal.append(Bomb)
            bomb = choice(arsenal)
            # if the bomb is a Seeker we need to drop it from the column
            # nearest the player's current x position
            if bomb is Seeker:

                def find_goose(idx):
                    while members[idx] and members[idx][-1] is None:
                        members[idx].pop()
                    member = members[idx][-1]
                    return abs(player_x - ((2 * member.x + member.w) // 2))

                sight = min(can_sight, key=find_goose)
            else:
                sight = choice(can_sight)

        for col in columns:
            column = members[col]
            if not column:
                continue
            # always search up from the player's position
            for idx, row in enumerate(reversed(range(len(column)))):
                member = column[row]
                if member is None:
                    continue
                if no_turn:
                    if cls.hive_direction is Direction.WEST:
                        if member.x <= cls.TURN_BUFFER:
                            member.direction = Direction.SOUTH
                    elif cls.hive_direction is Direction.EAST:
                        if member.x + member.w >= width - cls.TURN_BUFFER:
                            member.direction = Direction.SOUTH
                    else:
                        member.direction = cls.hive_aboutface
                    no_turn = False

                if count == 1 and member.direction is Direction.EAST:
                    if member.x + member.w + member.speed > width - cls.TURN_BUFFER:
                        member.x += 1
                member.move(stdscr, frame, width, height)

                if member.y + member.h >= height - 3:
                    have_invaded = True

                # drop the bomb from the bottom-most member
                if bomb and col == sight and idx == 0:
                    away = bomb(
                        (member.x + member.x + member.w) // 2,
                        member.y + 2,
                        speed=2 if count == 1 else 1,
                    )
                    away.render(stdscr)
                    cls.hive_dropped.insert(0, away)

        if have_invaded:
            raise SuccessfulInvasion(member)

        if cls.hive_use_sound:
            Sound.INVADER.play()
        cls.hive_moves += 1

    def wall(self, new_position: int, limit: int) -> int:
        """
        Handle wall impact. When we turn one, we turn all (we
        sayeth with more than a little irony).
        """
        raise RuntimeError(f"{self} -> {new_position} @ {limit}")

    @classmethod
    def render_all(cls, stdscr: Window, ranks_below: int = 0) -> None:
        """
        Render the hive, if only the ranks below a given index.
        """
        for col in cls.hive_members:
            while col and col[-1] is None:
                col.pop()
            for idx, member in enumerate(col):
                if idx >= ranks_below and member:
                    member.render(stdscr)

    @classmethod
    def find_collision(
        cls, bullet: Bullet
    ) -> Tuple[Optional[Invader], Optional[int], Optional[int]]:
        """
        Find any invader struck by the player's bullet.
        Returns either (Invader, column, row) on a hit or (None, None, None).
        """
        for col, column in enumerate(cls.hive_members):
            for row in reversed(range(len(column))):
                candidate = column[row]
                if candidate is None:
                    continue
                if candidate.impacted_by(bullet):
                    if cls.hive_use_sound:
                        Sound.KILLSHOT.play()
                    candidate.color = Color.RED
                    candidate.die()
                    column[row] = None
                    return candidate, col, row
        return None, None, None

    @classmethod
    def process_wavelet(cls, wave_hit: Set[Invader]) -> List[Invader]:
        """
        Process the wave hit invaders, returning those actually killed.
        """
        wave_killed = []
        for column in cls.hive_members:
            for row in reversed(range(len(column))):
                candidate = column[row]
                if candidate is None:
                    continue
                if candidate in wave_hit:
                    if cls.hive_use_sound:
                        Sound.KILLSHOT.play()
                    candidate.color = Color.MAGENTA
                    candidate.die()
                    column[row] = None
                    wave_killed.append(candidate)
        return wave_killed

    @classmethod
    def can_drop(cls, score: int) -> bool:
        """
        Check if a Bomb can be dropped.
        """
        if not cls.hive_dropped:
            return True
        # all these rates from the amazing work at:
        # https://www.computerarcheology.com/Arcade/SpaceInvaders/
        # though we have to massage them a bit for reasonable
        # play on curses
        if score < 200:
            delay = 48
        elif score < 1000:
            delay = 16
        elif score < 2000:
            delay = 11
        elif score < 3000:
            delay = 8
        else:
            delay = 7
        return cls.hive_dropped[0].in_flight % 60 > delay * 10

    @classmethod
    def superboom(cls) -> bool:
        """
        Check if a SuperBomb is in flight.
        """
        return any(isinstance(b, SuperBomb) for b in cls.hive_dropped)


class Collidable(Renderable):
    """
    A Renderable that can engage in collisions.
    """

    # pylint: disable=no-member, invalid-name

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._struck: List[Collidable] = []
        self._impacted = False

    @property
    def struck(self) -> bool:
        """
        Has the unit suffered a collision.
        """
        return bool(self._struck)

    @property
    def impacted(self) -> bool:
        """
        Has the unit impacted another in this round?
        """
        return self._impacted

    @impacted.setter
    def impacted(self, new_state: bool):
        """
        Update the impacted value for this unit.
        """
        self._impacted = new_state

    @property
    def cx(self):
        """
        The x coordinate of this unit's collision box.
        """
        # pylint: disable=unreachable

        return self.x
        if isinstance(self, Moveable):
            if self.direction is Direction.EAST:
                return self.x + self.speed
            if self.direction is Direction.WEST:
                return self.x - self.speed
        return self.x

    @property
    def cy(self):
        """
        The y coordinate of this unit's collision box.
        """
        # pylint: disable=unreachable

        return self.y
        if isinstance(self, Moveable):
            if self.direction is Direction.NORTH:
                return self.y - self.speed
            if self.direction is Direction.SOUTH:
                return self.y + self.speed
        return self.y

    def collides_with(self, other: Collidable) -> bool:
        """
        Tests if this unit and some other will collide on next move.
        """
        if isinstance(self, Killable) and self.is_dead():
            return False
        if isinstance(other, Killable) and other.is_dead():
            return False
        return (
            (other.cx + other.w > self.cx)
            and (other.cx < self.cx + self.w)
            and (other.cy + other.h >= self.cy)
            and (other.cy <= self.cy + self.h)
        )

    def impacted_by(self, impactor: Collidable) -> bool:
        """
        Tests if the impactor has struck this unit.
        """
        if self.collides_with(impactor):
            self._struck.append(impactor)
            impactor.impacted = True
            return True
        return False


class Destructible(Collidable):
    """
    Mixin for Renderable units that can be successively eroded by collisions.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._state: List[List[str]] = [list(r) for r in self.icon.splitlines()]
        self._devastated: Dict[str, Set[int]] = {"rows": set(), "cols": set()}

    def is_devastated(self) -> bool:
        """
        Check if the unit has been completely devastated.
        """
        return (
            len(self._devastated["rows"]) == self.h
            and len(self._devastated["cols"]) == self.w
        )

    def degrade(self) -> None:
        """
        Process any damage done by strikes.
        """
        # pylint: disable=too-many-branches, too-many-statements

        damaged = False
        while self._struck:
            other = self._struck.pop(0)

            # special case bullets, which fly fast but do not penetrate
            if isinstance(other, Bullet):
                assert other.direction is Direction.NORTH
                hit_x = other.cx - self.cx
                # don't bother processing devastated columns
                if hit_x in self._devastated["cols"]:
                    other.impacted = False
                    continue
                # process the first brick hit from the bottom
                for hit_y in range(self.h - 1, -1, -1):
                    if self._state[hit_y][hit_x] != " ":
                        self._state[hit_y][hit_x] = " "
                        damaged = True
                        other.die()
                        # we may have just devastated the column
                        if hit_y == 0:
                            self._devastated["cols"].add(hit_x)
                        break
                # no bricks hit, the column has been devastated
                else:
                    other.impacted = False
                    self._devastated["cols"].add(hit_x)

            # special case bombs, which fall slow or fast and may penetrate
            elif isinstance(other, Bomb):
                assert other.direction is Direction.SOUTH
                penetration = 1 if isinstance(other, SuperBomb) else 0
                hit_x = other.cx - self.cx
                # don't bother processing devastated columns
                if hit_x in self._devastated["cols"]:
                    other.impacted = False
                    continue
                # process the first brick hit from the bottom
                for hit_y in range(self.h):
                    if self._state[hit_y][hit_x] != " ":
                        self._state[hit_y][hit_x] = " "
                        damaged = True
                        # we may have just devastated the column
                        if hit_y == self.h:
                            self._devastated["cols"].add(hit_x)
                            other.die()
                            break
                        # we may have to consider penetration
                        if penetration:
                            penetration -= 1
                            continue
                        # otherwise we're done here
                        other.die()
                        break

                # no bricks hit, the column has been devastated
                else:
                    other.impacted = False
                    self._devastated["cols"].add(hit_x)

            # the only other thing to worry about is invaders wiping the unit
            else:

                rows_damaged, cols_damaged = set(), set()
                for row in range(len(self._state)):
                    # ignore non-overlapping rows
                    if not other.y < row + self.y < other.y + other.h:
                        continue
                    for col in range(len(self._state[row])):
                        # ignore non-overlapping rows
                        # had to massage the constants to keep the effect
                        # somewhat pleasing
                        if not other.x - 2 < col + self.x < other.x + other.w + 2:
                            continue
                        # clear out the overlap
                        if self._state[row][col] != " ":
                            self._state[row][col] = " "
                            rows_damaged.add(row)
                            cols_damaged.add(col)
                            damaged = True

                # check for devastation
                for row_idx in rows_damaged:
                    for col_idx in range(len(self._state[row_idx])):
                        if self._state[row_idx][col_idx] != " ":
                            break
                    else:
                        self._devastated["rows"].add(row_idx)

                for col_idx in cols_damaged:
                    for row_idx in range(len(self._state)):
                        if self._state[row_idx][col_idx] != " ":
                            break
                    else:
                        self._devastated["cols"].add(row_idx)

        if damaged:
            self.icon = "\n".join("".join(i) for i in self._state)


class Bullet(Moveable, Collidable, Killable, Renderable):
    """
    A player's shot at glory.
    """

    COLOR: Color = Color.CYAN
    ICON: Icon = make_icon(
        """
         ❚
        """
    )
    DEATH: Icon = make_icon(
        """
         ✺
        """
    )

    def __init__(self, *args, hadouken: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self._direction = Direction.NORTH
        self._hadouken = hadouken

    def wall(self, new_position: int, limit: int) -> int:
        """
        Stop on wall impact. Bullet only travels north.
        """
        assert self.direction is Direction.NORTH
        if new_position < limit + 2:
            self.die()
            return max([new_position, limit + 2])
        return new_position

    def is_hadouken(self) -> bool:
        """
        Kore wa hadō kendesu ka?
        """
        return self._hadouken

    def die(self):
        """
        Kill this bullet, allowing the user to fire again.
        """
        self.color = Color.RED
        self.speed = 0
        super().die()


class Player(Moveable, Collidable, Killable, Audible, Renderable):
    """
    The player's unit.
    """

    COLOR: Color = Color.YELLOW
    ICON: Icon = make_icon(
        """
        ▄█▄
        """
    )
    DEATH: Icon = make_icon(
        """
        ▘▙▁
        """
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def wall(self, new_position: int, limit: int) -> int:
        """
        Stop on wall impact. Player only travels east/west.
        """
        assert self.direction is not Direction.NORTH
        assert self.direction is not Direction.SOUTH

        if self.direction is Direction.WEST:
            return max(new_position, limit + 1)
        return min(new_position, limit - self.w - 2)

    def fire(self, hadouken: bool = False) -> Bullet:
        """
        Fire a Bullet upwards, if enough time has elapsed
        since the last shot.
        """
        if self.use_sound:
            if hadouken:
                Sound.HADOUKEN.play()
            else:
                Sound.SHOOT.play()
        return Bullet(
            (self.x + (self.x + self.w)) // 2, self.y - 1, speed=3, hadouken=hadouken
        )

    def die(self) -> None:
        """
        Die a death!
        """
        self.speed = 0
        if self.use_sound:
            Sound.EXPLOSION.play()
        super().die()

    def resurrect(self, x: int):
        """
        Resurrect the player.
        """
        # pylint: disable=invalid-name

        self.icon = self.ICON
        self.speed = 0
        self.x = x
        self.time_of_death = None


class Collectible:
    """
    Mixin to make a unit have a points value.
    """

    # pylint: disable=too-few-public-methods

    POINTS: Optional[int] = None

    def points(self, shot_count: int) -> int:
        """
        Return the points this Collectible is worth at this shot count.
        """
        # pylint: disable=unused-argument

        if self.POINTS is None:
            raise NotImplementedError("Collectible.points must be overloaded")
        return self.POINTS


class Alien(Moveable, Collidable, Killable, Collectible, Audible, Renderable):
    """
    Represents any alien units.
    """

    # pylint: disable=abstract-method
    ...


class Invader(Gestalt, Reskinable, Alien):
    """
    Represents the alien units that are actually Gestalt members.
    """

    ...


class Squid(Invader):
    """
    The Squid Invader.
    """

    POINTS = 30

    COLOR: Color = Color.CYAN
    ICON: Icon = make_icon(
        """
        ▗▆▖
        ▚╿▞
        """
    )
    ALT: Icon = make_icon(
        """
        ▗▆▖
        ▞╽▚
        """
    )
    DEATH: Icon = make_icon(
        """
        ⟫╳⟪
        ⠈ ⠁
        """
    )


class Crab(Invader):
    """
    The Crab Invader.
    """

    POINTS = 20

    COLOR: Color = Color.CYAN
    ICON: Icon = make_icon(
        """
        ▙▀▟
        ▝▔▘
        """
    )
    ALT: Icon = make_icon(
        """
        ▙▀▟
        ▘▔▝
        """
    )
    DEATH: Icon = make_icon(
        """
        ⟫╳⟪
        ⠈ ⠁
        """
    )


class Octopus(Invader):
    """
    The Octopus Invader.
    """

    POINTS = 10

    COLOR: Color = Color.CYAN
    ICON: Icon = make_icon(
        """
        ▟▆▙
        ▘▔▝
        """
    )
    ALT: Icon = make_icon(
        """
        ▟▆▙
        ▝▔▘
        """
    )
    DEATH: Icon = make_icon(
        """
        ⟫╳⟪
        ⠈ ⠁
        """
    )


class Mystery(Alien):
    """
    The Mystery Ship.
    """

    COLOR: Color = Color.RED
    ICON: Icon = make_icon(
        """
        ▁▁▁
       ▞█▀█▚
       ▔▘▔▝▔
        """
    )
    DEATH: Icon = make_icon(
        """
         ⎽
       ⟩⟫╳⟪〈
         ⎺
        """
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._reached_wall = False
        if self.use_sound:
            self._sound = Sound.MYSTERY.play()

    def silence(self) -> None:
        """
        Kills any sound that's playing for this ship.
        """
        if self.use_sound and self._sound.is_playing():
            self._sound.stop()

    def points(self, shot_count: int) -> int:
        """
        Return the points value for the Mystery ship.
        """
        factors = [10, 5, 5, 10, 15, 10, 10, 5, 30, 10, 10, 10, 5, 15, 10]
        return 10 * factors[shot_count % 15]

    def reached_wall(self) -> bool:
        """
        Check if the ship reached the wall unscathed.
        """
        return self._reached_wall

    def on_every(self, frame: int) -> bool:
        """
        Slow the down fractionally to allow the Player a chance.
        """
        return frame % 3 == 0

    def wall(self, new_position: int, limit: int) -> int:
        """
        Stop on wall impact. Mystery ship only travels east/west.
        """
        assert self.direction is not Direction.NORTH
        assert self.direction is not Direction.SOUTH

        # handle east wall impact
        if self.direction is Direction.WEST:
            if new_position < limit + 1:
                self._reached_wall = True
                self.die()
            return max([new_position, limit])

        # handle west wall impact
        if new_position + self.w < limit - 1:
            self._reached_wall = True
            self.die()

        return min([new_position, limit - self.w - 1])

    def die(self):
        """
        Kill this Mystery ship.
        """
        self.silence()
        self.color = Color.RED
        self.speed = 0
        if not self.reached_wall():
            super().die()

    @classmethod
    def spawn(
        cls, x: int, y: int, width: int, shot_count: int, use_sound: bool = True
    ) -> Mystery:
        """
        Spawn a new Mystery ship.
        """
        # pylint: disable=invalid-name, too-many-arguments

        on_right = shot_count % 2 == 0
        mystery = Mystery(x, y, speed=1, use_sound=use_sound)
        mystery.x = width - x - mystery.w if on_right else mystery.x
        mystery.direction = Direction.WEST if on_right else Direction.EAST
        return mystery


class Droppable(Moveable, Collidable, Killable, Reskinable, Renderable):
    """
    Any object in the alien arsenal.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.direction = Direction.SOUTH
        self.dropped_from: int = self.y
        self.in_flight: int = 0

    def on_every(self, frame: int) -> bool:
        """
        Retard the bombs a little.
        """
        return frame % 3 == 0

    def move(self, stdscr: Window, frame: int, width: int, height: int) -> None:
        super().move(stdscr, frame, width, height)
        self.in_flight += 1

    def wall(self, new_position: int, limit: int) -> int:
        """
        Stop on wall impact. Bombs only travel south.
        """
        assert self.direction is Direction.SOUTH
        if new_position > limit - 3:
            self.die()
        return min([new_position, limit - 3])

    def die(self):
        """
        Kill this bomb.
        """
        self.color = Color.RED
        self.speed = 0
        super().die()


class Bomb(Droppable):
    """
    The Invader's main weapon.
    """

    COLOR: Color = Color.CYAN
    ICON: Icon = make_icon(
        """
        ╿
        """
    )
    ALT: Icon = make_icon(
        """
        ╽
        """
    )
    DEATH: Icon = make_icon(
        """
        ✸
        """
    )


class Seeker(Bomb):
    """
    A bomb that starts above the Player's position.
    """

    ICON: Icon = make_icon(
        """
        ⎬
        """
    )
    ALT: Icon = make_icon(
        """
        ⎨
        """
    )


class SuperBomb(Bomb):
    """
    The Invader's most powerful  weapon.
    """

    COLOR: Color = Color.MAGENTA
    ICON: Icon = make_icon(
        """
        ⟅
        """
    )
    ALT: Icon = make_icon(
        """
        ⟆
        """
    )
    DEATH: Icon = make_icon(
        """
        ✺
        """
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._hitpoints = 1

    def die(self):
        """
        Kill this bomb.
        """
        if self._hitpoints:
            self._hitpoints -= 1
        else:
            super().die()


class Barrier(Destructible, Renderable):
    """
    The last line of defense between the Player and the Invaders.
    """

    COLOR: Color = Color.GREEN
    ICON: Icon = make_icon(
        """
        ▟██████▙
        ████████
        ████████
        ████████
        ▀▀    ▀▀
        """
    )


__all__ = [
    "Barrier",
    "Bomb",
    "Bullet",
    "Crab",
    "Gestalt",
    "Killable",
    "Moveable",
    "Mystery",
    "Octopus",
    "Player",
    "Renderable",
    "Squid",
    "SuperBomb",
]
