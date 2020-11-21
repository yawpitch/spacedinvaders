#! /usr/bin/env python3
# coding=utf-8
"""
Various sounds used by the game, if available.
"""
# stdlib imports
from functools import partial
import pkg_resources

# external library imports
try:
    from simpleaudio import WaveObject
except ImportError:

    class WaveObject:
        """
        Dummy WaveObject if simpleaudio fails to import.
        """

        # pylint: disable=no-self-use, missing-function-docstring

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

    # pylint: disable=too-few-public-methods

    EXPLOSION = _load(_resource("media/explosion.wav"))
    INVADER = _load(_resource("media/invader.wav"))
    KILLSHOT = _load(_resource("media/killshot.wav"))
    SHOOT = _load(_resource("media/shoot.wav"))
    MYSTERY = _load(_resource("media/mystery.wav"))
    HADOUKEN = _load(_resource("media/hadouken.wav"))
    COIN = _load(_resource("media/coin.wav"))
