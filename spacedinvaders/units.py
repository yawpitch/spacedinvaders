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
from curses import window
from typing import ByteString, Dict, List, Optional, Set, Tuple

# local imports
from spacedinvaders.constants import Color, Direction
from spacedinvaders.utils import regularize, colorize
from spacedinvaders.sounds import Sound

CODEC = locale.getpreferredencoding()

Icon = str
Window = curses.window


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

    def __init__(self, x: int, y: int):
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
    def color(self) -> int:
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


class Killable:
    """
    Mixin to allow a Renderable to be killed.
    """

    # icon to present on death
    DEATH: Icon

    def __init__(self, *args):
        super().__init__(*args)
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


class Moveable:
    """
    Mixin to allow a Renderable to be moved.
    """

    WALL_BUFFER = 5

    def __init__(self, *args, speed: int = 1):
        super().__init__(*args)
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

    def turn(self, direction: Direction) -> Direction:
        """
        Turns the unit, returning its original direction.
        """
        self.direction = direction

    def move(self, stdscr: Window, frame: int, width: int, height: int) -> None:
        """
        Moves the unit in the direction it's facing.
        Calls Moveable.wall(new_position, limit) near wall collisions.
        """
        # only move on every scheduled frame
        if not self.on_every(frame):
            return None

        if self.direction is Direction.NORTH:
            new_y = self.y - self.speed
            if new_y > self.WALL_BUFFER:
                self.y = new_y
            else:
                self.y = self.wall(new_y, 0)
            return

        if self.direction is Direction.WEST:
            new_x = self.x - self.speed
            if new_x > self.WALL_BUFFER:
                self.x = new_x
            else:
                self.x = self.wall(new_x, 0)
            return

        if self.direction is Direction.SOUTH:
            new_y = self.y + self.speed
            if new_y + self.h < height - self.WALL_BUFFER:
                self.y = new_y
            else:
                self.y = self.wall(new_y, height)
            return

        if self.direction is Direction.EAST:
            new_x = self.x + self.speed
            if new_x + self.w < width - self.WALL_BUFFER:
                self.x = new_x
            else:
                self.x = self.wall(new_x, width)
            return

    def wall(self, new_position: int, limit: int) -> int:
        """
        Handle wall impact in the direction just moved.
        """
        raise NotImplementedError("Subclass must implement")


