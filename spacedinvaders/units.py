#! /usr/bin/env python3
# coding=utf-8
"""
A textual, terminal spin on an arcade classic.
"""
# stdlib imports
import curses
import locale
import time
from curses import window
from typing import ByteString, List, Optional

# local imports
from spacedinvaders.constants import Color, Direction
from spacedinvaders.utils import regularize, colorize
from spacedinvaders.sounds import Sound

CODEC = locale.getpreferredencoding()
WALL_BUFFER = 5
BULLET_IN_FLIGHT = False

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
            for line in self._lines:
                try:
                    stdscr.addstr(self.y, self.x, line)
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

    @property
    def direction(self) -> Direction:
        """
        The direction in which the unit is moving.
        """
        return self._direction

    def turn(self, direction: Direction) -> Direction:
        """
        Turns the unit, returning its original direction.
        """
        self._direction = direction

    def move(self, stdscr: Window) -> None:
        """
        Moves the unit in the direction it's facing.
        Calls Moveable.wall(new_position, limit) near wall collisions.
        """

        if self.direction is Direction.NORTH:
            new_y = self.y - self.speed
            if new_y > WALL_BUFFER:
                self.y = new_y
            else:
                self.y = self.wall(new_y, 0)
            return

        if self.direction is Direction.WEST:
            new_x = self.x - self.speed
            if new_x > WALL_BUFFER:
                self.x = new_x
            else:
                self.x = self.wall(new_x, 0)
            return

        height, width = stdscr.getmaxyx()

        if self.direction is Direction.SOUTH:
            new_y = self.y + self.speed
            if new_y + self.h < height - WALL_BUFFER:
                self.y = new_y
            else:
                self.y = self.wall(new_y, height)
            return

        if self.direction is Direction.EAST:
            new_x = self.x + self.speed
            if new_x + self.w < width - WALL_BUFFER:
                self.x = new_x
            else:
                self.x = self.wall(new_x, width)
            return

    def wall(self, new_position: int, limit: int) -> int:
        """
        Handle wall impact in the direction just moved.
        """
        raise NotImplementedError("Subclass must implement")


class Bullet(Moveable, Killable, Renderable):
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
        ✸✺✸
                           """
    )

    _IN_FLIGHT: bool = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._direction = Direction.NORTH
        Bullet._IN_FLIGHT = True

    def wall(self, new_position: int, limit: int) -> int:
        """
        Stop on wall impact. Bullet only travels north.
        """
        assert self.direction is Direction.NORTH
        if new_position < limit + 1:
            self.die()
            return limit + 1
        return new_position

    def die(self):
        """
        Kill this bullet, allowing the user to fire again.
        """
        Bullet._IN_FLIGHT = False
        self.color = Color.RED
        self.speed = 0
        super().die()

    @classmethod
    def in_flight(cls):
        """
        Test if a bullet is in flight.
        """
        return cls._IN_FLIGHT


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
            if new_position < limit + 3:
                self.speed = 0
                return limit + 3

        if self.direction is Direction.EAST:
            if new_position + self.w < limit - 3:
                self.speed = 0
                return limit - self.w - 3

        return new_position

    def fire(self) -> Optional[Bullet]:
        """
        Fire a Bullet upwards, if enough time has elapsed
        since the last shot.
        """
        if not Bullet.in_flight():
            Sound.SHOOT.play()
            return Bullet(self.x, self.y, speed=2)
        return None

    def die(self) -> None:
        """
        Die a death!
        """
        self.speed = 0
        Sound.EXPLOSION.play()
        super().die()
