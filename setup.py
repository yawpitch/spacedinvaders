#! /usr/bin/env python3
import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="spacedinvaders",
    version="0.0.1",
    author="Michael Morehouse",
    author_email="yawpitch@yawpitchroll.com",
    description="A textual, terminal spin on an arcade classic",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yawpitch/spacedinvaders",
    packages=setuptools.find_packages(),
    package_dir={'spacedinvaders': 'spacedinvaders'},
    package_data={'spacedinvaders': ['media/*.wav']},
    entry_points={
        "console_scripts": [
            "spacedinvaders = spacedinvaders:main",
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
)
