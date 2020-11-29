#! /usr/bin/env python3
import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="spacedinvaders",
    author="Michael Morehouse",
    author_email="yawpitch@yawpitchroll.com",
    description="A textual, terminal spin on an arcade classic",
    keywords="space invaders classic arcade game",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yawpitch/spacedinvaders",
    packages=setuptools.find_packages(),
    package_dir={"spacedinvaders": "spacedinvaders"},
    package_data={"spacedinvaders": ["media/*.wav"]},
    entry_points={
        "console_scripts": [
            "spacedinvaders = spacedinvaders:main",
        ]
    },
    extras_require={
        "SOUNDS": ["simpleaudio"],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: Implementation :: CPython",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: POSIX",
        "Operating System :: POSIX :: Linux",
        "Environment :: Console :: Curses",
        "Intended Audience :: Education",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Games/Entertainment",
        "Topic :: Games/Entertainment :: Arcade",
        "Typing :: Typed",
    ],
    python_requires=">=3.7",
)
