import os
import sys
import datetime
import tempfile
import subprocess
import re
import urllib.request
from pathlib import Path
from subprocess import PIPE, STDOUT
from typing import Any, List, Tuple

SURY_KEY_URL = "https://packages.sury.org/php/apt.gpg"
SURY_KEY_LOC = "/usr/share/keyrings/php-sury.org.gpg"

PHP_VERSIONS = ['default', '7.3', '7.4', '8.0', '8.1']
PHP_DEFAULTS = {'buster': '7.3',
                'bullseye': '7.4'}
PACKAGES = ['php{PHP_V}', 'php{PHP_V}-common', 'php{PHP_V}-cli',

WEBSERVERS = {'apache': 'libapache2-mod-php{PHP_V}',
              'php-fpm': 'php{PHP_V}-fpm']
DATABASES = ['mysql': 'php{PHP_V}-mysql',
             'pgsql': 'php{PHP_V}-pgsql']
LIB = Path('/var/lib/turnkey-php')
TPL = Path('/usr/share/turnkey-php/templates')
CODENAME = subprocess.run(['lsb_release', '-sc'],
                          stdout=PIPE, text=True).stdout.strip()

class TklPhpError(Exception):
    pass


def _init():
    LIB.mkdir(parents=True, exist_ok=True)


def copy_files(codename: str = None, php_v: str = None):
    if not codename:
        codename = CODENAME
    if not php_v:
        php_v = PHP_DEFAULTS.get(codename, None)
    if not php_v:
        return False
    sources = Path('/etc/apt/sources.list.d')
    preferences = Path('/etc/apt/preferences.d')
    sources_tpl = Path(TPL, 'apt_sources.list')
    prefs_tpl = Path(TPL, 'apt_preferences.pref')
    with open(Path(sources, 'php.list.disabled'), 'w') as src_fob:
        with open(sources_tpl, 'r') as tpl_fob:
            for tpl_line in tpl_fob:
                if 'CODENAME' in tpl_line:
                    tpl_line = tpl_line.format(CODENAME=codename)
                src_fob.write(tpl_line)
    with open(Path(preferences, 'php-sury.pref'), 'w') as prf_fob:
        with open(prefs_tpl, 'r') as tpl_fob:
            for tpl_line in tpl_fob:
                if 'PHP_V' in tpl_line:
                    tpl_line = tpl_line.format(PHP_V=php_v)
    return True


def _ver_sort_key(e: Any) -> Tuple[int, Any]:
    """Use this as key for sorting PHP_VERSIONS."""
    e = str(e)
    if e[0].isalpha():
        return -1, e
    elif e[0].isdigit():
        return 0, e
    return 1, e


def get_php_default():
    codename = subprocess.run(
            ['lsb_release', '-sc'], stdout=PIPE, text=True).stdout.strip()
    return PHP_DEFAULTS.get(codename, '')


def check_gpg_expiry() -> bool:
    """Check GPG expiry timestamp.

    Returns False if:
     - key file not found, or
     - no expiry found, or
     - key has expired

     Returns True otherwise
    """
    if not Path(SURY_KEY_LOC).exists:
        return False
    with tempfile.TemporaryDirectory() as tmpdirname:
        proc = subprocess.run(['gpg', '--list-keys', f'--homedir={tmpdirname}',
                               f'--keyring={SURY_KEY_LOC}', '--with-colons'],
                              stderr=STDOUT, stdout=PIPE, text=True)
        if proc.returncode == '0':
            raise TklPhpError(proc.stdout)
        expiry = ''
        for line in proc.stdout.split('\n'):
            # currently only checks primary key expiry
            if line.startswith('pub'):
                expiry = line.split(':')[6]
            if expiry:
                break
        if not expiry:
            return False
        if int(expiry) <= int(datetime.datetime.now(tz=None).strftime('%s')):
            return False
    return True


def update_sury_key(force: bool = False) -> bool:
    """Update the sury.org apt key if requried.

    By default will check if key is valid first and only update if it's not.

    force=True can be used to force (re)download of key.

    Note that when this script is run and a relative path share/keyrings
    exists, the script will use that path instead of SURY_KEY_LOC
    """
    if Path('share/keyrings').exists():
        keyfile = Path('share/keyrings/php-sury.org.gpg')
    else:
        keyfile = Path(SURY_KEY_LOC)
    if force or not check_gpg_expiry():
        response = urllib.request.urlretrieve(SURY_KEY_URL, keyfile)
        if response[0] == keyfile:
            return True
    return False


def get_php_cli_v() -> str:
    """Function to get the current PHP CLI version."""
    try:
        return subprocess.run(['php', '-v'],
                              stdout=PIPE, text=True, check=True
                              ).stdout.split()[1]
    except subprocess.CalledProcessError:
        return ''


def get_php_apache_v() -> str:
    """Function to get the current PHP Apache2 (mod_php) version.

    Checks /etc/apache2/mods-enabled for file(s) that start with 'php',
    end with '.conf. or '.load' and the remaining part matches the regex:

        ^[0-9]+\.[0-9]+$

        i.e. one or more digits, a literal '.' and one or more digits.

        e.g.:

            'php7.3.conf' would return '7.3'
    """
    php_module_enabled = ''
    php_module_available: List = []
    version: List = []
    mods = Path('/etc/apache2/mods-enabled')
    if not mods.exists():
        return ''
    for item in mods.iterdir():
        out = ''
        if item.name.startswith('php'):
            out = item.name[3:]
        if Path(out).suffix == '.conf' or Path(out).suffix == '.load':
            out = out[:-5]
        match = re.match(r'^[0-9]+\.[0-9]+$', out)
        if match:
            version.append(out)
    version = list(set(version))
    if len(version) > 1:
        version.sort()
        print(f'problem: detected multiple PHP versions in Apache: {version}')
    return version[0]


def get_php_fpm_v():
    """Function to get the current PHP-FPM version.

    Checks for a systemd service named phpX.Y-fpm (where X.Y is PHP version).
    If it finds one, it returns X.Y.
    """
    command = ['systemctl', '--type=service', '--state=active', '--no-pager',
               '--no-legend']
    services = subprocess.run(command, stdout=PIPE, text=True)
    version: List = []
    for line in services.stdout.split('\n'):
        service = line.split(' ')[0]
        if service.startswith('php') and service.endswith('-fpm.service'):
            version.append(service[3:][:-12])
    if len(version) < 1:
        return ''
    if len(version) > 1:
        print(f"problem: multiple php-fpm services found: {version}")
    return version[0]


def get_current_versions():
    """Function to get the current PHP version of components."""
    return {'cli': get_php_cli_v(),
            'apache': get_php_apache_v(),
            'fpm': get_php_fpm_v()}