class Gestalt(Moveable):
    """
    Moveables that act as one.
    """

    COLUMNS = 11
    ROWS = 5
    TURN_BUFFER = 8
    hive_members = [[] for _ in range(COLUMNS)]
    hive_moves = 0
    hive_direction = Direction.EAST
    hive_aboutface = Direction.WEST
    hive_speed = 1
    hive_turned = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        row, col = divmod(sum(len(l) for l in Gestalt.hive_members), Gestalt.COLUMNS)
        assert (row, col) != (Gestalt.ROWS, 1)
        Gestalt.hive_members[col].append(self)

    @classmethod
    def populate(cls, x: int, y: int, *, x_sep: int = 2, y_sep: int = 1) -> None:
        """
        Populate the Gestalt.
        """
        # clear any existing hive
        for col in Gestalt.hive_members:
            col.clear()

        # place the invaders
        y_pos = y
        for row in range(Gestalt.ROWS):
            x_pos = x
            species = Squid if row < 1 else Crab if row < 3 else Octopus
            for col in range(cls.COLUMNS):
                vader = species(x_pos, y_pos, speed=1)
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
        Speed up as invaders get kill.
        """
        flip = frame % 15 == 0
        # if flip:
        #   Sound.INVADER_4.play()
        return flip

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
    def last_man(cls) -> Optional[Gestalt]:
        """
        As long as one invader remains, return it.
        """
        try:
            return cls.hive_members[0][0]
        except IndexError:
            return None

    @classmethod
    def lockstep(cls, stdscr: Window, frame: int, width: int, height: int) -> None:
        """
        Move as one. Fight as one. Die as one?
        """
        assert cls.hive_direction is not Direction.NORTH

        flip = cls.on_every(frame)
        if not flip:
            return None

        members = Gestalt.hive_members

        no_turn = True
        # by default search west to east
        columns = range(len(members))
        # reverse the search if the gestalt is moving east
        if cls.hive_direction is Direction.EAST:
            columns = reversed(columns)

        for col in columns:
            column = members[col]
            # always search up from the player's position
            for row in reversed(range(len(column))):
                member = column[row]
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

                if member.icon == member.ICON:
                    member.icon = member.ALT
                else:
                    member.icon = member.ICON

                member.move(stdscr, frame, width, height)

    def wall(self, new_position: int, limit: int) -> int:
        """
        Handle wall impact. When we turn one, we turn all (we
        sayeth with more than a little irony).
        """
        raise RuntimeError(f"{self} -> {new_position} @ {limit}")

    @classmethod
    def render_all(cls, stdscr: Window) -> None:
        """
        Render the hive.
        """
        [[v.render(stdscr) for v in col] for col in cls.hive_members]


class Collidable:
    """
    Mixin to allow a Renderable to be collided with.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
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
        if hasattr(self, "speed"):
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
        if hasattr(self, "speed"):
            if self.direction is Direction.NORTH:
                return self.y - self.speed
            if self.direction is Direction.SOUTH:
                return self.y + self.speed
        return self.y

    def collides_with(self, other: Collidable) -> bool:
        """
        Tests if this unit and some other will collide on next move.
        """
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
        super().__init__(*args)
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
                penetration = 2 if isinstance(other, SuperBomb) else 1
                hit_x = other.cx - self.cx
                # don't bother processing devastated columns
                if hit_x in self._devastated["cols"]:
                    other.impacted = False
                    continue
                # process the first brick hit from the bottom
                for hit_y in range(self.h + 1):
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
                cols_damaged, rows_damaged = set(), set()
                for y_idx in range(other.cy, other.cy + other.h + 1):
                    # ignore devastated and non-overlapping rows
                    if (
                        y_idx in self._devastated["rows"]
                        or y_idx > self.cy + self.h
                        or y_ix < self.cy
                    ):
                        continue
                    for x_idx in range(other.cx, other.cx + other.w + 1):
                        # ignore devastated and non-overlapping colums
                        if (
                            x_idx in self._devastated["cols"]
                            or x_idx > self.xw
                            or x_idx < self.cx
                        ):
                            continue
                        hit_y = other.cy - self.cy
                        hit_x = other.cx - self.cx
                        if self._state[hit_y][hit_x] != " ":
                            self._state[hit_y][hit_x] = " "
                            rows_damaged.add(hit_y)
                            cols_damaged.add(hit_x)
                            damaged = True

                # check for devastation
                for row_idx in rows_damaged:
                    for col_idx in range(self.cx, self.cx + self.w + 1):
                        if col_idx in self._devastated["cols"]:
                            continue
                        if self._state[row_idx][col_idx] != " ":
                            break
                    else:
                        self._devastated["rows"].add(row_idx)

                for col_idx in cols_damaged:
                    for row_idx in range(self.cy, self.cy + self.h + 1):
                        if row_idx in self._devastated["rows"]:
                            continue
                        if self._state[row_idx][col_idx] != " ":
                            break
                    else:
                        self._devastated["rows"].add(row_idx)

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
    DEATH: Optional[Icon] = make_icon(
        """
         ✺
        """
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._direction = Direction.NORTH

    def wall(self, new_position: int, limit: int) -> int:
        """
        Stop on wall impact. Bullet only travels north.
        """
        assert self.direction is Direction.NORTH
        if new_position < limit + 2:
            self.die()
            return max([new_position, limit + 2])
        return new_position

    def die(self):
        """
        Kill this bullet, allowing the user to fire again.
        """
        self.color = Color.RED
        self.speed = 0
        super().die()


class Player(Moveable, Killable, Renderable):
    """
    The player's unit.
    """

    COLOR: Color = Color.YELLOW
    ICON: Icon = make_icon(
        """
        ▄█▄
        """
    )
    DEATH: Optional[Icon] = make_icon(
        """
        ▘▙▁
        """
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_shot = 0

    def wall(self, new_position: int, limit: int) -> int:
        """
        Stop on wall impact. Player only travels east/west.
        """
        assert self.direction is not Direction.NORTH
        assert self.direction is not Direction.SOUTH

        if self.direction is Direction.WEST:
            return max([new_position, limit + 1])
        return min([new_position, limit - self.w - 2])

    def fire(self) -> Bullet:
        """
        Fire a Bullet upwards, if enough time has elapsed
        since the last shot.
        """
        Sound.SHOOT.play()
        return Bullet((self.x + (self.x + self.w)) // 2, self.y - 1, speed=3)

    def die(self) -> None:
        """
        Die a death!
        """
        self.speed = 0
        Sound.EXPLOSION.play()
        super().die()


class Collectible:
    """
    Mixin to make a unit have a points value.
    """

    POINTS: Optional[int] = None

    def points(self, shot_count: int) -> int:
        """
        Return the points this Collectible is worth at this shot count.
        """
        if self.POINTS is None:
            raise NotImplementedError("Collectible.points must be overloaded")
        return self.POINTS


class Squid(Gestalt, Collidable, Killable, Collectible, Renderable):
    """
    The Squid Invader.
    """

    POINTS: 30

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
        """
    )


class Crab(Gestalt, Collidable, Killable, Collectible, Renderable):
    """
    The Crab Invader.
    """

    POINTS: 20

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
        """
    )


class Octopus(Gestalt, Collidable, Killable, Collectible, Renderable):
    """
    The Octopus Invader.
    """

    POINTS: 10

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
        """
    )


class Mystery(Moveable, Collidable, Killable, Collectible, Renderable):
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
        self._sound = Sound.MYSTERY.play()

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
        return frame % 4 != 0

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
        if self._sound.is_playing():
            self._sound.stop()
        self.color = Color.RED
        self.speed = 0
        if not self.reached_wall():
            super().die()

    @classmethod
    def spawn(cls, x: int, y: int, width: int, shot_count: int) -> Mystery:
        """
        Spawn a new Mystery ship.
        """
        on_right = shot_count % 2 == 0
        mystery = Mystery(x, y, speed=1)
        mystery.x = width - x - mystery.w if on_right else mystery.x
        mystery.direction = Direction.WEST if on_right else Direction.EAST
        return mystery


class Bomb(Moveable, Collidable, Killable, Renderable):
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
    DEATH: Optional[Icon] = make_icon(
        """
        ✸
        """
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._direction = Direction.SOUTH

    def wall(self, new_position: int, limit: int) -> int:
        """
        Stop on wall impact. Bombs only travel south.
        """
        assert self.direction is Direction.SOUTH
        if new_position > limit - 2:
            self.die()
        return min([new_position, limit - 2])

    def die(self):
        """
        Kill this bomb.
        """
        self.color = Color.GREEN
        self.speed = 0
        super().die()


class SuperBomb(Bomb):
    """
    The Invader's alt weapon.
    """

    COLOR: Color = Color.MAGENTA
    ICON: Icon = make_icon(
        """
        ⧘
        """
    )
    ALT: Icon = make_icon(
        """
        ⧙
        """
    )
    DEATH: Optional[Icon] = make_icon(
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
        if self_hitpoints:
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
