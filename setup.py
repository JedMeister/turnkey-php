#!/usr/bin/python3

from setuptools import setup

setup(
    name='turnkey-php',
    version='0.1',
    description="Update/control PHP versions (from default Debia nor sury.org)",
    author='TurnKey GNU/Linux',
    author_email='jeremy@turnkeylinux.org',
    license='GPLv3+',
    url='https://github.com/JedMeister/turnkey-php',
    packages=['turnkey_php_lib'],
    scripts=['turnkey-php']
)
