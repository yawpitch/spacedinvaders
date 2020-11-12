#! /usr/bin/env python3
# coding=utf-8
"""
Various sounds used by the game, if available.
"""
# stdlib imports
import pkg_resources
from functools import partial

# external library imports
try:
    from simpleaudio import WaveObject
except ImportError:

    class WaveObject:
        """
        Dummy WaveObject if simpleaudio fails to import.
        """

        def play(self):
            ...

        @classmethod
        def from_wave_file(cls, _):
            return cls()


# function aliases to keep the class clean
_resource = partial(pkg_resources.resource_filename, "spacedinvaders")
_load = WaveObject.from_wave_file


class Sound:
    """
    Sounds for use in the game.
    If simplesound is not available, the Sound.[SOUND].play
    method is a noop.
    """

    EXPLOSION = _load(_resource("media/explosion.wav"))
    INVADER_1 = _load(_resource("media/fastinvader1.wav"))
    INVADER_2 = _load(_resource("media/fastinvader2.wav"))
    INVADER_3 = _load(_resource("media/fastinvader3.wav"))
    INVADER_4 = _load(_resource("media/fastinvader4.wav"))
    KILLSHOT = _load(_resource("media/invaderkilled.wav"))
    SHOOT = _load(_resource("media/shoot.wav"))
    UFO_HIGH = _load(_resource("media/ufo_highpitch.wav"))
    UFO_LOW = _load(_resource("media/ufo_lowpitch.wav"))
