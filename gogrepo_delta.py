# -*- coding: utf-8 -*-
# The following code block between #START# and #END#
# generates an error message if this script is called as a shell script.
# Using a "shebang" instead would fail on Windows.
#START#
if False:
    print("Please start this script with a python interpreter: python /path/to/gogrepo_delta.py")
#END#
__appname__ = 'gogrepo_delta.py'
__author__ = 'eddie3,kalanyr,MarS301,claude.ai,chatgpt'
__version__ = '0.5.50'   # 0.5.N: N is the number of the newest entry in CHANGELOG.md (raise it with every new entry)
__url__ = 'https://github.com/MarS301/gogrepo_delta'   # based on gogrepoc by kalanyr, which is based on gogrepo by eddie3

# =============================================================================================
# gogrepo_delta.py - back up your GOG library (a single file, by choice)
#
# Based on gogrepoc by kalanyr, which is based on gogrepo by eddie3. How to use it: README.md.
# Every change, the known issues and how the version number works: CHANGELOG.md (the version is
# 0.5.N, where N is the number of the newest entry there). Places that were changed for an entry
# carry a "Refactoring" comment or docstring.
# =============================================================================================
# Future idea (not implemented): optional plugin hooks for extensions; keep core/base functionality
# in this single file and define a stable extension interface before adding any plugin loader.
# =============================================================================================


# imports
import unicodedata
import ast
import tempfile
import tokenize
import difflib
import os
import sys
import threading
import atexit
import logging
import html5lib
import pprint
import time
import zipfile
import hashlib
import getpass
import argparse
import io
import datetime
import shutil
import xml.etree.ElementTree
import copy
import logging.handlers
import ctypes
import requests
import re
import configparser
import textwrap
#import OpenSSL
import platform
import locale
import warnings
import webbrowser
import json
import csv
import zlib
from fnmatch import fnmatch
import email.utils
import signal
import psutil
import glob
import tempfile
import errno
minPy3 = [3,10]          # recommended: the version the tests run on
specialPy3=[3,8]         # oldest version that can still start the program (the last one for Windows 7)

def check_python_version(version_info=None, stream=None):
    """Stops (exit status 1) below specialPy3; between specialPy3 and minPy3 it only warns and carries on.
    Refactoring: the old check exited below minPy3 as well, so the specialPy3 branch was dead (3.8 and 3.9 could never start).
    The one call that needs 3.10 (glob root_dir) is gone, see _multi_zip_parts()."""
    version_info = sys.version_info if version_info is None else version_info
    stream = sys.stderr if stream is None else stream
    wanted = "%d.%d" % tuple(minPy3)
    oldest = "%d.%d" % tuple(specialPy3)
    if tuple(version_info[:2]) < tuple(specialPy3):
        print("Your Python version is not supported, please update to " + wanted + "+ if possible and " + oldest + " if not (eg Windows 7 )", file=stream)
        sys.exit(1)
    if tuple(version_info[:2]) < tuple(minPy3):
        print("Warning: Python %d.%d is older than the recommended %s+. It should start, but it is not covered by the tests; please update if you can." % (version_info[0], version_info[1], wanted), file=stream)

check_python_version()

from queue import Queue, Empty
from urllib.parse import urlparse, unquote, urlunparse, parse_qs, urlencode
from itertools import zip_longest
from io import StringIO

if (platform.system() == "Windows"):
    import ctypes.wintypes

def _import_macos_modules():
    """(CoreFoundation, objc) from PyObjC, or (None, None) when it is not installed.
    Refactoring: the import used to be unconditional on macOS, so the program died at start without PyObjC although the README lists it as
    optional. It is only needed for the sleep inhibitor (Wakelock); without it the program runs and the computer may go to sleep."""
    try:
        import CoreFoundation as core_foundation   # CFStringCreateWithCString ...
        import objc as pyobjc                      # pyobjc_id
    except ImportError:
        return None, None
    return core_foundation, pyobjc

CoreFoundation, objc = _import_macos_modules() if platform.system() == "Darwin" else (None, None)

if not ((platform.system() == "Darwin") or (platform.system() == "Windows")):
    try:
        import PyQt5.QtDBus
    except ImportError:
        pass



# optional imports
try:
    from html2text import html2text
except ImportError:
    def html2text(x): return x

# BLAKE3 (entry 38): optional. Without the package the program works exactly as before, MD5 only.
try:
    import blake3 as _blake3
except ImportError:
    _blake3 = None


GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
CREATE_NEW = 0x1
OPEN_EXISTING = 0x3
FILE_BEGIN = 0x0


# ---------------------------------------------------------------------------------------------
# Configuration file (gogrepo_delta.cfg)
# ---------------------------------------------------------------------------------------------
# Two things can be set in the file: the program settings (timeouts, retries, threads, ...) in [settings], and the
# default for every command-line flag (sections [common] and one per command). The settings are read here, when the
# program starts, because the constants further down are built from them. The flag defaults are applied when the
# command line is read (see apply_config_flags). The file is created with all keys and explanations when it is missing.
USER_CONFIG_FILENAME = 'gogrepo_delta.cfg'
USER_CONFIG_ENV_VAR = 'GOGREPO_DELTA_CONFIG'   # use another config file (also used by the tests)


class ConfigError(Exception):
    """The config file cannot be read or holds a value that cannot be used. The message says where and why."""


def user_config_path():
    return os.environ.get(USER_CONFIG_ENV_VAR) or USER_CONFIG_FILENAME


# key, kind, built-in default, smallest allowed value (kinds: int, number = int or decimal, codes = list of HTTP codes)
SETTINGS = [
    ('log_max_mb', 'int', 180, 1),
    ('log_backups', 'int', 9, 0),
    ('http_retry_count', 'int', 4, 0),
    ('http_retry_delay', 'number', 5, 0),
    ('http_timeout', 'number', 60, 1),
    ('http_no_retry_codes', 'codes', (404, 403), None),
    ('download_chunk_size', 'int', 64 * 1024, 1),
    ('download_threads', 'int', 4, 1),
    ('progress_interval', 'number', 1, 0.1),
    ('resume_save_threshold', 'int', 50, 1),
    ('summary_max_items', 'int', 15, 1),
    ('max_listed_failures', 'int', 40, 1),
    ('file_replace_attempts', 'int', 5, 1),
    ('file_replace_delay', 'number', 0.2, 0),
]
SETTING_KEYS = dict((s[0], s) for s in SETTINGS)

# how the settings are grouped and explained in the generated file: one comment per group, the texts in the order of the keys
SETTING_GROUPS = [
    (('log_max_mb', 'log_backups'),
     'log file gogrepo.log: size in MB at which a new file is started; how many old files are kept'),
    (('http_retry_count', 'http_retry_delay', 'http_timeout'),
     'requests to GOG: retries after a failure; seconds between tries (the original code warns that less than about 10 '
     'seconds between the first and third try gives error 503); seconds without an answer or data before giving up'),
    (('http_no_retry_codes',),
     'HTTP error codes that are final and not retried (503 is left out on purpose: the original code notes that GOG uses '
     'it to ask for a short wait)'),
    (('download_chunk_size', 'download_threads', 'progress_interval'),
     'downloads: bytes read per piece (a piece must arrive within http_timeout seconds); files downloaded at the same '
     'time; seconds between progress lines'),
    (('resume_save_threshold', 'summary_max_items', 'max_listed_failures'),
     'update saves its progress every N games; combined warnings list at most N names; the summary at the end lists at '
     'most N failed items'),
    (('file_replace_attempts', 'file_replace_delay'),
     'saving a file is retried when Windows has it locked for a moment (virus scanner): number of attempts; seconds '
     'between them'),
]


def format_setting(kind, value):
    return ', '.join(str(v) for v in value) if kind == 'codes' else str(value)


def parse_setting(key, text):
    """The value of a [settings] entry, from its text. Raises ValueError (with the reason) if it cannot be used."""
    kind, minimum = SETTING_KEYS[key][1], SETTING_KEYS[key][3]
    text = text.strip()
    if kind == 'codes':
        codes = []
        for part in text.replace('\n', ',').split(','):
            part = part.strip()
            if not part:
                continue
            if not part.isdigit() or not 100 <= int(part) <= 599:
                raise ValueError('%r is not an HTTP status code (a number from 100 to 599)' % part)
            codes.append(int(part))
        return tuple(codes)
    try:
        value = int(text) if kind == 'int' or re.fullmatch(r'[+-]?\d+', text) else float(text)
    except ValueError:
        raise ValueError('%r is not %s' % (text, 'a whole number' if kind == 'int' else 'a number'))
    if value != value or value in (float('inf'), float('-inf')):
        raise ValueError('%r is not a usable number' % text)
    if value < minimum:
        raise ValueError('must be at least %s' % minimum)
    return value


def make_config_parser():
    # no % interpolation and no comments after a value, so titles and globs can hold % and # as they are
    return configparser.ConfigParser(interpolation=None, delimiters=('=',), comment_prefixes=('#', ';'),
                                     inline_comment_prefixes=None, empty_lines_in_values=False)


def read_user_config(path=None):
    """The config file as a ConfigParser, or None if there is no such file. Raises ConfigError if it cannot be read."""
    path = path or user_config_path()
    if not os.path.exists(path):
        return None
    parser = make_config_parser()
    try:
        with open(path, encoding='utf-8-sig') as reader:   # utf-8-sig: Notepad may have put a BOM in front
            parser.read_file(reader, source=path)
    except (OSError, UnicodeDecodeError, configparser.Error) as e:
        raise ConfigError('config file %s cannot be read: %s' % (path, e))
    return parser


def load_settings(parser, path=None):
    """(values, problems): the value of every setting (built-in default unless the file gives one) and a list of
    messages for entries that were ignored. Raises ConfigError for an entry whose value cannot be used."""
    path = path or user_config_path()
    values = dict((s[0], s[2]) for s in SETTINGS)
    problems = []
    if parser is not None and parser.has_section('settings'):
        for key, text in parser.items('settings'):
            if key not in SETTING_KEYS:
                problems.append("config file %s: [settings] has no setting '%s', ignored" % (path, key))
            elif text.strip():          # an empty value means: use the built-in default
                try:
                    values[key] = parse_setting(key, text)
                except ValueError as e:
                    raise ConfigError('config file %s: [settings] %s = %s: %s' % (path, key, text.strip(), e))
    return values, problems


try:
    SETTING_VALUES, CONFIG_PROBLEMS = load_settings(read_user_config())
except ConfigError as _config_error:
    sys.stderr.write('error: %s\n' % _config_error)
    sys.exit(1)

# lib mods
# configure logging
LOG_MAX_MB = SETTING_VALUES['log_max_mb']
LOG_BACKUPS = SETTING_VALUES['log_backups']
logFormatter = logging.Formatter("%(asctime)s | %(message)s", datefmt='%H:%M:%S')
fileLogFormatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", datefmt='%Y-%m-%d %H:%M:%S')
rootLogger = logging.getLogger('gogrepoc')
rootLogger.setLevel(logging.DEBUG)
# Refactoring (fix): when output goes to a file or pipe (a scheduled task, "> log.txt"), Windows uses its legacy code
# page (e.g. cp1252), which cannot hold Chinese, Japanese, ... game titles. Every such log line then failed with a
# "Logging error" traceback and was lost, and print() crashed the program. Characters the output encoding cannot
# represent are now written as \uXXXX escapes instead; the log file (always UTF-8) keeps the real characters.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors='backslashreplace')
    except (AttributeError, ValueError, OSError):
        pass   # no text stream that can be reconfigured (e.g. pythonw without a console, or replaced by a test runner)

consoleHandler = logging.StreamHandler(sys.stdout)
loggingHandler = logging.handlers.RotatingFileHandler('gogrepo.log', mode='a+', maxBytes = 1024*1024*LOG_MAX_MB , backupCount = LOG_BACKUPS,  encoding='utf-8', delay=True)
loggingHandler.setFormatter(fileLogFormatter)
consoleHandler.setFormatter(logFormatter)
rootLogger.addHandler(consoleHandler)

# logging aliases
info = rootLogger.info
warn = rootLogger.warning
debug = rootLogger.debug
error = rootLogger.error
log_exception = rootLogger.exception

for _problem in CONFIG_PROBLEMS:
    warn(_problem)

# Repetitive, per-file conditions are logged at DEBUG as they happen and reported
# once, combined, at the end of the run (see note_summarised / flush_summarised).
SUMMARY_MAX_ITEMS = SETTING_VALUES['summary_max_items']
NO_MD5_MESSAGE = ("No MD5 data was available for {count} file(s), so they can only be checked by file size: {items}. "
                  "This is normal for some GOG files (many patches and extras have no MD5). Use -debug for per-file details.")
_summarised = {}
_summarised_lock = threading.Lock()

def note_summarised(key, item, message):
    """Remember that `item` hit the condition `key`. `message` is a format string
    with {count} (and {items} when item names are listed) used for the final summary."""
    debug('%s: %s', key, item)
    with _summarised_lock:
        entry = _summarised.setdefault(key, {'message': message, 'items': []})
        if item not in entry['items']:
            entry['items'].append(item)

def flush_summarised():
    """Emit one combined warning per condition, then forget them."""
    with _summarised_lock:
        pending = list(_summarised.values())
        _summarised.clear()
    for entry in pending:
        items = entry['items']
        shown = items[:SUMMARY_MAX_ITEMS]
        listing = ', '.join(shown)
        if len(items) > len(shown):
            listing += ' ... and %d more' % (len(items) - len(shown))
        warn(entry['message'].format(count=len(items), items=listing))

atexit.register(flush_summarised)  # safety net for early exits, Ctrl-C and other commands


class RunReport(object):
    """What a command did, for the summary at the end of the run and for the exit status.

    Commands record counts (files downloaded, ...) and failures (a file that could not be downloaded, a game that could
    not be fetched, a file that failed verification, ...). main() logs the summary and exits with status 1 if there were
    failures, so scheduled tasks and scripts can tell that something went wrong."""
    MAX_LISTED_FAILURES = SETTING_VALUES['max_listed_failures']

    def __init__(self):
        self.reset()

    def reset(self, command=None):
        self.command = command
        self.counts = {}        # label -> [amount, bytes]
        self.failures = []      # (what, why)

    def count(self, label, amount=1, size=None):
        entry = self.counts.setdefault(label, [0, 0])
        entry[0] += amount
        if size:
            entry[1] += size

    def fail(self, what, why=''):
        self.failures.append((what, why))

    def exit_status(self):
        return 1 if self.failures else 0

    @staticmethod
    def _folder_of(what):
        parts = re.split(r'[\\/]', what, maxsplit=1)
        return parts[0] if len(parts) == 2 else None

    def _all_in_folders(self):
        return all(self._folder_of(what) for what, _why in self.failures)

    def _log_grouped_failures(self):
        """Over the cap, one line per reason ('missing: 99 files in 14 games') and the games with their counts in a wrapped paragraph,
        instead of 40 file names and 'and 59 more'. Refactoring: the same 99 files were already listed once per file by the command."""
        groups = {}                                   # why -> {folder: number of files}, in order of first appearance
        for what, why in self.failures:
            folder = groups.setdefault(why or '(no reason given)', {})
            folder[self._folder_of(what)] = folder.get(self._folder_of(what), 0) + 1
        for why, folders in groups.items():
            error('      %s: %d file%s in %d game%s' % (why, sum(folders.values()), '' if sum(folders.values()) == 1 else 's',
                                                        len(folders), '' if len(folders) == 1 else 's'))
            names = ['%s (%d)' % (name, count) for name, count in list(folders.items())[:self.MAX_LISTED_FAILURES]]
            for line in textwrap.wrap(', '.join(names), width=100, initial_indent='         ', subsequent_indent='         '):
                error(line)
            if len(folders) > self.MAX_LISTED_FAILURES:
                error('         ... and %d more games (see the messages above)' % (len(folders) - self.MAX_LISTED_FAILURES))

    def log(self, interrupted=False):
        if not (self.counts or self.failures or interrupted):
            return
        info('')
        info('-- summary%s%s' % (': ' + self.command if self.command else '', ' (interrupted, only what was done so far)' if interrupted else ''))
        width = max([len(label) for label in self.counts] + [0])
        for label, (amount, size) in self.counts.items():
            info('   %-*s %d%s' % (width + 1, label + ':', amount, ' (%s)' % pretty_size(size) if size else ''))
        if self.failures:
            error('   FAILED: %d' % len(self.failures))
            if len(self.failures) > self.MAX_LISTED_FAILURES and self._all_in_folders():
                self._log_grouped_failures()
            else:
                for what, why in self.failures[:self.MAX_LISTED_FAILURES]:
                    error('      %s%s' % (what, ': ' + why if why else ''))
                if len(self.failures) > self.MAX_LISTED_FAILURES:
                    error('      ... and %d more (see the messages above)' % (len(self.failures) - self.MAX_LISTED_FAILURES))
        elif not interrupted:
            info('   no failures')


run_report = RunReport()

# filepath constants
GAME_STORAGE_DIR = r'.'
TOKEN_FILENAME = r'gog-token.json'
LEGACY_TOKEN_FILENAME = r'gog-token.dat'  # read-only compatibility; never overwrite or delete
MANIFEST_FILENAME = r'gog-manifest.dat'
RESUME_MANIFEST_FILENAME = r'gog-resume-manifest.dat'
TEMP_EXT = r'.tmp'
BACKUP_EXT = r'.bak'
CONFIG_FILENAME = r'gog-config.dat'
SERIAL_FILENAME = r'!serial.txt'
INFO_FILENAME = r'!info.txt'


#github API URLs
REPO_HOME_URL = "https://api.github.com/repos/MarS301/gogrepo_delta"   # for update_self (not connected to any command, see the known issues in CHANGELOG.md)
NEW_RELEASE_URL = "/releases/latest"

# GOG URLs
GOG_HOME_URL = r'https://www.gog.com'
GOG_ACCOUNT_URL = r'https://www.gog.com/account'
GOG_LOGIN_URL = r'https://login.gog.com/login_check'
GOG_API_URL = r'https://api.gog.com'

#GOG Galaxy URLs
GOG_AUTH_URL = r'https://auth.gog.com/auth'
GOG_TOKEN_URL = r'https://auth.gog.com/token'
GOG_EMBED_URL = r'https://embed.gog.com'
GOG_GALAXY_REDIRECT_URL = GOG_EMBED_URL + r'/on_login_success'
GOG_CLIENT_ID = '46899977096215655'
GOG_SECRET = '9d85c43b1482497dbbce61f6e4aa173a433796eeae2ca8c5f6129f2dc4de46d9'


# GOG Constants
GOG_MEDIA_TYPE_GAME  = '1'
GOG_MEDIA_TYPE_MOVIE = '2'

# HTTP request settings
HTTP_FETCH_DELAY = 1   # in seconds
HTTP_RETRY_DELAY = SETTING_VALUES['http_retry_delay']   # in seconds #If you reduce this such that the wait between the first and third try is less than 10 seconds, you're gonna have a bad time with the 503 error.
HTTP_RETRY_COUNT = SETTING_VALUES['http_retry_count']
HTTP_TIMEOUT = SETTING_VALUES['http_timeout']
# Refactoring (CPU): size of the pieces a download is read in. It used to be 4 KB, which meant ~1500 loop
# iterations (and, before the watchdog change, ~1500 new threads) per second at 6 MB/s. A download must deliver
# one piece within HTTP_TIMEOUT seconds, so this also sets the slowest usable connection (64 KB / 60 s = ~1.1 KB/s).
DOWNLOAD_CHUNK_SIZE = SETTING_VALUES['download_chunk_size']

HTTP_GAME_DOWNLOADER_THREADS = SETTING_VALUES['download_threads']
DOWNLOAD_PROGRESS_INTERVAL = SETTING_VALUES['progress_interval']   # seconds between two progress lines
HTTP_PERM_ERRORCODES = SETTING_VALUES['http_no_retry_codes'] #503 was in here GOG uses it as a request to wait for a bit when it's under stress. The time out appears to be ~10 seconds in such cases.
USER_AGENT = 'GOGRepoDelta/' + str(__version__)

# Language table that maps two letter language to their unicode gogapi json name
LANG_TABLE = {'en': 'English',   # English
              'bl': '\u0431\u044a\u043b\u0433\u0430\u0440\u0441\u043a\u0438',  # Bulgarian
              'ru': '\u0440\u0443\u0441\u0441\u043a\u0438\u0439',              # Russian
              'gk': '\u0395\u03bb\u03bb\u03b7\u03bd\u03b9\u03ba\u03ac',        # Greek
              'sb': '\u0421\u0440\u043f\u0441\u043a\u0430',                    # Serbian
              'ar': '\u0627\u0644\u0639\u0631\u0628\u064a\u0629',              # Arabic
              'br': 'Portugu\xeas do Brasil',  # Brazilian Portuguese
              'jp': '\u65e5\u672c\u8a9e',      # Japanese
              'ko': '\ud55c\uad6d\uc5b4',      # Korean
              'fr': 'fran\xe7ais',             # French
              #'cn': '\u4e2d\u6587',            # Chinese
              'cz': '\u010desk\xfd',           # Czech
              'hu': 'magyar',                  # Hungarian
              'pt': 'portugu\xeas',            # Portuguese
              'tr': 'T\xfcrk\xe7e',            # Turkish
              'sk': 'slovensk\xfd',            # Slovak
              'nl': 'nederlands',              # Dutch
              'ro': 'rom\xe2n\u0103',          # Romanian
              'es': 'espa\xf1ol',      # Spanish
              'pl': 'polski',          # Polish
              'it': 'italiano',        # Italian
              'de': 'Deutsch',         # German
              'da': 'Dansk',           # Danish
              'sv': 'svenska',         # Swedish
              'fi': 'suomi',           # Finnish
              'no': 'norsk',           # Norsk
              'cn': '\u4e2d\u6587(\u7b80\u4f53)', #Chinese (Simplified)
              'zh': '\u4e2d\u6587(\u7e41\u9ad4)', #Chinese (Traditional)
              'cno' : '\u4e2d\u6587',            # Chinese (Original before Simplified/Traditional Split )
              'es_mx' : 'Espa\u00f1ol (AL)',  # Spanish (Latin American)
              'th': '\u0e44\u0e17\u0e22', #Thai
              'uk': 'y\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u0430', #Ukranian
              'he': '\u05e2\u05d1\u05e8\u05d9\u05ea' #Hebrew

              }

VALID_OS_TYPES = ['windows', 'linux', 'mac']
VALID_LANG_TYPES = list(LANG_TABLE.keys())

lineSep = "\n"


DEFAULT_FALLBACK_LANG = 'en'

# ---------------------------------------------------------------------------------------------
# Default operating system and language
#
# Refactoring: used when neither -os/-lang nor -skipos/-skiplang is given, by every command that filters by
# operating system and language (update, download, verify, import, backup). Before, only "update" used this
# computer's OS and locale (detected by taking the first two letters of locale.getlocale(), which is often empty
# on Windows) and all other commands used every operating system and every language.
# Detection never fails: if it cannot find a usable value it falls back to FALLBACK_OS / DEFAULT_FALLBACK_LANG.
# ---------------------------------------------------------------------------------------------
FALLBACK_OS = 'windows'

if platform.system().lower() == "java":
    error("Jython is not currently supported. Let me know if you want Jython support.")
    sys.exit(1)

# Language codes of locale names (ISO 639-1) -> GOG's own codes. Codes that are the same in both are listed too.
_ISO_TO_GOG_LANG = {'en': 'en', 'de': 'de', 'fr': 'fr', 'es': 'es', 'it': 'it', 'pl': 'pl', 'ru': 'ru', 'cs': 'cz', 'hu': 'hu',
                    'nl': 'nl', 'sv': 'sv', 'da': 'da', 'fi': 'fi', 'no': 'no', 'nb': 'no', 'nn': 'no', 'tr': 'tr', 'ja': 'jp',
                    'ko': 'ko', 'sk': 'sk', 'ro': 'ro', 'bg': 'bl', 'el': 'gk', 'sr': 'sb', 'ar': 'ar', 'th': 'th', 'uk': 'uk',
                    'he': 'he', 'pt': 'pt', 'zh': 'cn'}
# The same for the English language names Windows uses in locale names ("German_Germany")
_WINDOWS_LANG_NAMES = {'english': 'en', 'german': 'de', 'french': 'fr', 'spanish': 'es', 'italian': 'it', 'polish': 'pl',
                       'russian': 'ru', 'czech': 'cz', 'hungarian': 'hu', 'dutch': 'nl', 'swedish': 'sv', 'danish': 'da',
                       'finnish': 'fi', 'norwegian': 'no', 'turkish': 'tr', 'japanese': 'jp', 'korean': 'ko', 'slovak': 'sk',
                       'romanian': 'ro', 'bulgarian': 'bl', 'greek': 'gk', 'serbian': 'sb', 'arabic': 'ar', 'thai': 'th',
                       'ukrainian': 'uk', 'hebrew': 'he', 'portuguese': 'pt', 'chinese': 'cn'}
_TRADITIONAL_CHINESE_MARKERS = ('tw', 'hk', 'mo', 'hant', 'taiwan', 'hong kong', 'macao', 'macau', 'traditional')

def gog_language_from_locale_name(name):
    """GOG language code for a locale name such as 'de_DE.UTF-8', 'pt_BR', 'zh_TW' or 'German_Germany'; None if unknown."""
    if not isinstance(name, str):
        return None
    base = name.strip().split('.')[0].split('@')[0]
    if not base or base.upper() in ('C', 'POSIX'):
        return None
    parts = re.split(r'[_-]', base, maxsplit=1)
    lang = parts[0].strip().lower()
    region = parts[1].strip().lower() if len(parts) > 1 else ''
    if lang in ('zh', 'chinese') or lang.startswith('chinese'):
        traditional = any(marker in region or marker in lang for marker in _TRADITIONAL_CHINESE_MARKERS)
        code = 'zh' if traditional else 'cn'
    elif lang in ('pt', 'portuguese'):
        code = 'br' if (region.startswith('br') or 'brazil' in region) else 'pt'
    else:
        code = _ISO_TO_GOG_LANG.get(lang) or _WINDOWS_LANG_NAMES.get(lang)
    return code if code in VALID_LANG_TYPES else None

def detect_os(system_name=None):
    """Return (os, source): the GOG name of this computer's operating system ('windows', 'linux' or 'mac') and
    'detected', or (FALLBACK_OS, 'fallback') if platform.system() fails or names something else."""
    try:
        name = (platform.system() if system_name is None else system_name).strip().lower()
        if name == 'darwin':
            return 'mac', 'detected'
        if name in VALID_OS_TYPES:
            return name, 'detected'
    except Exception:
        pass
    return FALLBACK_OS, 'fallback'

def _windows_ui_locale_name():
    """Windows only: locale name of the display language, e.g. 'de_DE'. locale.getlocale() usually has no value on Windows."""
    if platform.system() != 'Windows':
        return None
    return locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage())

def _default_locale_name():
    """locale.getdefaultlocale(), which is deprecated (and removed in Python 3.15), so it is only a last resort."""
    getdefaultlocale = getattr(locale, 'getdefaultlocale', None)
    if getdefaultlocale is None:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return getdefaultlocale()[0]

def detect_lang():
    """Return (language, source): the GOG language code of the user's locale and where it came from, or
    (DEFAULT_FALLBACK_LANG, 'fallback') if no source gives a language GOG offers."""
    sources = (('system locale', lambda: locale.getlocale()[0]),
               ('Windows display language', _windows_ui_locale_name),
               ('default locale', _default_locale_name))
    for label, get_name in sources:
        try:
            code = gog_language_from_locale_name(get_name())
        except Exception:
            code = None
        if code in VALID_LANG_TYPES:
            return code, label
    return DEFAULT_FALLBACK_LANG, 'fallback'

def filter_languages(entries, valid_langs, fallback_lang=None):
    """Entries (objects with .lang and .os_type) that are in one of valid_langs.

    With fallback_lang (a GOG language name such as 'English'), every operating system for which `entries` has
    none of the wanted languages gets its fallback_lang entries instead. So a game that only has an English
    Linux installer still gives you that installer when you asked for German, while a game that has a German
    installer gives you only the German one. Used for the default language; an explicit -lang stays strict."""
    if not fallback_lang:
        return [entry for entry in entries if entry.lang in valid_langs]
    covered = set(entry.os_type for entry in entries if entry.lang in valid_langs)
    return [entry for entry in entries
            if entry.lang in valid_langs or (entry.lang == fallback_lang and entry.os_type not in covered)]

def apply_os_lang_defaults(args):
    """Fill in args.os and args.lang for the commands that filter by operating system and language.

    -os / -lang given: used as they are. Only -skipos / -skiplang given: every os / language except those.
    Neither: this computer's operating system and the user's language (windows / en if they cannot be detected).
    Refactoring: replaces five copies of this logic in main() that disagreed about the default."""
    if not args.os:
        if args.skipos:
            args.os = [x for x in VALID_OS_TYPES if x not in args.skipos]
        else:
            os_name, source = detect_os()
            args.os = [os_name]
            info("no -os given, using %s (%s). Use -os to choose, e.g. -os windows linux mac" %
                 (os_name, "the operating system of this computer" if source == 'detected' else "fallback, the operating system could not be detected"))
    args.lang_fallback = None   # a language to use for games/systems that have none of the wanted languages
    if not args.lang:
        if args.skiplang:
            args.lang = [x for x in VALID_LANG_TYPES if x not in args.skiplang]
        else:
            lang, source = detect_lang()
            args.lang = [lang]
            if lang != DEFAULT_FALLBACK_LANG:
                args.lang_fallback = DEFAULT_FALLBACK_LANG
            info("no -lang given, using %s (%s)%s. Use -lang to choose, e.g. -lang en de" %
                 (lang, ("from your system: " + source) if source != 'fallback' else "fallback, the system language could not be detected",
                  ", with %s for games that have no version in that language" % LANG_TABLE[DEFAULT_FALLBACK_LANG] if args.lang_fallback else ""))


# These file types don't have md5 data from GOG
SKIP_MD5_FILE_EXT = ['.txt','.zip','.jpg','.pdf','.png','.rar','.mp4'] #Removed tar.gz as it can have md5s and is actually parsed as .gz so wasn't working, Removed '' as some data files do now have MD5s and this is a wortwhile tradeoff, Left .zip despite a very small number having MD5s as most don't and we verify zip correctness anyway
for i in range(1,21):
    n = i
    a = "." + "%03d"%n
    SKIP_MD5_FILE_EXT.append(a)

INSTALLERS_EXT = ['.exe','.bin','.dmg','.pkg','.sh']

MD5_DIR_NAME = '!md5_xmls'
ORPHAN_DIR_NAME = '!orphaned'
DOWNLOADING_DIR_NAME = '!downloading'
PROVISIONAL_DIR_NAME = '!provisional'
IMAGES_DIR_NAME = '!images'

ORPHAN_DIR_EXCLUDE_LIST = [ORPHAN_DIR_NAME,DOWNLOADING_DIR_NAME,IMAGES_DIR_NAME, MD5_DIR_NAME, '!misc', ]
ORPHAN_FILE_EXCLUDE_LIST = [INFO_FILENAME, SERIAL_FILENAME]
RESUME_SAVE_THRESHOLD = SETTING_VALUES['resume_save_threshold']

MANIFEST_SYNTAX_VERSION = 1
RESUME_MANIFEST_SYNTAX_VERSION = 1

token_lock = threading.RLock()
MISSING_FILES_LISTED = 3     # verify names up to this many missing files per game; more are reported as one line per game

class AuthExpired(SystemExit):
    """The token cannot be renewed: the user has to log in again.
    It is a SystemExit (exit status 1) on purpose: in the main thread it ends the program exactly like the sys.exit(1) it replaces, and no
    'except Exception' in between can swallow it. A download worker thread catches it explicitly (see _download_worker); before, the
    SystemExit silently ended that thread only and the run reported 'a download thread stopped unexpectedly'."""
    def __init__(self):
        SystemExit.__init__(self, 1)

WINDOWS_PREALLOCATION_FS = ["NTFS","exFAT","FAT32"]
POSIX_PREALLOCATION_FS = ["exfat","vfat","ntfs","btrfs", "ext4", "ocfs2", "xfs"] #May need to exempt NTFS because of reported hangs on remote drives, but should check if that's because of NFS or similar first



#request wrapper
def request(session,url,args=None,byte_range=None,retries=HTTP_RETRY_COUNT,delay=None,stream=False,data=None,quiet_statuses=(),no_retry_statuses=()):
    """Performs web request to url with optional retries, delay, and byte range.
    """
    _retry = False
    if delay is not None:
        time.sleep(delay)

    renew_token(session)

    try:
        if data is not None:
            if byte_range is not None:
                response = session.post(url, params=args, headers= {'Range':'bytes=%d-%d' % byte_range},timeout=HTTP_TIMEOUT,stream=stream,data=data)
            else:
                response = session.post(url, params=args,stream=stream,timeout=HTTP_TIMEOUT,data=data)
        else:
            if byte_range is not None:
                response = session.get(url, params=args, headers= {'Range':'bytes=%d-%d' % byte_range},timeout=HTTP_TIMEOUT,stream=stream)
            else:
                response = session.get(url, params=args,stream=stream,timeout=HTTP_TIMEOUT)
        response.raise_for_status()
    except (requests.HTTPError, requests.URLRequired, requests.Timeout,requests.ConnectionError,requests.exceptions.SSLError) as e:
        if isinstance(e, requests.HTTPError):
            if e.response.status_code in HTTP_PERM_ERRORCODES or e.response.status_code in no_retry_statuses:  # do not retry these HTTP codes (no_retry_statuses: only for this call)
                if e.response.status_code in quiet_statuses:  # caller handles (and reports) this status itself
                    debug('request failed: %s.  will not retry.', e)
                else:
                    warn('request failed: %s.  will not retry.', e)
                raise
        if retries > 0:
            _retry = True
        else:
            raise

        if _retry:
            warn('request failed: %s (%d retries left) -- will retry in %ds...' % (e, retries, HTTP_RETRY_DELAY))
            return request(session=session,url=url, args=args, byte_range=byte_range, retries=retries-1, delay=HTTP_RETRY_DELAY,stream=stream,data=data,quiet_statuses=quiet_statuses,no_retry_statuses=no_retry_statuses)
    return response

#Request Head weapper
def request_head(session,url,args=None,retries=HTTP_RETRY_COUNT,delay=None,allow_redirects=True):
    """Performs web head request to url with optional retries, delay,allow_redirects
    """
    _retry = False
    if delay is not None:
        time.sleep(delay)

    renew_token(session)

    try:
        response = session.head(url, params=args,timeout=HTTP_TIMEOUT, allow_redirects=allow_redirects)
        response.raise_for_status()
    except (requests.HTTPError, requests.URLRequired, requests.Timeout,requests.ConnectionError,requests.exceptions.SSLError) as e:
        if isinstance(e, requests.HTTPError):
            if e.response.status_code in HTTP_PERM_ERRORCODES:  # do not retry these HTTP codes
                warn('request failed: %s.  will not retry.', e)
                raise
        if retries > 0:
            _retry = True
        else:
            raise

        if _retry:
            warn('request failed: %s (%d retries left) -- will retry in %ds...' % (e, retries, HTTP_RETRY_DELAY))
            return request_head(session=session,url=url, args=args, retries=retries-1, delay=HTTP_RETRY_DELAY)
    return response



def renew_token(session,retries=HTTP_RETRY_COUNT,delay=None):
    with token_lock:
        _retry = False
        if delay is not None:
            time.sleep(delay)

        time_now = time.time()
        try:
            if time_now + 300 > session.token['expiry']:
                info('refreshing token')
                try:
                    token_response = session.get(GOG_TOKEN_URL,params={'client_id':GOG_CLIENT_ID ,'client_secret':GOG_SECRET, 'grant_type': 'refresh_token','refresh_token': session.token['refresh_token']},timeout=HTTP_TIMEOUT)
                    token_response.raise_for_status()
                except Exception as e:
                        if retries > 0:
                            _retry = True
                        else:
                            error(e)
                            error('Could not renew token, Please login again.')
                            raise AuthExpired()
                        if _retry:
                            warn('token refresh failed: %s (%d retries left) -- will retry in %ds...' % (e, retries, HTTP_RETRY_DELAY))
                            return renew_token(session=session, retries=retries-1, delay=HTTP_RETRY_DELAY)
                token_json = token_response.json()
                for item in token_json:
                    session.token[item] = token_json[item]
                session.token['expiry'] = time_now + token_json['expires_in']
                save_token(session.token)
                session.headers['Authorization'] = "Bearer " + session.token['access_token']
                info('refreshed token')
        except AttributeError:
            #Not a Token based session
            pass


# --------------------------
# Helper types and functions
# --------------------------
def _multi_zip_parts(item_name, item_file):
    """Names (no folder) of the files next to item_file that share the base name of item_name, like 'x.zip.001', 'x.zip.002'.
    Refactoring: replaces glob.glob(..., root_dir=...), which exists only from Python 3.10 (TypeError on 3.8 / 3.9)."""
    pattern = os.path.join(glob.escape(os.path.dirname(item_file)), os.path.splitext(item_name)[0] + ".*")
    return [os.path.basename(found) for found in glob.glob(pattern)]

def get_fs_type(path,isWindows=False):
    path = os.path.realpath(path) #We need the real location for this
    partition = {}
    for part in psutil.disk_partitions(all=True):
        partition[part.mountpoint] = part.fstype
    if path in partition:
        return partition[path]
    splitpath = path.split(os.sep)
    for i in range(len(splitpath),0,-1):
        if isWindows:
            path = os.sep.join(splitpath[:i]) + os.sep
            if path in partition:
                return partition[path]
        else:
            path = os.sep.join(splitpath[:i])
            if path in partition:
                return partition[path]
    if not isWindows and os.sep in partition:
        # Refactoring: the loop above stops before it joins zero parts, so the root mount '/' was never tried and every folder on the
        # root file system was reported as "unknown" (no preallocation, e.g. in a container or on a one-partition install).
        return partition[os.sep]
    return "unknown"

class AttrDict(dict):
    def __init__(self, **kw):
        self.update(kw)

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, val):
        self[key] = val

class ConditionalWriter(object):
    """File writer that only updates file on disk if contents chanaged"""

    def __init__(self, filename):
        self._buffer = None
        self._filename = filename

    def __enter__(self):
        self._buffer = tmp = StringIO()
        return tmp

    def __exit__(self, _exc_type, _exc_value, _traceback):
        if _exc_type is not None:
            return False        # Refactoring: the body failed, so the buffer is incomplete; never put it on disk (the exception goes on)
        tmp = self._buffer
        if tmp:
            tmp.seek(0)

            file_changed = not os.path.exists(self._filename)
            if not file_changed:
                with open(self._filename, mode='r', encoding='utf-8') as orig: #Universal newlines are not used here because we need to be aware of the actual line ends
                    for (new_chunk, old_chunk) in zip_longest(tmp, orig):
                        if new_chunk != old_chunk:
                            file_changed = True
                            break

            if file_changed:
                if os.path.exists(self._filename):
                    # Refactoring: an existing file is replaced atomically (and keeps its permissions), so a crash cannot leave it truncated
                    def write_buffer(w):
                        tmp.seek(0)
                        shutil.copyfileobj(tmp, w)
                    try:
                        atomic_write_text(self._filename, write_buffer)
                        return
                    except OSError:
                        pass        # for example a read-only folder with a writable file: write in place, as before
                with open(self._filename, mode='w', encoding='utf-8') as overwrite:
                    tmp.seek(0)
                    shutil.copyfileobj(tmp, overwrite)

def slugify(value, allow_unicode=False):
    '''
    The below block comment applies to this function in it's entirety (including the header except for the BSD License text itself and this comment )
    '''
    '''
    Copyright (c) Django Software Foundation and individual contributors.
    All rights reserved.

    Redistribution and use in source and binary forms, with or without modification,
    are permitted provided that the following conditions are met:

        1. Redistributions of source code must retain the above copyright notice,
           this list of conditions and the following disclaimer.

        2. Redistributions in binary form must reproduce the above copyright
           notice, this list of conditions and the following disclaimer in the
           documentation and/or other materials provided with the distribution.

        3. Neither the name of Django nor the names of its contributors may be used
           to endorse or promote products derived from this software without
           specific prior written permission.

    THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
    ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
    WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
    DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
    ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
    (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
    LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
    ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
    (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
    SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
    '''
    """
    Convert to ASCII if 'allow_unicode' is False. Convert spaces or repeated
    dashes to single dashes. Remove characters that aren't alphanumerics,
    underscores, or hyphens. Convert to lowercase. Also strip leading and
    trailing whitespace, dashes, and underscores.
    """
    value = str(value)
    if allow_unicode:
        value = unicodedata.normalize("NFKC", value)
    else:
        value = (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
    value = re.sub(r"[^\w\s-]", "", value.lower())
    return re.sub(r"[-\s]+", "-", value).strip("-_")


def path_preserving_split_ext(path):
    # Refactoring (fix): os.path.splitext returns an empty extension for names without one
    # (the old rsplit code raised IndexError, e.g. when moving an orphaned "README" onto an
    # existing "README") and does not treat a leading dot as an extension (".hidden" used to
    # become "(1).hidden" on a clash, now ".hidden(1)"). Results are unchanged for "name.ext".
    root, extension = os.path.splitext(os.path.basename(path))
    return [os.path.join(os.path.dirname(path), root), extension]

def move_with_increment_on_clash(src,dst,count=0):
    if (count == 0):
        potDst = dst
    else:
        if os.path.isdir(dst):
            potDst =  dst + "(" +str(count) + ")"
        else:
            root,ext = path_preserving_split_ext(dst)
            potDst = numbered_name(root, ext, count)
        warn('Unresolved destination clash for "{}" detected. Trying "{}"'.format(dst,potDst))
    if (not os.path.exists(potDst)) or (os.path.isdir(potDst)):
        shutil.move(src,potDst)
    else:
        move_with_increment_on_clash(src,dst,count+1)

def _attrdict_tree(value):
    """Recursively restore AttrDict access for data loaded from a literal structure."""
    if isinstance(value, dict):
        result = AttrDict()
        for key, item in value.items():
            result[key] = _attrdict_tree(item)
        return result
    if isinstance(value, list):
        return [_attrdict_tree(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_attrdict_tree(item) for item in value)
    return value


def _load_legacy_literal(text):
    """Safely load historical pprint/AttrDict data without executing Python code."""
    # Remove only the known AttrDict(**{...}) wrapper tokens. A plain text replacement of
    # the closing ``})`` would corrupt legitimate string values containing those characters.
    tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    remove = set()
    for i in range(len(tokens) - 3):
        if (tokens[i].type == tokenize.NAME and tokens[i].string == 'AttrDict'
                and tokens[i + 1].string == '(' and tokens[i + 2].string == '**'
                and tokens[i + 3].string == '{'):
            depth = 0
            for j in range(i + 3, len(tokens)):
                if tokens[j].type == tokenize.OP and tokens[j].string == '{':
                    depth += 1
                elif tokens[j].type == tokenize.OP and tokens[j].string == '}':
                    depth -= 1
                    if depth == 0:
                        if j + 1 < len(tokens) and tokens[j + 1].string == ')':
                            remove.update((i, i + 1, i + 2, j + 1))
                        break
    literal_text = tokenize.untokenize([token for i, token in enumerate(tokens) if i not in remove])
    return _attrdict_tree(ast.literal_eval(literal_text))


def parse_manifest_text(ad, filepath, save_repair=True):
    """Items from the text of a manifest file (JSON or old format). Raises ManifestDamaged if it cannot be read."""
    json_items = manifest_from_json(ad)
    if json_items is not None:
        return json_items

    compiledregexclose = re.compile(r"'changelog':.*?(?:'downloads':|'changelog_end':)|'Report-To':.*?'Server':|'report-to':.*?'server':|(})",re.DOTALL)
    compiledregexopen =  re.compile(r"'changelog':.*?(?:'downloads':|'changelog_end':)|'Report-To':.*?'Server':|'report-to':.*?'server':|({)",re.DOTALL)
    #compiledregexmungeopen = re.compile(r"((?:AttrDict\(**)+{")
    #compiledregexmungeclose = re.compile(r"}\)+")
    compiledregexmunge = re.compile(r"((?:AttrDict\(\*\*)+{)(.*?)(}\)+)")

    def myreplacementopen(m):
        if m.group(1):
           return "AttrDict(**{"
        else:
           return m.group(0)
    def myreplacementclose(m):
        if m.group(1):
            return "})"
        else:
            return m.group(0)
    def mungereplacement(m):
        return "{" + m.group(2) + "}"

    mungeDetected = compiledregexmunge.search(ad)
    if mungeDetected:
        warn("detected AttrDict error in manifest")
        while(compiledregexmunge.search(ad)):
            ad = compiledregexmunge.sub(mungereplacement,ad)
        warn("fixed AttrDict in manifest. If this occurs more than once please report it to the maintainer.")

    ad =  compiledregexopen.sub(myreplacementopen,ad)
    ad =  compiledregexclose.sub(myreplacementclose,ad)

    ad = re.sub(r"'size': ([0-9]+)L,",r"'size': \1,",ad)
    try:
        db = _load_legacy_literal(ad)
    except Exception as e:
        raise ManifestDamaged("%s: %s" % (type(e).__name__, e))
    if (mungeDetected and save_repair):
        try:
            save_manifest(db,filepath)
        except IOError:
            error("Could not save repaired manifest, aborting")
            raise SystemExit(1)
    return db


def _windows_console_input(fd):
    """True if the file descriptor is a real Windows console (someone can type into it).
    isatty() is not enough on Windows: it also says yes for the NUL device, which is what a scheduled task or
    'command < NUL' gives as input. Only a real console has a console mode."""
    import ctypes, msvcrt
    from ctypes import wintypes
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetConsoleMode.restype = wintypes.BOOL
    mode = wintypes.DWORD()
    return bool(kernel32.GetConsoleMode(msvcrt.get_osfhandle(fd), ctypes.byref(mode)))


def _stdin_is_interactive():
    """True if a person can answer a question on this run's standard input."""
    try:
        if sys.stdin is None or not sys.stdin.isatty():
            return False
        if os.name == 'nt':
            return _windows_console_input(sys.stdin.fileno())
        return True
    except Exception:
        return False


def ask_yes_no(question):
    """Ask on the terminal; the default (just Enter) is no."""
    try:
        answer = input(question + " [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in ('y', 'yes', 'j', 'ja')


def _keep_copy(source, kept):
    """Copy `source` to the file name `kept` (with a time stamp added if that name is taken). Returns the name of the copy."""
    if os.path.exists(kept):
        kept += datetime.datetime.now().strftime('.%Y%m%d-%H%M%S')
    shutil.copyfile(source, kept)
    return kept


def _manual_recovery_instructions(filepath, has_backup):
    """What to do by hand; only shown once the program has stopped (every question was declined, or nobody could be asked)."""
    backup = filepath + BACKUP_EXT
    if has_backup:
        error("To use the backup yourself: copy '%s' over '%s'." % (backup, filepath))
    error("To start from scratch yourself: delete or move '%s'%s, then run 'update' to build a new manifest."
          % (filepath, (" and '%s'" % backup) if has_backup else ""))


def _restore_manifest_from_backup(filepath, backup):
    """Check the backup, keep a damaged manifest as <file>.damaged, copy the backup over the manifest and return its items."""
    try:                                                    # make sure the backup is usable before anything is replaced
        with open(backup, mode='r', encoding='utf-8') as r:
            items = parse_manifest_text(r.read(), filepath, save_repair=False)
    except (OSError, UnicodeDecodeError, ManifestDamaged) as e:
        error("The backup copy is not usable either (%s). Nothing was changed." % e)
        raise SystemExit(1)
    if os.path.exists(filepath):                            # never throw the damaged file away
        info("the damaged file was kept as '%s'" % _keep_copy(filepath, filepath + '.damaged'))
    tmp_path = filepath + TEMP_EXT
    shutil.copyfile(backup, tmp_path)
    _replace_file(tmp_path, filepath)
    info("restored '%s' from '%s'" % (filepath, backup))
    return items


def recover_manifest(filepath, problem):
    """`filepath` is missing or damaged. Say what is wrong, then ask:
    1. if a backup copy exists (<file>.bak, the manifest as it was before the last save): use it?
    2. if not: start a new, empty manifest? (only for 'update', the command that builds the manifest; for any other command an
       empty manifest is useless or dangerous, e.g. 'clean' would treat every game folder as an orphan)
    Returns the items to work with. If both questions are declined, or nobody can be asked (scheduled run), the program stops
    with exit status 1 and only then explains how to restore or start over by hand."""
    backup = filepath + BACKUP_EXT
    has_backup = os.path.exists(backup)
    error("The manifest file '%s' %s." % (filepath, problem))
    if has_backup:
        try:
            stat = os.stat(backup)
            details = " (last changed %s, %s)" % (datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'), pretty_size(stat.st_size))
        except OSError:
            details = ""
        error("A backup copy exists: '%s'%s. It is the manifest as it was before the last save." % (backup, details))
    else:
        error("There is no backup copy ('%s') to fall back on." % backup)
    if not _stdin_is_interactive():
        error("Not asking, because this run is not interactive (run it again in a terminal to be asked).")
        _manual_recovery_instructions(filepath, has_backup)
        raise SystemExit(1)
    if has_backup and ask_yes_no("Use the backup copy '%s' instead?" % backup):
        return _restore_manifest_from_backup(filepath, backup)
    command = run_report.command
    if command not in (None, 'update'):
        error("'%s' needs an existing manifest; only 'update' can build a new one." % command)
        _manual_recovery_instructions(filepath, has_backup)
        raise SystemExit(1)
    warn("A new manifest starts empty, so the next update has to fetch every game again (this takes a while for a large library).")
    if not ask_yes_no("Start a new, empty manifest '%s' instead?" % filepath):
        error("Not starting a new manifest either, stopping.")
        _manual_recovery_instructions(filepath, has_backup)
        raise SystemExit(1)
    if os.path.exists(filepath):                            # never throw anything away
        info("the damaged file was kept as '%s'" % _keep_copy(filepath, filepath + '.damaged'))
    if has_backup:                                          # a later save would overwrite the backup
        info("the old backup was kept as '%s'" % _keep_copy(backup, filepath + '.oldbackup'))
    info("starting a new manifest '%s'" % filepath)
    return []


def load_manifest(filepath=MANIFEST_FILENAME):
    info('loading local manifest...')
    try:
        with open(filepath, mode='r', encoding='utf-8') as r:
            ad = r.read()
    except FileNotFoundError:
        if os.path.exists(filepath + BACKUP_EXT):
            return recover_manifest(filepath, "was not found")
        return []                                           # no manifest and no backup: the first run
    except UnicodeDecodeError as e:
        return recover_manifest(filepath, "is damaged (%s)" % e)
    except OSError as e:                                    # e.g. no permission, or locked by another program
        error("The manifest file '%s' cannot be read (%s). Stopping, so that it is not mistaken for an empty library." % (filepath, e))
        raise SystemExit(1)
    try:
        return parse_manifest_text(ad, filepath)
    except ManifestDamaged as e:
        return recover_manifest(filepath, "is damaged (%s)" % e)


def save_manifest(items,filepath=MANIFEST_FILENAME,update_md5_xml=False,delete_md5_xml=False):
    if update_md5_xml:
        #existing_md5s = []
        all_items_by_title = {}
        # make convenient dict with title/dirname as key
        for item in items:
            try:
                _ = item.folder_name
            except AttributeError:
                item.folder_name = item.title
            all_items_by_title[item.folder_name] = item

        if os.path.isdir(MD5_DIR_NAME):
            info ("Cleaning up " + MD5_DIR_NAME)
            for cur_dir in sorted(os.listdir(MD5_DIR_NAME)):
                cur_fulldir = os.path.join(MD5_DIR_NAME, cur_dir)
                if os.path.isdir(cur_fulldir):
                    if cur_dir not in all_items_by_title:
                        #ToDo: Maybe try to rename ? Content file names will probably change when renamed (and can't be recognised by md5s as partial downloads) so maybe not wortwhile ?
                        info("Removing outdated directory " + cur_fulldir)
                        shutil.rmtree(cur_fulldir)
                    else:
                        # dir is valid game folder, check its files
                        expected_dirnames = []
                        expected_dirnames.append("downloads")
                        expected_dirnames.append("extras")
                        for cur_dir_file in os.listdir(cur_fulldir):
                            if os.path.isdir(os.path.join(MD5_DIR_NAME, cur_dir, cur_dir_file)):
                                if cur_dir_file not in expected_dirnames:
                                    info("Removing incorrect subdirectory " + os.path.join(MD5_DIR_NAME, cur_dir, cur_dir_file))
                                    shutil.rmtree(os.path.join(MD5_DIR_NAME, cur_dir, cur_dir_file))
                                else:
                                    cur_fulldir2 = os.path.join(MD5_DIR_NAME, cur_dir,cur_dir_file)
                                    if cur_dir_file == "downloads":
                                        os_types = []
                                        for game_item in all_items_by_title[cur_dir].downloads:
                                            if game_item.os_type not in os_types:
                                                os_types.append(game_item.os_type)
                                        for cur_dir_file in os.listdir(cur_fulldir2):
                                            if os.path.isdir(os.path.join(cur_fulldir2,cur_dir_file)):
                                                if cur_dir_file not in os_types:
                                                    info("Removing incorrect subdirectory " + os.path.join(cur_fulldir2,cur_dir_file))
                                                    shutil.rmtree(os.path.join(cur_fulldir2, cur_dir_file))
                                                else:
                                                    cur_fulldir3 = os.path.join(cur_fulldir2,cur_dir_file)
                                                    os_game_items = [x for x in all_items_by_title[cur_dir].downloads if x.os_type == cur_dir_file]
                                                    for game_item in os_game_items:
                                                        langs = []
                                                        for game_item in os_game_items:
                                                            if game_item.lang not in langs:
                                                                langs.append(game_item.lang)
                                                    for cur_dir_file in os.listdir(cur_fulldir3):
                                                        if os.path.isdir(os.path.join(cur_fulldir3,cur_dir_file)):
                                                            if cur_dir_file not in langs:
                                                                info("Removing incorrect subdirectory " + os.path.join(cur_fulldir3,cur_dir_file))
                                                                shutil.rmtree(os.path.join(cur_fulldir3, cur_dir_file))
                                                            else:
                                                                cur_fulldir4 = os.path.join(cur_fulldir3,cur_dir_file)
                                                                lang_os_game_items = [x for x in os_game_items if x.lang == cur_dir_file]
                                                                expected_filenames = []
                                                                for game_item in lang_os_game_items:
                                                                    if ( game_item.name is None ):
                                                                        warn("Game item has OS and Lang but no name in game associated with " + cur_fulldir4)
                                                                        if game_item.provisional_name:
                                                                            warn("This was due to a failure to fetch file info: the provisional name of item was: " + game_item.provisional_name + " from " + game_item.manualUrl)
                                                                    if ( game_item.name is not None ):
                                                                        expected_filenames.append(game_item.name + ".xml")
                                                                for cur_dir_file in os.listdir(cur_fulldir4):

                                                                    for cur_dir_file in os.listdir(cur_fulldir4):
                                                                        if os.path.isdir(os.path.join(cur_fulldir4, cur_dir_file)):
                                                                            info("Removing subdirectory(?!) " + os.path.join(cur_fulldir4, cur_dir_file))
                                                                            shutil.rmtree(os.path.join(cur_fulldir4, cur_dir_file)) #There shouldn't be subdirectories here ?? Nuke to keep clean.
                                                                        else:
                                                                            if cur_dir_file not in expected_filenames:
                                                                                info("Removing outdated file " + os.path.join(cur_fulldir4, cur_dir_file))
                                                                                os.remove(os.path.join(cur_fulldir4, cur_dir_file))
                                                        else:
                                                            info("Removing invalid file " + os.path.join(cur_fulldir3, cur_dir_file))
                                                            os.remove(os.path.join(cur_fulldir3, cur_dir_file))
                                            else:
                                                info("Removing invalid file " + os.path.join(cur_fulldir2, cur_dir_file))
                                                os.remove(os.path.join(cur_fulldir2, cur_dir_file))
                                    elif cur_dir_file== "extras":
                                        expected_filenames = []
                                        for extra_item in all_items_by_title[cur_dir].extras:
                                            if (extra_item.name is None):
                                                    if not extra_item.unreleased:
                                                        warn("Extra item that is probably released but has no name in extra associated with " + cur_fulldir2)
                                                        if extra_item.provisional_name:
                                                            warn("This was probably due to a failure to fetch file info: the provisional name of item was: " + extra_item.provisional_name + " from " + extra_item.manualUrl)
                                            if (extra_item.name is not None):
                                                expected_filenames.append(extra_item.name + ".xml")

                                        for cur_dir_file in os.listdir(cur_fulldir2):
                                            if os.path.isdir(os.path.join(cur_fulldir2, cur_dir_file)):
                                                info("Removing subdirectory(?!) " + os.path.join(cur_fulldir2, cur_dir_file))
                                                shutil.rmtree(os.path.join(cur_fulldir2, cur_dir_file)) #There shouldn't be subdirectories here ?? Nuke to keep clean.
                                            else:
                                                if cur_dir_file not in expected_filenames:
                                                    info("Removing outdated file " + os.path.join(cur_fulldir2, cur_dir_file))
                                                    os.remove(os.path.join(cur_fulldir2, cur_dir_file))
                            else:
                                info("Removing invalid file " + os.path.join(MD5_DIR_NAME, cur_dir, cur_dir_file))
                                os.remove(os.path.join(MD5_DIR_NAME,cur_dir, cur_dir_file))

    if update_md5_xml or delete_md5_xml:
        if not os.path.isdir(MD5_DIR_NAME):
            os.makedirs(MD5_DIR_NAME)
        for item in items:
            try:
                _ = item.folder_name
            except Exception:
                item.folder_name = item.title
            info("Handling MD5 XML info for " + item.folder_name)
            fname = os.path.join(MD5_DIR_NAME,item.folder_name)
            if not os.path.isdir(fname):
                os.makedirs(fname)
            for download in item.downloads:
                ffdir = os.path.join(fname,"downloads",download.os_type,download.lang)
                if not os.path.isdir(ffdir):
                    os.makedirs(ffdir)
                if (download.name is None):
                    try:
                        text = download.gog_data.md5_xml.text
                        if text is not None and text != "":
                            warn("Download item with MD5 XML Data but without a filename exists in manifest")
                            if download.provisional_name:
                                warn("It should not be possible to have XML Data without a filename but with a provisional name but since you do, the provisional name of item was: " +  download.provisional_name + " from " + download.manualUrl)
                    except AttributeError:
                        pass
                if (download.name is not None):
                    ffname = os.path.join(ffdir,download.name + ".xml")
                    #rffname = os.path.join(".",ffname)
                    try:
                        text = download.gog_data.md5_xml.text
                        #existing_md5s.append(ffname)
                        if (update_md5_xml):
                            with ConditionalWriter(ffname) as fd_xml:
                                fd_xml.write(text)
                        if (delete_md5_xml):
                            del download.gog_data.md5_xml["text"]
                    except AttributeError:
                        pass
            for extra in item.extras:
                ffdir = os.path.join(fname,'extras')
                if not os.path.isdir(ffdir):
                    os.makedirs(ffdir)
                if (extra.name is None):
                    try:
                        text = extra.gog_data.md5_xml.text
                        if text is not None and text != "":
                            warn("Extra item with MD5 XML Data but without a filename exists in manifest")
                            if extra.provisional_name:
                                warn("It should not be possible to have XML Data without a filename but with a provisional name but since you do, the provisional name of item was: " +  extra.provisional_name + " from " + extra.manualUrl)
                    except AttributeError:
                        pass
                if (extra.name is not None):
                    ffname = os.path.join(ffdir,extra.name + ".xml")
                    #rffname = os.path.join(".",ffname)
                    try:
                        text = extra.gog_data.md5_xml.text
                        #existing_md5s.append(ffname)
                        if (update_md5_xml):
                            with ConditionalWriter(ffname) as fd_xml:
                                fd_xml.write(text)
                        if (delete_md5_xml):
                            del extra.gog_data.md5_xml["text"]
                    except AttributeError:
                        pass

 #all_md5s = glob.glob()   Can't recursive glob before 3.5 so have to do this the hardway

    save_manifest_core(items,filepath)

def _replace_file(src, dst, attempts=SETTING_VALUES['file_replace_attempts'], delay=SETTING_VALUES['file_replace_delay']):
    """os.replace with a short retry; on Windows the destination can be briefly
    locked by a virus scanner or indexer, which raises PermissionError."""
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)

def _fsync_directory(path):
    """Best effort: make the rename itself durable. Not possible on Windows."""
    try:
        fd = os.open(os.path.dirname(os.path.abspath(path)), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)

def atomic_write_text(path, write_fn, backup_path=None, mode=None):
    """Atomically write UTF-8 text using a unique temporary file in the destination directory.

    A unique file avoids following a pre-created ``.tmp`` symlink and avoids collisions between
    unrelated writers. Existing destination permissions are preserved unless an explicit mode
    is supplied. ``mode`` is used for secrets such as the GOG token (0600 on POSIX).
    """
    directory = os.path.dirname(os.path.abspath(path))
    legacy_tmp = path + TEMP_EXT
    try:
        os.remove(legacy_tmp)
    except OSError:
        pass
    fd, tmp_path = tempfile.mkstemp(prefix=os.path.basename(path) + '.', suffix=TEMP_EXT, dir=directory)
    try:
        if mode is not None and os.name != 'nt':
            os.chmod(tmp_path, mode)
        w = os.fdopen(fd, mode='w', encoding='utf-8')
        fd = None                       # the file object owns the descriptor from here on, and closes it
        with w:
            write_fn(w)
            w.flush()
            os.fsync(w.fileno())
        if os.path.exists(path):
            if mode is None:
                try:
                    shutil.copymode(path, tmp_path)
                except OSError:
                    pass
            if backup_path is not None:
                shutil.copyfile(path, backup_path)
        _replace_file(tmp_path, path)
    except BaseException:
        if fd is not None:              # only when no file object took the descriptor over (closing it again would close a
            try:                        # file that another thread opened in the meantime, which got the same number)
                os.close(fd)
            except OSError:
                pass
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    _fsync_directory(path)

# ---------------------------------------------------------------------------------------------
# Manifest file format
#
# Refactoring: the manifest used to be Python text (pprint) that had to be formatted and evaluated again, which took
# seconds on a large library (about 9 s per save and 8 s per load in one real log). It is now written as indented JSON:
# still plain text you can open in any editor (one field per line), but roughly 20x faster to save and 100x faster to
# load. The old format can always be read, and written on request (-manifestformat legacy), e.g. to keep using other
# gogrepo versions. Every JSON save is read back and compared with what was written; if anything would not survive
# exactly (tuples, non-text dict keys, NaN ...) that save uses the old format instead, so no data can be changed by it.
# ---------------------------------------------------------------------------------------------
MANIFEST_FORMAT = 'json'          # 'json' or 'legacy'; set from -manifestformat
MANIFEST_JSON_VERSION = 1
LEGACY_BACKUP_EXT = '.legacy'     # copy of a manifest in the old format, made before the first JSON save over it

def _attrdict_from_json_object(obj):
    """json.loads hook: every JSON object becomes an AttrDict (built with update, so any key name works)."""
    result = AttrDict()
    result.update(obj)
    return result

def manifest_to_json(items, game_count):
    """Text of the manifest as JSON, or None if that would not read back exactly the same."""
    try:
        text = json.dumps({'gogrepoc_manifest': MANIFEST_JSON_VERSION, 'games': game_count, 'items': items},
                          indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stored = json.loads(text, object_hook=_attrdict_from_json_object)['items']
    except (TypeError, ValueError, RecursionError) as e:
        warn("the manifest cannot be stored as JSON (%s), using the old format for this save" % e)
        return None
    if stored != items:
        warn("the manifest would not read back identically from JSON (tuples or non-text keys?), using the old format for this save")
        return None
    return text

class ManifestDamaged(Exception):
    """A manifest file whose content cannot be read."""


def manifest_from_json(text):
    """Items of a manifest in the JSON format; None if `text` is in the old format. Raises ManifestDamaged if the JSON is broken."""
    if text.lstrip()[:1] != '{':          # the JSON format starts with '{', the old one with '#' or '['
        return None
    try:
        data = json.loads(text, object_hook=_attrdict_from_json_object)
        items = data['items']
        if not isinstance(items, list):
            raise ValueError("'items' is not a list")
    except (ValueError, KeyError, TypeError) as e:
        raise ManifestDamaged(str(e))
    return items

def keep_legacy_copy(filepath):
    """Before the first JSON save over a manifest in the old format: keep that file as <file>.legacy, once.
    Returns False if the copy could not be made (then the caller must not switch the format)."""
    legacy_copy = filepath + LEGACY_BACKUP_EXT
    try:
        if os.path.exists(legacy_copy) or not os.path.exists(filepath):
            return True
        with open(filepath, encoding='utf-8') as f:
            first = f.read(64).lstrip()[:1]
        if first in ('#', '['):
            shutil.copyfile(filepath, legacy_copy)
            info("the manifest is now saved in the faster JSON format; the old-format file was kept as %s" % legacy_copy)
    except (OSError, UnicodeDecodeError) as e:
        warn("could not keep a copy of the old-format manifest (%s), not switching to the JSON format" % e)
        return False
    return True

def save_manifest_core_worker(items,filepath,hasManifestPropsItem=False):
    len_adjustment = -1 if hasManifestPropsItem else 0
    game_count = len(items)+len_adjustment
    json_text = manifest_to_json(items, game_count) if MANIFEST_FORMAT == 'json' else None
    if json_text is not None and not keep_legacy_copy(filepath):
        json_text = None
    def write(w):
        if json_text is not None:
            w.write(json_text)
        else:
            print('# {} games'.format(game_count), file=w)
            pprint.pprint(items, width=123, stream=w)
    atomic_write_text(filepath, write, backup_path=filepath+BACKUP_EXT)


def save_manifest_core(items,filepath=MANIFEST_FILENAME):
    info('saving manifest...')
    save_manifest_core_worker(items,filepath)
    info('saved manifest')



def save_resume_manifest(items):
    info('saving resume manifest...')
    save_manifest_core_worker(items,RESUME_MANIFEST_FILENAME,True)
    info('saved resume manifest')

def load_resume_manifest(filepath=RESUME_MANIFEST_FILENAME):
    info('loading local resume manifest...')
    try:
        with open(filepath, mode='r', encoding='utf-8') as r:
            text = r.read()
        try:
            json_items = manifest_from_json(text)
        except ManifestDamaged as e:
            error("%s is damaged (%s). Delete it to continue without resuming, or restore %s." % (filepath, e, filepath + BACKUP_EXT))
            raise SystemExit(1)
        if json_items is not None:
            return json_items
        ad = text.replace('{', 'AttrDict(**{').replace('}', '})')
        ad = re.sub(r"'size': ([0-9]+)L,",r"'size': \1,",ad)
        return _load_legacy_literal(ad)
    except IOError:
        return []

def save_config_file(items):
    info('saving config...')
    def write(w):
        print('# {} games'.format(len(items)-1), file=w)
        pprint.pprint(items, width=123, stream=w)
    try:
        atomic_write_text(CONFIG_FILENAME, write)
        info('saved config')
    except KeyboardInterrupt:
        atomic_write_text(CONFIG_FILENAME, write)
        info('saved config')
        raise

def load_config_file(filepath=CONFIG_FILENAME):
    info('loading config...')
    try:
        with open(filepath, mode='r', encoding='utf-8') as r:
            ad = r.read().replace('{', 'AttrDict(**{').replace('}', '})')
        return _load_legacy_literal(ad)
    except IOError:
        return []
def open_notrunc(name, bufsize=4*1024):
    flags = os.O_WRONLY | os.O_CREAT
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY  # windows
    fd = os.open(name, flags, 0o666)
    return os.fdopen(fd, 'wb', bufsize)

def open_notruncwrrd(name, bufsize=4*1024):
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY  # windows
    fd = os.open(name, flags, 0o666)
    return os.fdopen(fd, 'r+b', bufsize)


def hashstream(stream,start,end):
    stream.seek(start)
    readlength = (end - start)+1
    hasher = hashlib.md5()
    try:
        buf = stream.read(readlength)
        hasher.update(buf)
    except Exception:
        log_exception('')
        raise
    return hasher.hexdigest()

def hashfile(afile, blocksize=65536):
    # Refactoring (fix): the file is closed now (it used to be left to the garbage collector).
    hasher = hashlib.md5()
    with open(afile, 'rb') as f:
        buf = f.read(blocksize)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(blocksize)
    return hasher.hexdigest()


HASH_BLOCKSIZE = 1024 * 1024


def blake3_available():
    """True when the optional blake3 package is installed (entry 38)."""
    return _blake3 is not None


def _new_blake3_hasher():
    """A BLAKE3 hasher that may use several threads for large updates (when this version of the package can)."""
    try:
        return _blake3.blake3(max_threads=_blake3.blake3.AUTO)
    except (AttributeError, TypeError):
        return _blake3.blake3()


def hash_file(path, md5=True, blake3=False, blocksize=HASH_BLOCKSIZE):
    """Hashes a file with MD5 and/or BLAKE3 in ONE read pass. Returns {'md5': hex or None, 'blake3': hex or None}.
    When only BLAKE3 is wanted, the file is memory-mapped (fast, multi-threaded) if the package supports it; any problem
    with that falls back to normal reads. Entry 38."""
    result = {'md5': None, 'blake3': None}
    if blake3 and _blake3 is None:
        raise RuntimeError('the blake3 package is not installed')
    if blake3 and not md5:
        hasher = _new_blake3_hasher()
        update_mmap = getattr(hasher, 'update_mmap', None)
        if update_mmap is not None:
            try:
                update_mmap(path)
                result['blake3'] = hasher.hexdigest()
                return result
            except Exception:
                pass    # empty or unmappable file, or an older package: read it normally below
    md5_hasher = hashlib.md5() if md5 else None
    blake3_hasher = _new_blake3_hasher() if blake3 else None
    buf = bytearray(blocksize)
    view = memoryview(buf)
    with open(path, 'rb', buffering=0) as f:
        while True:
            n = f.readinto(buf)
            if not n:
                break
            chunk = view[:n]
            if md5_hasher is not None:
                md5_hasher.update(chunk)
            if blake3_hasher is not None:
                blake3_hasher.update(chunk)
    if md5_hasher is not None:
        result['md5'] = md5_hasher.hexdigest()
    if blake3_hasher is not None:
        result['blake3'] = blake3_hasher.hexdigest()
    return result


def test_zipfile(filename):
    """Opens filename and tests the file for ZIP integrity.  Returns True if
    zipfile passes the integrity test, False otherwise.
    """
    badZipException = zipfile.BadZipFile

    try:
        with zipfile.ZipFile(filename, 'r') as f:
            if f.testzip() is None:
                return True
    except (badZipException,zlib.error) as e:
        return False
    return False


def pretty_size(n):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if n < 1024 or unit == 'TB':
            break
        n = n / 1024  # start at KB

    if unit == 'B':
        return "{0}{1}".format(n, unit)
    else:
        return "{0:.2f}{1}".format(n, unit)


def get_total_size(dir):
    total = 0
    for (root, dirnames, filenames) in os.walk(dir):
        for f in filenames:
            total += os.path.getsize(os.path.join(root, f))
    return total


def item_checkdb(search_id, gamesdb):
    for i in range(len(gamesdb)):
        if search_id == gamesdb[i].id:
            return i
    return None

def handle_game_renames(savedir,gamesdb,dryrun):
    info("scanning manifest for renames...")
    orphan_root_dir = os.path.join(savedir, ORPHAN_DIR_NAME)
    if not os.path.isdir(orphan_root_dir):
        os.makedirs(orphan_root_dir)

    for game in gamesdb:
        try:
            _ = game.galaxyDownloads
        except AttributeError:
            game.galaxyDownloads = []

        try:
            a = game.sharedDownloads
        except AttributeError:
            game.sharedDownloads = []
        try:
            _ = game.old_title
        except AttributeError:
            game.old_title = None
        try:
            _ = game.folder_name
        except AttributeError:
            game.folder_name = game.title
        try:
            _ = game.old_folder_name
        except AttributeError:
            game.old_folder_name = game.old_title
        if (game.old_folder_name is not None):
            src_dir = os.path.join(savedir, game.old_folder_name)
            dst_dir = os.path.join(savedir, game.folder_name)
            if os.path.isdir(src_dir):
                try:
                    if os.path.exists(dst_dir):
                        warn("orphaning destination clash '{}'".format(dst_dir))
                        if not dryrun:
                            move_with_increment_on_clash(dst_dir, os.path.join(orphan_root_dir,game.folder_name))
                    info('  -> renaming directory "{}" -> "{}"'.format(src_dir, dst_dir))
                    if not dryrun:
                        move_with_increment_on_clash(src_dir,dst_dir)
                except Exception:
                    error('    -> rename failed "{}" -> "{}"'.format(game.old_folder_name, game.folder_name))
        for item in game.downloads+game.galaxyDownloads+game.sharedDownloads+game.extras:
            try:
                _ = item.old_name
            except AttributeError:
                item.old_name = None

            if (item.old_name is not None):
                game_dir =  os.path.join(savedir, game.folder_name)
                src_file =  os.path.join(game_dir,item.old_name)
                dst_file =  os.path.join(game_dir,item.name)
                if os.path.isfile(src_file):
                    try:
                        if os.path.exists(dst_file):
                            warn("orphaning destination clash '{}'".format(dst_file))
                            dest_dir = os.path.join(orphan_root_dir, game.folder_name)
                            if not os.path.isdir(dest_dir):
                                if not dryrun:
                                    os.makedirs(dest_dir)
                            if not dryrun:
                                move_with_increment_on_clash(dst_file, os.path.join(dest_dir,item.name))
                        info('  -> renaming file "{}" -> "{}"'.format(src_file, dst_file))
                        if not dryrun:
                            move_with_increment_on_clash(src_file,dst_file)
                            item.old_name = None #only once
                    except Exception:
                        error('    -> rename failed "{}" -> "{}"'.format(src_file, dst_file))
                        if not dryrun:
                            item.prev_verified = False



def handle_game_updates(olditem, newitem,strict, update_downloads_strict, update_extras_strict):
    try:
        _ = olditem.galaxyDownloads
    except AttributeError:
        olditem.galaxyDownloads = []

    try:
        a = olditem.sharedDownloads
    except AttributeError:
        olditem.sharedDownloads = []
    try:
        a = olditem.folder_name
    except AttributeError:
        olditem.folder_name = olditem.title
    try:
        a = newitem.folder_name
    except AttributeError:
        newitem.folder_name = newitem.title

    if newitem.has_updates:
        info('  -> gog flagged this game as updated')

    if olditem.title != newitem.title:
        info('  -> title has changed "{}" -> "{}"'.format(olditem.title, newitem.title))
        newitem.old_title = olditem.title

    if olditem.folder_name != newitem.folder_name:
        info('  -> folder name has changed "{}" -> "{}"'.format(olditem.folder_name, newitem.folder_name))
        newitem.old_folder_name = olditem.folder_name

    if olditem.long_title != newitem.long_title:
        try:
            info('  -> long title has change "{}" -> "{}"'.format(olditem.long_title, newitem.long_title))
        except UnicodeEncodeError:
            pass

    # Older gogrepoc manifests may not contain a changelog key.
    old_changelog = getattr(olditem, 'changelog', '')
    new_changelog = getattr(newitem, 'changelog', '')
    if old_changelog != new_changelog and new_changelog not in (None, ''):
        info('  -> changelog was updated')

    try:
        if olditem.serials != newitem.serials:
            info('  -> serial key(s) have changed')
    except AttributeError:
        if olditem.serial != '':
            info('  -> gogrepoc serial key format has changed')
        if olditem.serial != newitem.serial:
            info('  -> serial key has changed')

    #Done this way for backwards compatability. Would be faster to do each separately.
    for newDownload in newitem.downloads+newitem.galaxyDownloads+newitem.sharedDownloads:
        candidate = None
        for oldDownload in olditem.downloads+olditem.galaxyDownloads+olditem.sharedDownloads:
            if oldDownload.md5 is not None:
                if oldDownload.md5 == newDownload.md5 and oldDownload.size == newDownload.size and oldDownload.lang == newDownload.lang:
                    if oldDownload.name == newDownload.name:
                        candidate = oldDownload #Match already exists
                        break #Can't be overriden so end it now
                    if oldDownload.name != newDownload.name and ( candidate == None or candidate.md5 == None ) : #Will not override and gets overridden by a perfect match (also allows only one match)
                         candidate = oldDownload
            else:
                if oldDownload.size == newDownload.size and oldDownload.name == newDownload.name and oldDownload.lang == newDownload.lang and candidate == None:
                    candidate = AttrDict(**oldDownload.copy())
                    if strict:
                        candidate.blake3 = None    # entry 38: no md5 to confirm it is the same file, so the recorded BLAKE3 goes too
                        try:
                           candidate.prev_verified = False
                        except AttributeError:
                            pass
        if candidate != None:
            try:
                _ = candidate.unreleased
            except AttributeError:
                candidate.unreleased = False
            try:
                newDownload.prev_verified = candidate.prev_verified
            except AttributeError:
                newDownload.prev_verified = False
            newDownload.blake3 = getattr(candidate, 'blake3', None)    # entry 38: same content (md5/size/lang match), same BLAKE3
            try:
                newDownload.old_updated = candidate.old_updated #Propogate until actually updated.
            except AttributeError:
                newDownload.old_updated = None
            try:
                newDownload.force_change = candidate.force_change
            except AttributeError:
                newDownload.force_change = False #An entry lacking force_change will also lack old_updated so this gets handled later

            oldUpdateTime = None
            updateTime = None
            if newDownload.old_updated is not None:
                oldUpdateTime = datetime.datetime.fromisoformat(newDownload.old_updated)
            if newDownload.updated is not None:
                updateTime = datetime.datetime.fromisoformat(newDownload.updated)
            newestUpdateTime = None
            newer = False
            if updateTime is None:
                newer = True  #Treating this as definitive because it's probably a result of an item being removed
            elif oldUpdateTime is None:
                newestUpdateTime = newDownload.updated
            elif updateTime > oldUpdateTime:
                newer = True
                newestUpdateTime = newDownload.updated
            else:
                newestUpdateTime = newDownload.old_updated

            if candidate.name != newDownload.name:
                info('  -> in folder_name "{}" a download has changed name "{}" -> "{}"'.format(newitem.folder_name,candidate.name,newDownload.name))
                newDownload.old_name  = candidate.name
            if (candidate.md5 != None and candidate.md5 == newDownload.md5 and candidate.size == newDownload.size) or ( newDownload.unreleased and candidate.unreleased ):
                #Not released or MD5s match , so whatever the update was it doesn't matter
                newDownload.old_updated = newestUpdateTime
                newDownload.updated =  newestUpdateTime
            elif update_downloads_strict:
                newDownload.updated = newestUpdateTime #Don't forget our *newest* update time.
                if newer:
                    info('  -> in folder_name "{}" a download "{}" has probably been updated (update date {} -> {}) and has been marked for change."'.format(newitem.folder_name,newDownload.name,newDownload.old_updated,newDownload.updated))
                    newDownload.force_change = True
        else:
            #New file entry, presume changed
            newDownload.force_change = True

    for newExtra in newitem.extras:
        candidate = None
        for oldExtra in olditem.extras:
            if (oldExtra.md5 != None):
                if oldExtra.md5 == newExtra.md5 and oldExtra.size == newExtra.size:
                    if oldExtra.name == newExtra.name:
                        candidate = oldExtra #Match already exists
                        break #Can't be overriden so end it now
                    if oldExtra.name != newExtra.name and (candidate == None or candidate.md5 == None):
                        candidate = oldExtra
            else:
                if oldExtra.name == newExtra.name and oldExtra.size == newExtra.size and candidate == None:
                    candidate = AttrDict(**oldExtra.copy())
                    if strict:
                        candidate.blake3 = None    # entry 38
                        try:
                            #candidate.force_change = True
                            candidate.prev_verified = False
                        except AttributeError:
                            pass
        if candidate != None:
            try:
                _ = candidate.unreleased
            except AttributeError:
                candidate.unreleased = False
            try:
                newExtra.prev_verified = candidate.prev_verified
            except AttributeError:
                newExtra.prev_verified = False
            newExtra.blake3 = getattr(candidate, 'blake3', None)    # entry 38
            try:
                newExtra.force_change = candidate.force_change
            except AttributeError:
                newExtra.force_change = False #An entry lacking force_change will also lack old_updated so this gets handled later
            try:
                newExtra.old_updated = candidate.old_updated #Propogate until actually updated.
            except AttributeError:
                newExtra.old_updated = None

            oldUpdateTime = None
            updateTime = None
            if newExtra.old_updated is not None:
                oldUpdateTime = datetime.datetime.fromisoformat(newExtra.old_updated)
            if newExtra.updated is not None:
                updateTime = datetime.datetime.fromisoformat(newExtra.updated)
            newestUpdateTime = None
            newer = False
            if updateTime is None:
                newer = True  #Treating this as definitive because it's probably a result of an item being removed
            elif oldUpdateTime is None:
                newestUpdateTime = newExtra.updated
            elif updateTime > oldUpdateTime:
                newer = True
                newestUpdateTime = newExtra.updated
            else:
                newestUpdateTime = newExtra.old_updated

            if candidate.name != newExtra.name:
                info('  -> in folder_name "{}" an extra has changed name "{}" -> "{}"'.format(newitem.folder_name,candidate.name,newExtra.name))
                newExtra.old_name  = candidate.name
            if (candidate.md5 != None and candidate.md5 == newExtra.md5 and candidate.size == newExtra.size) or ( newExtra.unreleased and candidate.unreleased ):
                #Not released or MD5s match , so whatever the update was it doesn't matter
                newExtra.old_updated = newestUpdateTime
                newExtra.updated =  newestUpdateTime
            elif update_extras_strict:
                newExtra.updated = newestUpdateTime #Don't forget our *newest* update time.
                if newer:
                    info('  -> in folder_name "{}" an extra "{}" has perhaps been updated (update date {} -> {}) and has been marked for change."'.format(newitem.folder_name,newExtra.name,newExtra.old_updated,newExtra.updated))
                    newExtra.force_change = True
        else:
            #New file entry, presume changed
            newExtra.force_change = True


def fetch_product_download_links(session, product_id):
    """Return GOG product API downlink resolvers indexed by their file id."""
    if product_id is None:
        return {}
    response = request(session, GOG_API_URL + '/products/{}'.format(product_id),
                       args={'expand': 'downloads,expanded_dlcs'})
    product_data = response.json()
    links = {}

    def add_product(product):
        slug = product.get('slug')
        downloads = product.get('downloads') or {}
        for category in ('installers', 'patches', 'language_packs', 'bonus_content'):
            for download_group in downloads.get(category) or []:
                for download_file in download_group.get('files') or []:
                    api_downlink = download_file.get('downlink')
                    if api_downlink and slug:
                        file_id = urlparse(api_downlink).path.rstrip('/').split('/')[-1]
                        links[(slug, file_id)] = api_downlink
        for dlc in product.get('expanded_dlcs') or []:
            add_product(dlc)

    add_product(product_data)
    return links


def find_product_downlink(product_download_links, manual_url):
    if not product_download_links or not manual_url:
        return None
    path_parts = urlparse(manual_url).path.rstrip('/').split('/')
    if len(path_parts) < 2:
        return None
    return product_download_links.get((path_parts[-2], path_parts[-1]))


def fetch_checksum_url(session, api_downlink):
    if not api_downlink:
        return None
    response = request(session, api_downlink)
    return response.json().get('checksum')


def fetch_chunk_tree(response, session, api_downlink=None):
    chunk_url = None
    file_ext = os.path.splitext(urlparse(response.url).path)[1].lower()
    if file_ext not in SKIP_MD5_FILE_EXT:
        try:
            if api_downlink:
                chunk_url = fetch_checksum_url(session, api_downlink)
                if not chunk_url:
                    warn("no checksum URL found for {}".format(
                        unquote(urlparse(response.url).path.split('/')[-1])))
                    return None
            else:
                # Backwards compatibility for manifests made before api_downlink was stored.
                query = parse_qs(urlparse(response.url).query)
                uses_signed_prefix = all(key in query for key in ('wsSecret', 'wsTime', 'prefix'))
                if not uses_signed_prefix:
                    chunk_url = append_xml_extension_to_url_path(response.url)
                else:
                    warn("signed prefix required to fetch checksum data for {} but secret could not be retrieved".format(
                        unquote(urlparse(response.url).path.split('/')[-1])))
                    return None
            chunk_response = request(session,chunk_url,quiet_statuses=(404,))
            shelf_etree = xml.etree.ElementTree.fromstring(chunk_response.content)
            return  shelf_etree
        except requests.HTTPError as e:
            if not chunk_url:
                chunk_url = unquote(urlparse(response.url).path.split('/')[-1])
                warn("invalid downlink found for {}".format(chunk_url) + " . Leading to ")
            if e.response.status_code == 404:
                note_summarised('no md5 data', unquote(urlparse(response.url).path.split('/')[-1]), NO_MD5_MESSAGE)
            else:
                warn("unexpected error fetching md5 data for {}".format(chunk_url))
                debug("The handled exception was:")
                if rootLogger.isEnabledFor(logging.DEBUG):
                    log_exception('')
                debug("End exception report.")
            return None
        except xml.etree.ElementTree.ParseError:
            warn('xml parsing error occurred trying to get md5 data for {}'.format(chunk_url))
            debug("The handled exception was:")
            if rootLogger.isEnabledFor(logging.DEBUG):
                log_exception('')
            debug("End exception report.")
            return None
        except requests.exceptions.ConnectionError as e:
            warn("unexpected connection error fetching md5 data for {}".format(chunk_url) + " This error may be temporary. Please retry in 24 hours.")
            debug("The handled exception was:")
            if rootLogger.isEnabledFor(logging.DEBUG):
                log_exception('')
            debug("End exception report.")
            return None
        except requests.exceptions.ContentDecodingError as e:
            warn("unexpected content decoding error fetching md5 data for {}".format(chunk_url) + " This error may be temporary. Please retry in 24 hours.")
            debug("The handled exception was:")
            if rootLogger.isEnabledFor(logging.DEBUG):
                log_exception('')
            debug("End exception report.")
            return None
    return None

def fetch_file_info(d, fetch_md5,save_md5_xml,updateSession,product_api_context=None,diagnostic=False):
   # fetch file name/size
    #try:
    response= request_head(updateSession,d.href)
    #except ContentDecodingError as e:
        #info('decoding failed because getting 0 bytes')
        #response = e.response


    d.gog_data.headers = AttrDict()
    d.gog_data.original_headers = AttrDict()
    for key in response.headers.keys():
        d.gog_data.original_headers[key] = response.headers[key]
    for key in d.gog_data.original_headers:
        d.gog_data.headers[key.lower()] = d.gog_data.original_headers[key]
    d.name = unquote(urlparse(response.url).path.split('/')[-1])
    d.size = int(d.gog_data.headers['content-length'])



    # fetch file md5
    if fetch_md5:
        file_ext = os.path.splitext(urlparse(response.url).path)[1].lower()
        skip_md5_file_ext = SKIP_MD5_FILE_EXT
        if diagnostic:
            skip_md5_file_ext = []
        if file_ext not in skip_md5_file_ext:
            try:
                #warn(response.url)
                api_downlink = d.gog_data.get('api_downlink')
                query = parse_qs(urlparse(response.url).query)
                uses_signed_prefix = all(key in query for key in ('wsSecret', 'wsTime', 'prefix'))
                if not api_downlink and uses_signed_prefix and product_api_context is not None:
                    if product_api_context.get('download_links') is None:
                        product_api_context.download_links = fetch_product_download_links(
                            updateSession, product_api_context.product_id)
                    api_downlink = find_product_downlink(
                        product_api_context.download_links, d.get('manualUrl'))
                    if api_downlink:
                        d.gog_data.api_downlink = api_downlink
                    else:
                        d.gog_data.api_downlink_fallback = True
                        try:
                            #We don't use root_product_id but sense checking it helps validate that we haven't just coincidentally hit a number on a link of the wrong form.
                            root_product_id = urlparse(response.url).path.split("/")[3]
                            product_id = urlparse(response.url).path.split("/")[4]
                        except IndexError:
                            root_product_id = ''
                            product_id = ''
                        validProductID = False
                        try:
                            #sense check
                            _ = int(root_product_id)
                            _ = int(product_id)
                            validProductID = True
                        except ValueError:
                            warn('Could not extract product ID from URL:' + response.url + " . Abandoning attempt to generate Galaxy API Link for %s" % (d.href))
                        if (validProductID):
                            type = d.get('manualUrl').split("/")[-1]
                            if "installer" in type:
                                api_downlink = "https://api.gog.com/products/"+product_id+"/downlink/installer/" + type
                            elif "patch" in type:
                                api_downlink = "https://api.gog.com/products/"+product_id+"/downlink/patch/" + type
                            else:
                                try:
                                    bonusID = int(type)
                                    api_downlink = "https://api.gog.com/products/"+product_id+"/downlink/product_bonus/" + type
                                except ValueError:
                                    pass
                            if api_downlink:
                                d.gog_data.api_downlink = api_downlink
                if api_downlink:
                    tmp_md5_url = fetch_checksum_url(updateSession, api_downlink)
                    if not tmp_md5_url:
                        #Rewrite this to treat absence of checksum link at this point as authorative indicator that none exists
                        #Not possible, GOG has a checksum endpoint for all files, even ones where no XML has ever existed.
                        warn("no checksum URL found for {}".format(d.name))
                        tmp_md5_url = append_xml_extension_to_url_path(response.url)
                else:
                    tmp_md5_url = append_xml_extension_to_url_path(response.url)
                if api_downlink or not uses_signed_prefix:  #Only try to use the signed prefix path if we have a signature
                    md5_response = request(updateSession,tmp_md5_url,quiet_statuses=(404,))
                    shelf_etree = xml.etree.ElementTree.fromstring(md5_response.content)
                    d.gog_data.md5_xml = AttrDict()
                    d.gog_data.md5_xml.tag = shelf_etree.tag
                    for key in shelf_etree.attrib.keys():
                        d.gog_data.md5_xml[key] = shelf_etree.attrib.get(key)
                    if (save_md5_xml):
                        d.gog_data.md5_xml.text = md5_response.text
                    #d.gog_data.md5_xml.chunks = AttrDict()
                    #Too large need a better way to handle this
                    #for child in shelf_etree:
                        #d.gog_data.md5_xml.chunks[child.attrib['id']] = AttrDict()
                        #d.gog_data.md5_xml.chunks[child.attrib['id']].tag = child.tag
                        #for key in child.attrib.keys():
                        #    d.gog_data.md5_xml.chunks[child.attrib['id']][key] = child.attrib.get(key)
                        #if len(child) != 0:
                        #    warn('Unexpected MD5 Chunk Structure, please report to the maintainer')
                    d.md5 = shelf_etree.attrib['md5']
                    d.raw_updated = shelf_etree.attrib['timestamp']
                    d.updated = datetime.datetime.fromisoformat(d.raw_updated).replace(tzinfo=datetime.timezone.utc).isoformat() #Standardize #Only valid after 3.7 or maybe 3.11 ? #Assumes that timezone is UTC (might actually be GMT +2 (Poland) but even if so UTC is a far more consistent approximation than local time for most of the world)
                else:
                    warn("signed prefix required to fetch checksum data for {} but secret cannot be retrieved".format(d.name))
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    note_summarised('no md5 data', d.name, NO_MD5_MESSAGE)
                else:
                    warn("unexpected error fetching md5 data for {}".format(d.name))
                debug("The handled exception was:")
                if rootLogger.isEnabledFor(logging.DEBUG):
                    log_exception('')
                debug("End exception report.")
            except xml.etree.ElementTree.ParseError as e:
                warn('xml parsing error occurred trying to get md5 data for {}'.format(d.name))
                debug("The handled exception was:")
                if rootLogger.isEnabledFor(logging.DEBUG):
                    log_exception('')
                debug("End exception report.")
            except requests.exceptions.ConnectionError as e:
                warn("unexpected connection error fetching md5 data for {}".format(d.name) + " This error may be temporary. Please retry in 24 hours.")
                debug("The handled exception was:")
                if rootLogger.isEnabledFor(logging.DEBUG):
                    log_exception('')
                debug("End exception report.")
            except requests.exceptions.ContentDecodingError as e:
                warn("unexpected content decoding error fetching md5 data for {}".format(d.name) + " This error may be temporary. Please retry in 24 hours.")
                debug("The handled exception was:")
                if rootLogger.isEnabledFor(logging.DEBUG):
                    log_exception('')
                debug("End exception report.")
        else:
            d.md5_exempt = True
    if d.updated == None:
        d.raw_updated = d.gog_data.headers["last-modified"]
        d.updated = email.utils.parsedate_to_datetime(d.raw_updated).isoformat() #Standardize

def filter_downloads(out_list, downloads_list, lang_list, os_list,save_md5_xml,updateSession,product_api_context=None,diagnostic=False,lang_fallback=None):
    """filters any downloads information against matching lang and os, translates
    them, and extends them into out_list
    """
    filtered_downloads = []
    downloads_dict = dict(downloads_list)

    # hold list of valid languages languages as known by gogapi json stuff
    valid_langs = []
    for lang in lang_list:
        valid_langs.append(LANG_TABLE[lang])

    # Refactoring: with a fallback language every operating system gets the wanted languages if GOG offers it in
    # one of them, and the fallback language otherwise. Decided here, on GOG's data, before any file info is fetched.
    fallback_name = LANG_TABLE[lang_fallback] if lang_fallback else None
    languages_for_os = {}
    for os_type in os_list:
        offered = [lang for lang in downloads_dict if lang in valid_langs and downloads_dict[lang].get(os_type)]
        languages_for_os[os_type] = valid_langs if (offered or not fallback_name) else [fallback_name]

    # check if lang/os combo passes the specified filter
    for lang in downloads_dict:
        if lang in valid_langs or lang == fallback_name:
            for os_type in downloads_dict[lang]:
                if os_type in os_list and lang in languages_for_os[os_type]:
                    for download in downloads_dict[lang][os_type]:
                        tempd = download['manualUrl']
                        if tempd[:10] == "/downloads":
                            tempd = "/downlink" +tempd[10:]
                        hrefs = [GOG_HOME_URL + download['manualUrl']] #GOG_HOME_URL + tempd (this seem to be obsolete and always return forbidden)
                        href_ds = []
                        file_info_success = False
                        md5_success = False
                        unreleased = False
                        for href in hrefs:
                            if not (unreleased or (file_info_success and md5_success)):
                                debug("trying to fetch file info from %s" % href)
                                file_info_success = False
                                md5_success = False
                                # passed the filter, create the entry
                                d = AttrDict(desc=download['name'],
                                             os_type=os_type,
                                             lang=lang,
                                             version=download['version'],
                                             href= href,
                                             md5=None,
                                             blake3=None,
                                             name=None,
                                             size=None,
                                             prev_verified=False,
                                             old_name=None,
                                             unreleased = False,
                                             md5_exempt = False,
                                             gog_data = AttrDict(),
                                             updated = None,
                                             old_updated = None,
                                             force_change = False,
                                             old_force_change = None
                                             )
                                for key in download:
                                    try:
                                        tmp_contents = d[key]
                                        if tmp_contents != download[key]:
                                            debug("GOG Data Key, %s , for download clashes with Download Data Key storing detailed info in secondary dict" % key)
                                            d.gog_data[key] = download[key]
                                    except Exception:
                                        d[key] = download[key]
                                if d.gog_data.size == "0 MB":#Not Available
                                    warn("Unreleased File, Skipping Data Fetching %s" % d.desc)
                                    d.unreleased = True
                                    unreleased = True
                                else: #Available
                                    try:
                                        #head_response = request_head(updateSession,d.href)
                                        #with open('head_test_headers.txt', mode='w', encoding='utf-8') as w:
                                        #    w.write(str(head_response.headers))
                                        #shelf_head.etree = xml.etree.ElementTree.fromstring(head_response.content)
                                        fetch_file_info(d, True,save_md5_xml,updateSession,product_api_context,diagnostic)
                                        file_info_success = True
                                    except requests.HTTPError as e:
                                        warn("failed to fetch %s" % (d.href))
                                        try:
                                            d.provisional_name = unquote(urlparse(e.response.url).path.split('/')[-1])
                                        except Exception:
                                            warn("failed to generate provisional name")
                                            warn("The handled exception was:")
                                            log_exception('')
                                            warn("End exception report.")
                                    except Exception:
                                        warn("failed to fetch %s and because of non-HTTP Error" % (d.href))
                                        warn("The handled exception was:")
                                        log_exception('')
                                        warn("End exception report.")
                                    if d.md5_exempt == True or d.md5 != None:
                                        md5_success = True


                                href_ds.append([d,file_info_success,md5_success])
                        if unreleased:
                            debug("File Not Available For Manual Download Storing Canonical Link: %s" % d.href)
                            filtered_downloads.append(d)
                        elif file_info_success and md5_success: #Will be the current d because no more are created once we're successful
                            debug("Successfully fetched file info and md5 from %s" % d.href)
                            filtered_downloads.append(d)
                        else: #Check for first file info success since all MD5s failed.
                            any_file_info_success = False
                            for href_d in href_ds:
                                if not any_file_info_success:
                                    if (href_d[1]) == True:
                                        any_file_info_success = True
                                        filtered_downloads.append(href_d[0])
                                        note_summarised('no md5 data', href_d[0].name or href_d[0].href, NO_MD5_MESSAGE)
                            if not any_file_info_success:
                                #None worked so go with the canonical link
                                error("Could not fetch file info so using canonical link: %s" % href_ds[0][0].href)
                                filtered_downloads.append(href_ds[0][0])
    out_list.extend(filtered_downloads)


def filter_extras(out_list, extras_list,save_md5_xml,updateSession,product_api_context=None,diagnostic=False):
    """filters and translates extras information and adds them into out_list
    """
    filtered_extras = []

    for extra in extras_list:
        tempd = extra['manualUrl']
        if tempd[:10] == "/downloads":
            tempd = "/downlink" +tempd[10:]
        hrefs = [GOG_HOME_URL + extra['manualUrl']] #GOG_HOME_URL + tempd (this seem to be obsolete and always return forbidden)
        href_ds = []
        file_info_success = False
        md5_success = False
        unreleased = False
        for href in hrefs:
            if not (unreleased or file_info_success):
                debug("trying to fetch file info from %s" % href)
                file_info_success = False
                d = AttrDict(desc=extra['name'],
                             os_type='extra',
                             lang='',
                             version=None,
                             href= href,
                             md5=None,
                             blake3=None,
                             name=None,
                             size=None,
                             prev_verified=False,
                             old_name = None,
                             unreleased = False,
                             md5_exempt = False,
                             gog_data = AttrDict(),
                             updated = None,
                             old_updated = None,
                             force_change = False,
                             old_force_change = None
                             )
                for key in extra:
                    try:
                        tmp_contents = d[key]
                        if tmp_contents != extra[key]:
                            debug("GOG Data Key, %s , for extra clashes with Extra Data Key storing detailed info in secondary dict" % key)
                            d.gog_data[key] = extra[key]
                    except Exception:
                        d[key] = extra[key]
                if d.gog_data.size == "0 MB":#Not Available
                    debug("Unreleased File, Skipping Data Fetching %s" % d.desc)
                    d.unreleased = True
                    unreleased = True
                else:
                    try:
                        #head_response = request_head(updateSession,d.href)
                        #with open('head_test_headers.txt', mode='w', encoding='utf-8') as w:
                        #    w.write(str(head_response.headers))
                        fetch_file_info(d, True,save_md5_xml,updateSession,product_api_context,diagnostic)
                        file_info_success = True
                    except requests.HTTPError as e:
                        warn("failed to fetch %s" % d.href)
                        try:
                            d.provisional_name = unquote(urlparse(e.response.url).path.split('/')[-1])
                        except Exception:
                            warn("failed to generate provisional name")
                            warn("The handled exception was:")
                            log_exception('')
                            warn("End exception report.")
                    except Exception:
                        warn("failed to fetch %s because of non-HTTP Error" % d.href)
                        warn("The handled exception was:")
                        log_exception('')
                        warn("End exception report.")
                    if d.md5_exempt == True or d.md5 != None:
                        md5_success = True
                href_ds.append([d,file_info_success])
        if unreleased:
            debug("File Not Available For Manual Download Storing Canonical Link: %s" % d.href)
            filtered_extras.append(d)
        elif file_info_success and md5_success: #Will be the current d because no more are created once we're successful
            debug("Successfully fetched file info and md5 from %s" % d.href)
            filtered_extras.append(d)
        else: #Check for first file info success since all MD5s failed.
            any_file_info_success = False
            for href_d in href_ds:
                if not any_file_info_success:
                    if (href_d[1]) == True:
                        any_file_info_success = True
                        filtered_extras.append(href_d[0])
                        note_summarised('no md5 data', href_d[0].name or href_d[0].href, NO_MD5_MESSAGE)
            if not any_file_info_success:
                #None worked so go with the canonical link
                error("Could not fetch file info so using canonical link: %s" % href_ds[0][0].href)
                filtered_extras.append(href_ds[0][0])
    out_list.extend(filtered_extras)


def filter_dlcs(item, dlc_list, lang_list, os_list,save_md5_xml,updateSession,product_api_context=None,diagnostic=False,lang_fallback=None):
    """filters any downloads/extras information against matching lang and os, translates
    them, and adds them to the item downloads/extras

    dlcs can contain dlcs in a recursive fashion, and oddly GOG does do this for some titles.
    """
    for dlc_dict in dlc_list:
        base_title = dlc_dict['title']
        potential_title = base_title
        i = 1
        while potential_title in item.used_titles:
            potential_title = base_title + " (" + str(i) + ")"
            i = i + 1
        item.used_titles.append(potential_title)
        if urlparse(dlc_dict['backgroundImage']).path != "":
           item.bg_urls[potential_title] = dlc_dict['backgroundImage']
        if dlc_dict['cdKey'] != '':
            item.serials[potential_title] = dlc_dict['cdKey']
            if (not(item.serials[potential_title].isprintable())): #Probably encoded in UTF-16
                pserial = item.serials[potential_title]
                if (len(pserial) % 2): #0dd
                    pserial=pserial+"\x00"
                pserial = bytes(pserial,"UTF-8")
                pserial = pserial.decode("UTF-16")
                if pserial.isprintable():
                    item.serials[potential_title] = pserial
                else:
                    warn('DLC serial code is unprintable for %s, storing raw',potential_title)
        downloads_dict = dict(dlc_dict['downloads'])
        available_langs = list(downloads_dict.keys())
        available_os_types = dict()
        for available_lang in available_langs:
                available_os_types[available_lang] =  list(downloads_dict[available_lang].keys())
        item.available_langs[potential_title] = available_langs
        item.available_os_types[potential_title] = available_os_types
        filter_downloads(item.downloads, dlc_dict['downloads'], lang_list, os_list,save_md5_xml,updateSession,product_api_context,diagnostic,lang_fallback)
        filter_downloads(item.galaxyDownloads, dlc_dict['galaxyDownloads'], lang_list, os_list,save_md5_xml,updateSession,product_api_context,diagnostic,lang_fallback)
        filter_extras(item.extras, dlc_dict['extras'],save_md5_xml,updateSession,product_api_context,diagnostic)
        filter_dlcs(item, dlc_dict['dlcs'], lang_list, os_list,save_md5_xml,updateSession,product_api_context,diagnostic,lang_fallback)  # recursive

def deDuplicateList(duplicatedList,existingItems,strictDupe):
    deDuplicatedList = []
    for update_item in duplicatedList:
        if update_item.name is not None:
            dummy_item = copy.copy(update_item)
            deDuplicatedName = deDuplicateName(dummy_item,existingItems,strictDupe)
            if deDuplicatedName is not None:
                if (update_item.name != deDuplicatedName):
                    info('  -> ' + update_item.name + ' already exists in this game entry with a different size and/or md5, this file renamed to ' + deDuplicatedName)
                    update_item.name = deDuplicatedName
                deDuplicatedList.append(update_item)
            else:
                info('  -> ' + update_item.name + ' already exists in this game entry with same size/md5, skipping adding this file to the manifest')
        else:
            #Placeholder for an item coming soon, pass through
            deDuplicatedList.append(update_item)
    return deDuplicatedList


def deDuplicateName(potentialItem,clashDict,strictDupe):
    try:
        #Check if Name Exists
        existingDict = clashDict[potentialItem.name]
        try:
            #Check if this md5 / size pair have already been resolved
            prevItemsCount = 0
            for key in existingDict:
                prevItemsCount += len(existingDict[key])
            md5list = existingDict[potentialItem.size]
            try:
                idx = md5list.index(potentialItem.md5)
            except ValueError:
                #Do this early, so we can abort early if need to rely on size match.
                existingDict[potentialItem.size].append(potentialItem.md5) #Mark as resolved
                if ((not strictDupe) and (None in md5list or potentialItem.md5 == None)):
                    return None
                else:
                    potentialItem.name = makeDeDuplicateName(potentialItem.name,prevItemsCount)
                    return deDuplicateName(potentialItem,clashDict,strictDupe)
            return None
        except KeyError:
            potentialItem.name = makeDeDuplicateName(potentialItem.name,prevItemsCount)
            existingDict[potentialItem.size] = [potentialItem.md5] #Mark as resolved
            return deDuplicateName(potentialItem,clashDict,strictDupe)
    except KeyError:
        #No Name Clash
        clashDict[potentialItem.name] = {potentialItem.size:[potentialItem.md5]}
        return potentialItem.name

def numbered_name(root, ext, count):
    """Insert "(count)" before the extension, e.g. setup.exe -> setup(1).exe.
    For GOG's multi-part .bin sets it goes before the part number: setup-1.bin -> setup(1)-1.bin.
    Refactoring: this rule used to be copy-pasted in makeDeDuplicateName and move_with_increment_on_clash."""
    if ext != ".bin":
        return root + "(" + str(count) + ")" + ext
    #bin file, adjust name to account for gogs weird extension method
    setDelimiter = root.rfind("-")
    try:
        setPart = int(root[setDelimiter+1:])
    except ValueError:
        #This indicators a false positive. The "-" found was part of the file name not a set delimiter.
        setDelimiter = -1
    if setDelimiter == -1:
        #not part of a bin file set , some other binary file , treat it like a non .bin file
        return root + "(" + str(count) + ")" + ext
    return root[:setDelimiter] + "(" + str(count) + ")" + root[setDelimiter:] + ext

def makeDeDuplicateName(name,prevItemsCount):
    # Refactoring (fix): uses path_preserving_split_ext, so names without an extension no longer raise ValueError.
    root,ext = path_preserving_split_ext(name)
    return numbered_name(root, ext, prevItemsCount)


def check_skip_file(fname, skipfiles):
    # return pattern that matched, or None
    for skipf in skipfiles:
        if fnmatch(fname, skipf):
            return skipf
    return None

def process_path(path):
    fpath = path
    fpath = os.path.abspath(fpath)
    raw_fpath = '\\\\?\\%s' % fpath
    return raw_fpath

def is_numeric_id(s):
    try:
        int(s)
        return True
    except (ValueError, TypeError):  # Refactoring (fix): TypeError added, so None and other non-strings return False
        return False

def md5_xml_url(url):
    """Build the URL of the MD5 XML file that belongs to a download URL. Returns (xml_url, had_prefix).

    '.xml' is appended to the URL path and, when the URL has a 'prefix' query parameter (the older
    signed-URL format), to that too. had_prefix is False for URLs without that parameter, such as the
    newer CDN URLs that carry the access token in the path.
    Refactoring: split out of append_xml_extension_to_url_path so it is pure and unit-testable."""
    parsed = urlparse(url)
    parsed_query = parse_qs(parsed.query)
    had_prefix = True
    try:
        parsed_query['prefix'][0]=parsed_query['prefix'][0] + ".xml"
        encoded_query = urlencode(parsed_query,doseq=True)
        parsed = parsed._replace(query=encoded_query)
    except KeyError:
        had_prefix = False
    xml_url = urlunparse(parsed._replace(path = parsed.path + ".xml")).replace('%28','(').replace('%29',')').replace('%2F','/') #Thanks to pasbeg
    return xml_url, had_prefix

def append_xml_extension_to_url_path(url):
    xml_url, had_prefix = md5_xml_url(url)
    if not had_prefix:
        note_summarised("md5 url without 'prefix'", unquote(urlparse(url).path.split('/')[-1]),
                            "The MD5 URL for {count} file(s) had no 'prefix' query parameter, so '.xml' was appended to the URL path instead "
                            "(typical for GOG's newer CDN URLs, which carry the access token in the path). This is harmless if the MD5s were found; "
                            "if many files also report missing MD5 data, the URL format has probably changed again, please report it to the maintainer.")
    return xml_url

class GogArgumentParser(argparse.ArgumentParser):
    """ArgumentParser which also accepts each legacy single-dash long option
    (e.g. -skipos) in GNU style (--skipos). The single-dash spellings keep
    working exactly as before; the aliases map to the same dest."""

    @staticmethod
    def _add_aliases(names):
        extra = tuple('-' + n for n in names
                      if n.startswith('-') and not n.startswith('--') and len(n) > 2
                      and ('-' + n) not in names)
        return names + extra

    def add_argument(self, *names, **kwargs):
        return super(GogArgumentParser, self).add_argument(*self._add_aliases(names), **kwargs)

    def _wrap_group(self, group):
        plain_add = group.add_argument
        group.add_argument = lambda *names, **kwargs: plain_add(*self._add_aliases(names), **kwargs)
        return group

    def add_argument_group(self, *args, **kwargs):
        return self._wrap_group(super(GogArgumentParser, self).add_argument_group(*args, **kwargs))

    def add_mutually_exclusive_group(self, *args, **kwargs):
        return self._wrap_group(super(GogArgumentParser, self).add_mutually_exclusive_group(*args, **kwargs))


def add_common_flags(parser):
    """Options shared by every sub-command."""
    parser.add_argument('-nolog', action='store_true', help="doesn't write log file gogrepo.log")
    parser.add_argument('-debug', action='store_true', help="Includes debug messages")
    parser.add_argument('-manifestformat', choices=['json', 'legacy'], default='json',
                        help="file format used when the manifest is saved: json (default: fast, readable in any text editor) or legacy (the original format, for other gogrepo versions). Both formats can always be read.")


def validate_lang_and_os(args):
    """Exit with an error if a language/os given on the command line is unknown."""
    for lang in args.lang + args.skiplang:
        if lang not in VALID_LANG_TYPES:
            error('error: specified language "%s" is not one of the valid languages %s' % (lang, VALID_LANG_TYPES))
            raise SystemExit(1)

    for os_type in args.os + args.skipos:
        if os_type not in VALID_OS_TYPES:
            error('error: specified os "%s" is not one of the valid os types %s' % (os_type, VALID_OS_TYPES))
            raise SystemExit(1)


# ---------------------------------------------------------------------------------------------
# Finding games by id or name (-ids, -skipids and the list command)
# ---------------------------------------------------------------------------------------------
# Marks that are dropped from names (not turned into a space): trade mark signs and apostrophes.
_NAME_MARKS = dict.fromkeys(map(ord, u"\u2122\u00ae\u00a9\u2120'\u2019\u02bc`"))
SUGGESTION_CUTOFF = 0.6        # how alike a name must be to be suggested (0 to 1)
SUGGESTION_LIMIT = 3           # how many games are suggested at most


def normalize_name(text):
    """A game name in a form that ignores case, accents, punctuation, underscores and spacing, so that the name shown on GOG
    ('Ultima(tm) IV: Quest of the Avatar') and the title used in file names ('ultima_iv_quest_of_the_avatar') become the same.
    Letters of every script are kept as they are (only accents on Latin letters are dropped)."""
    text = unicodedata.normalize('NFKC', str(text).translate(_NAME_MARKS))
    kept = []
    for char in text:
        if ord(char) < 0x250:       # Latin letters: drop the accents (e acute -> e)
            char = ''.join(c for c in unicodedata.normalize('NFKD', char) if not unicodedata.combining(c))
        kept.append(char if char and all(c.isalnum() or unicodedata.category(c)[0] == 'M' for c in char) else ' ')
    return ' '.join(''.join(kept).casefold().split())


def game_names(game):
    """The names a game is known by: its title (as used in folder names and by -ids) and its long title (as shown on GOG)."""
    names = [game.title]
    long_title = getattr(game, 'long_title', None)
    if long_title and long_title != game.title:
        names.append(long_title)
    return names


def describe_game(game):
    return '%s (id %s, %s)' % (game.title, game.id, getattr(game, 'long_title', game.title))


def _name_index(items):
    """{normalised name: [games with that name]}"""
    index = {}
    for game in items:
        for name in game_names(game):
            key = normalize_name(name)
            found = index.setdefault(key, []) if key else []
            if not found or found[-1] is not game:
                found.append(game)
    return index


def _name_score(key, words, name):
    """How much a (normalised) name looks like what was typed: 1 = the same, 0.8-0.9 = contains all the words, less = alike."""
    if key == name:
        return 1.0
    if all(word in name for word in words):
        return 0.9 if name.startswith(key) else 0.8
    matcher = difflib.SequenceMatcher(None, key, name)
    best = matcher.ratio() if matcher.real_quick_ratio() >= SUGGESTION_CUTOFF and matcher.quick_ratio() >= SUGGESTION_CUTOFF else 0.0
    name_words = name.split()
    if name_words:         # a typo in one word should not spoil the match of the others
        total = 0.0
        for word in words:
            top = 0.0
            for name_word in name_words:
                m = difflib.SequenceMatcher(None, word, name_word)
                if m.real_quick_ratio() > top and m.quick_ratio() > top:
                    top = max(top, m.ratio())
            total += top
        best = max(best, 0.9 * total / len(words))
    return best


def suggest_games(items, query, limit=SUGGESTION_LIMIT):
    """The games whose names are most like the query (a typo, a part of the name, other word order), best first."""
    key = normalize_name(query)
    if len(key) < 3:
        return []
    words = key.split()
    scored = []
    for game in items:
        best = max(_name_score(key, words, normalize_name(name)) for name in game_names(game))
        if best >= SUGGESTION_CUTOFF:
            scored.append((-best, game.title, game))
    scored.sort(key=lambda entry: (entry[0], entry[1]))
    return [entry[2] for entry in scored[:limit]]


def search_games(items, terms):
    """The games whose title, name or id contain all of the words (in any order and any case), best matches first. A word that
    is only digits also matches the start or any part of the id if it has at least 4 digits."""
    terms = [str(term) for term in terms if str(term).strip()]
    if not terms:
        return sorted(items, key=lambda game: game.title)       # nothing asked for: all games
    key = normalize_name(' '.join(terms))
    words = key.split()
    if not words:
        return []                                               # only punctuation: that matches no game
    found = []
    for game in items:
        names = [normalize_name(name) for name in game_names(game)]
        text, id_text = ' '.join(names), str(game.id)
        if not all(word in text or (word.isdigit() and len(word) >= 4 and word in id_text) for word in words):
            continue
        rank = 0 if (key in names or key == id_text) else 1 if any(name.startswith(key) for name in names) else 2
        found.append((rank, game.title, game))
    found.sort(key=lambda entry: (entry[0], entry[1]))
    return [entry[2] for entry in found]


class IdResolution(object):
    """What -ids (or -skipids) means in the manifest."""
    def __init__(self):
        self.selected = set()   # the ids of the games that were meant
        self.notes = []         # games that were found by their name, not by their exact title or id
        self.problems = []      # (what, why, message): something that matches no game, or several games


def resolve_game_ids(items, ids, option='-ids'):
    """Which of the games do these ids mean? An id (number) or an exact title selects a game, as always. A name that is only
    different in case, accents, punctuation, underscores or spacing ('Beneath a Steel Sky (1994)') selects it too, if it fits one
    game. Anything else is a problem, with the games that look most like it, and a hint when the words of one name were typed
    without quotes. A game is never selected because it looks a bit like what was typed."""
    result = IdResolution()
    by_title = dict((game.title, game) for game in items)
    by_id = dict((str(game.id), game) for game in items)
    index = _name_index(items)
    ids = [str(i) for i in ids]
    unmatched = []
    for position, query in enumerate(ids):
        game = by_title.get(query) or by_id.get(query)
        if game is not None:
            result.selected.add(game.id)
            continue
        found = index.get(normalize_name(query), []) if normalize_name(query) else []
        if len(found) == 1:
            result.selected.add(found[0].id)
            result.notes.append("%s '%s' is taken as %s" % (option, query, describe_game(found[0])))
        elif len(found) > 1:
            result.problems.append(('%s %s' % (option, query), 'could be several games',
                                    "%s '%s' could be any of these games, so none was chosen; use the id or the exact title: %s"
                                    % (option, query, '; '.join(describe_game(game) for game in found))))
        else:
            unmatched.append(position)
    # words of one name that were typed without quotes (-ids Beneath a Steel Sky)
    explained = set()
    start = 0
    while start < len(unmatched):
        stop = start
        while stop + 1 < len(unmatched) and unmatched[stop + 1] == unmatched[stop] + 1:
            stop += 1                                   # unmatched[start:stop+1] are next to each other on the command line
        first = start
        while first < stop:
            for last in range(stop, first, -1):
                words = ids[unmatched[first]:unmatched[last] + 1]
                found = index.get(normalize_name(' '.join(words)), [])
                if len(found) == 1:
                    shown = ' '.join("'%s'" % word for word in words)
                    result.problems.append(('%s %s' % (option, ' '.join(words)), 'name typed without quotes',
                                            '%s %s look like the name of one game that was split into words: %s. A name with spaces '
                                            'must be in quotes: %s "%s"' % (option, shown, describe_game(found[0]), option,
                                                                           ' '.join(words))))
                    explained.update(range(unmatched[first], unmatched[last] + 1))
                    first = last
                    break
            first += 1
        start = stop + 1
    for position in unmatched:
        if position in explained:
            continue
        suggestions = suggest_games(items, ids[position])
        result.problems.append(('%s %s' % (option, ids[position]), 'no such game',
                                "%s '%s' matches no game in the manifest.%s" % (
                                    option, ids[position],
                                    ' Did you mean: %s?' % '; '.join(describe_game(game) for game in suggestions) if suggestions
                                    else " ('list' shows the games; 'list <words>' searches them.)")))
    return result


def report_id_resolution(result):
    for note in result.notes:
        info(note)
    for what, why, message in result.problems:
        error(message)
        run_report.fail(what, why)


def resolve_ids_and_report(items, ids, option='-ids'):
    """The ids of the games that -ids (or -skipids) means; what does not match is logged and counts as a failed run."""
    result = resolve_game_ids(items, ids, option)
    report_id_resolution(result)
    return result.selected


# ---------------------------------------------------------------------------------------------
# Library tags (-tags and -skiptags; entry 39)
# ---------------------------------------------------------------------------------------------
# The tags are the ones you made in your GOG library. GOG sends them with the product list: every product has a list of tag ids,
# and the whole answer has the list of {id, name}. update stores the NAMES in the field tag_names of each game in the manifest
# (also for games it does not fetch again), and the other commands read them from there.
def tag_key(name):
    """A tag name in the form that is compared: case, accents, punctuation and spacing do not matter."""
    return normalize_name(name)


def tag_map_of(json_data):
    """{tag id (text): tag name} from a page of the product list."""
    tag_map = {}
    for tag in (json_data.get('tags') or []):
        if isinstance(tag, dict) and tag.get('id') is not None and tag.get('name'):
            tag_map[str(tag['id'])] = str(tag['name'])
    return tag_map


def product_tag_names(product, tag_map):
    """The names of the tags of one product of the product list. A tag id with no known name is kept as the id, so that it
    can still be used."""
    names = []
    for tag in (product.get('tags') or []):
        if isinstance(tag, dict):
            name = tag.get('name') or tag_map.get(str(tag.get('id')))
        else:
            name = tag_map.get(str(tag))
            if name is None:
                name = str(tag)
        if name and str(name) not in names:
            names.append(str(name))
    return names


def game_tag_names(game):
    return list(getattr(game, 'tag_names', None) or [])


def game_has_any_tag(game, keys):
    return bool(set(tag_key(name) for name in game_tag_names(game)) & keys)


def tag_keys(tags):
    return set(key for key in (tag_key(tag) for tag in tags) if key)


class TagSelection(object):
    def __init__(self):
        self.selected = None     # ids of the games that have one of the -tags (None: -tags was not used)
        self.skipped = set()     # ids of the games that have one of the -skiptags
        self.problems = []       # (what, why, message)
        self.fatal = False       # nothing can be decided (the manifest has no tag data)


def select_games_by_tags(items, tags, skiptags):
    """Which games do -tags and -skiptags mean? A game matches if it has ANY of the tags. A tag that no game has is a problem, with
    the tags that exist, and a hint when the words of one tag were typed without quotes."""
    result = TagSelection()
    known = {}
    for game in items:
        for name in game_tag_names(game):
            known.setdefault(tag_key(name), name)
    if not any('tag_names' in game for game in items):
        result.fatal = True
        result.problems.append(('-tags' if tags else '-skiptags', 'no tag data',
                                "The manifest holds no tag data yet. Run 'update' once: it reads your tags from GOG and keeps them in the manifest."))
        return result

    def check(option, wanted):
        unmatched = [tag for tag in wanted if tag_key(tag) and tag_key(tag) not in known]
        shown = ('Tags in the manifest: %s.' % ', '.join(sorted(known.values(), key=str.casefold))) if known else 'No game in the manifest has a tag.'
        joined = ' '.join(unmatched)
        for tag in unmatched:
            hint = ''
            if len(unmatched) > 1 and tag_key(joined) in known:
                hint = ' The words %s look like one tag that was split into words: %s. A tag with spaces must be in quotes: %s "%s".' % (
                    ' '.join("'%s'" % word for word in unmatched), known[tag_key(joined)], option, joined)
            result.problems.append(('%s %s' % (option, tag), 'no such tag',
                                    "%s '%s' matches no game in the manifest.%s %s" % (option, tag, hint, shown)))
    check('-tags', tags)
    check('-skiptags', skiptags)
    if tags:
        keys = tag_keys(tags)
        result.selected = set(game.id for game in items if game_has_any_tag(game, keys))
    if skiptags:
        keys = tag_keys(skiptags)
        result.skipped = set(game.id for game in items if game_has_any_tag(game, keys))
    return result


def apply_tag_options(args):
    """For download, verify, import and backup: turns -tags and -skiptags into the ids that -ids / -skipids already handle, so those
    commands need no change. -tags together with -ids means the games that are in both. Returns False when nothing is left to do
    (or nothing can be decided); an empty selection must never fall through as 'all games'."""
    tags, skiptags = list(args.tags or []), list(args.skiptags or [])
    if not tags and not skiptags:
        return True
    items = load_manifest()
    selection = select_games_by_tags(items, tags, skiptags)
    for what, why, message in selection.problems:
        error(message)
        run_report.fail(what, why)
    if selection.fatal:
        return False
    if tags:
        chosen = set(selection.selected)
        if args.ids:
            resolved = resolve_game_ids(items, args.ids, '-ids')
            report_id_resolution(resolved)
            chosen &= resolved.selected
        chosen -= selection.skipped
        if not chosen:
            warn('no game matches the tag(s) {%s}%s' % (', '.join(tags), ' and -ids' if args.ids else ''))
            return False
        info('-tags {%s}%s: %d game(s)' % (', '.join(tags), ' with -ids' if args.ids else '', len(chosen)))
        args.ids = [str(game_id) for game_id in sorted(chosen, key=str)]
    if skiptags:
        info('-skiptags {%s}: skipping %d game(s)' % (', '.join(skiptags), len(selection.skipped)))
        args.skipids = list(args.skipids or []) + [str(game_id) for game_id in sorted(selection.skipped, key=str)]
    return True


# --- the list command ---
def _display_width(text):
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in text)


def _fit(text, width):
    """The text, cut to a width on the screen (Chinese, Japanese and Korean characters are two wide), ending in ... if cut."""
    if _display_width(text) <= width:
        return text
    kept, used = '', 0
    for char in text:
        if used + _display_width(char) > width - 3:
            break
        kept, used = kept + char, used + _display_width(char)
    return kept + '...'


def _pad(text, width, right=False):
    gap = ' ' * max(0, width - _display_width(text))
    return gap + text if right else text + gap


LIST_OS_NAMES = {'windows': 'win', 'linux': 'lin', 'mac': 'mac'}


def cmd_list(words, os_list, skipos_list, lang_list, skiplang_list, output_format='table'):
    """Shows the games in the manifest, or the ones that match the words. Needs no login and no network."""
    items = load_manifest()
    wanted_langs = set(LANG_TABLE[lang] for lang in lang_list)
    skipped_langs = set(LANG_TABLE[lang] for lang in skiplang_list)
    code_of = dict((name, code) for code, name in LANG_TABLE.items())
    filtered = bool(os_list or skipos_list or lang_list or skiplang_list)

    def passes(entry):
        return ((not os_list or entry.os_type in os_list) and entry.os_type not in skipos_list
                and (not lang_list or entry.lang in wanted_langs) and entry.lang not in skipped_langs)

    files_of, candidates = {}, []
    for game in items:
        installers = [e for kind in ('downloads', 'galaxyDownloads', 'sharedDownloads') for e in getattr(game, kind, [])
                      if passes(e)]
        if filtered and not installers:
            continue
        files_of[id(game)] = (installers, list(getattr(game, 'extras', [])))
        candidates.append(game)
    found = search_games(candidates, words)
    if not found:
        shown = ' '.join(words)
        filter_text = '; '.join(part for part in ('-os ' + ' '.join(os_list) if os_list else '', '-skipos ' + ' '.join(skipos_list) if skipos_list else '',
                                                  '-lang ' + ' '.join(lang_list) if lang_list else '', '-skiplang ' + ' '.join(skiplang_list) if skiplang_list else '') if part)
        filter_note = ' The filter in use is: %s (typed, or the defaults from the config file).' % filter_text if filter_text else ''
        if words:
            hidden = search_games(items, words) if filtered else []        # the games the words fit, before the filter took some out
            if hidden:
                names = ', '.join(game.title for game in hidden[:5]) + (' and %d more' % (len(hidden) - 5) if len(hidden) > 5 else '')
                error("%d game%s match%s '%s' (%s) but none has files for the chosen operating system / language.%s"
                      % (len(hidden), '' if len(hidden) == 1 else 's', 'es' if len(hidden) == 1 else '', shown, names, filter_note))
                run_report.fail('list %s' % shown, 'no matching game has files for this operating system / language')
            else:
                suggestions = suggest_games(items, shown)
                error("no game matches '%s'.%s" % (shown, ' Did you mean: %s?' % '; '.join(describe_game(g) for g in suggestions)
                                                  if suggestions else ''))
                run_report.fail('list %s' % shown, 'no game matches')
        elif filtered:
            error('no game has files for this operating system / language.%s' % filter_note)
            run_report.fail('list', 'no game has files for this operating system / language')
        else:
            info('the manifest has no games')
        return
    if output_format == 'ids':
        for game in found:
            print(game.title)
    else:
        rows = []
        for game in found:
            installers, extras = files_of[id(game)]
            everything = installers + extras
            rows.append((str(game.id), game.title, getattr(game, 'long_title', game.title),
                         ','.join(LIST_OS_NAMES.get(o, o) for o in sorted(set(e.os_type for e in installers))) or '-',
                         ','.join(sorted(code_of.get(l, l) for l in set(e.lang for e in installers))) or '-',
                         str(len(everything)), pretty_size(sum(getattr(e, 'size', 0) or 0 for e in everything))))
        header = ('ID', 'TITLE', 'NAME', 'OS', 'LANG', 'FILES', 'SIZE')
        widths = [max(_display_width(r[i]) for r in rows + [header]) for i in range(7)]
        if sys.stdout.isatty():                                      # on a screen: make it fit (the name first, then the title)
            room = shutil.get_terminal_size((120, 24)).columns - 1 - 2 * 6
            for column in (2, 1):
                over = sum(widths) - room
                if over > 0:
                    widths[column] = max(12, widths[column] - over)
        for row in [header] + rows:
            cells = [_pad(_fit(row[i], widths[i]), widths[i], right=i in (0, 5, 6)) for i in range(7)]
            print('  '.join(cells).rstrip())
    info('%d of %d games' % (len(found), len(items)))


def build_parser():
    """All commands and flags. Returns (parser, the sub-parsers by command name)."""
    p1 = GogArgumentParser(description='%s (%s)' % (__appname__, __url__), add_help=False)
    sp1 = p1.add_subparsers(help='command', dest='command', title='commands')
    sp1.required = True

    g1 = sp1.add_parser('login', help='Login to GOG ( using a GOG or Galaxy Account only ) and save a local copy of your authenticated token')
    g1.add_argument('username', action='store', help='GOG username/email', nargs='?', default=None)
    g1.add_argument('password', action='store', help='GOG password (deprecated: visible in shell history and process lists, omit it to be prompted securely)', nargs='?', default=None)
    g1.add_argument('-browser', action='store_true', help="sign in with a web browser instead of with a user name and password typed here: use this when GOG shows a captcha or the automatic login stops working. The sign-in page is opened (or its address is shown), and you paste the address the browser ends up on. Username and password are not used.")
    add_common_flags(g1)


    g1 = sp1.add_parser('update', help='Update locally saved game manifest from GOG server')
    g1.add_argument('-resumemode',action="store",choices=['noresume','resume','onlyresume'],default='resume',help="how to handle resuming if necessary")
    g1.add_argument('-strictverify',action="store_true",help="clear previously verified unless md5 match")
    g1.add_argument('-strictdupe',action="store_true",help="missing MD5s do not default to checking only file size (missing MD5s only match other missing MD5s rather than any value)")
    g1.add_argument('-lenientdownloadsupdate',action="store_false",help="Does not mark installers for updating, even if size and name match,  if the last updated time has changed and MD5s are not available or do not match")
    g1.add_argument('-strictextrasupdate',action="store_true",help="Marks extras for updating, even if size and name match,  if the last updated time has changed and MD5s are not available or do not match  ")
    g1.add_argument('-md5xmls',action="store_true",help="Downloads the MD5 XML files for each item (where available) and outputs them to " + MD5_DIR_NAME)
    g1.add_argument('-nochangelogs',action="store_true",help="Skips saving the changelogs for games")
    g2 = g1.add_mutually_exclusive_group()
    g2.add_argument('-os', action='extend', help="operating system(s) (default: the operating system of this computer)", nargs='*', default=[])
    g2.add_argument('-skipos', action='store', help='skip operating system(s)', nargs='*', default=[])
    g3 = g1.add_mutually_exclusive_group()
    g3.add_argument('-lang', action='extend', help="game language(s) (default: the language of your system, en if unknown)", nargs='*', default=[])
    g3.add_argument('-skiplang', action='store', help='skip game language(s)', nargs='*', default=[])
    g1.add_argument('-skiphidden',action='store_true',help='skip games marked as hidden')
    g1.add_argument('-installers', action='store', choices = ['standalone','both'], default = 'standalone',  help='GOG Installer type to use: standalone or both galaxy and standalone. Default: standalone (Deprecated)')
    g4 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g4.add_argument('-standard', action='store_true', help='new and updated games only (default unless -ids used)')
    g4.add_argument('-skipknown', action='store_true', help='skip games already known by manifest')
    g4.add_argument('-updateonly', action='store_true', help='only games marked with the update tag')
    g4.add_argument('-full', action='store_true', help='all games on your account (default if -ids used)')
    g5 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g5.add_argument('-ids', action='store', help='id(s)/titles(s) of (a) specific game(s) to update', nargs='*', default=[])
    g5.add_argument('-skipids', action='store', help='id(s)/titles(s) of (a) specific game(s) not to update', nargs='*', default=[])
    g1.add_argument('-tags', action='store', help='only the games with one of these tags of your GOG library (any of them); with -ids: the games in both', nargs='*', default=[])
    g1.add_argument('-skiptags', action='store', help='skip the games with one of these tags of your GOG library', nargs='*', default=[])
    g1.add_argument('-wait', action='store', type=float,
                    help='wait this long in hours before starting', default=0.0)  # sleep in hr
    g1.add_argument('-diagnostic', action='store_true', help = "More exhaustively probes GOG for data in preparation for the diagnostics command. This causes slower updates and will generate more warning messages. ")
    add_common_flags(g1)


    g1 = sp1.add_parser('download', help='Download all your GOG games and extra files')
    g1.add_argument('savedir', action='store', help='directory to save downloads to', nargs='?', default=GAME_STORAGE_DIR)
    g1.add_argument('-dryrun', action='store_true', help='display, but skip downloading of any files')
    g1.add_argument('-skipgalaxy', action='store_true', help='skip downloading Galaxy installers (Deprecated)' )
    g1.add_argument('-skipstandalone', action='store_true', help='skip downloading standlone installers (Deprecated)')
    g1.add_argument('-skipshared', action = 'store_true', help ='skip downloading installers shared between Galaxy and standalone (Deprecated)')
    g2 = g1.add_mutually_exclusive_group()
    g2.add_argument('-skipextras', action='store_true', help='skip downloading of any GOG extra files')
    g2.add_argument('-skipgames', action='store_true', help='skip downloading of any GOG game files (deprecated, use -skipgalaxy -skipstandalone -skipshared instead)')
    g3 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g3.add_argument('-ids', action='store', help='id(s) or title(s) of the game in the manifest to download', nargs='*', default=[])
    g3.add_argument('-skipids', action='store', help='id(s) or title(s) of the game(s) in the manifest to NOT download', nargs='*', default=[])
    g1.add_argument('-tags', action='store', help='only the games with one of these tags of your GOG library (any of them); with -ids: the games in both', nargs='*', default=[])
    g1.add_argument('-skiptags', action='store', help='skip the games with one of these tags of your GOG library', nargs='*', default=[])
    g3.add_argument('-id', action='store', help='(deprecated) id or title of the game in the manifest to download')
    g1.add_argument('-covers', action='store_true', help='downloads cover images for each game')
    g1.add_argument('-backgrounds', action='store_true', help='downloads background images for each game')
    g1.add_argument('-nocleanimages', action='store_true', help='delete rather than clean old background/cover images for each game')
    g1.add_argument('-skipfiles', action='store', help='file name (or glob patterns) to NOT download', nargs='*', default=[])
    g1.add_argument('-wait', action='store', type=float,
                    help='wait this long in hours before starting', default=0.0)  # sleep in hr
    g1.add_argument('-downloadlimit', action='store', type=float,
                    help='limit downloads to this many MB (approximately)', default=None)  # sleep in hr
    g4 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g4.add_argument('-skipos', action='store', help='skip downloading game files for operating system(s)', nargs='*', default=[])
    g4.add_argument('-os', action='extend', help="download game files only for operating system(s) (default: the operating system of this computer)", nargs='*', default=[])
    g5 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g5.add_argument('-lang', action='extend', help="download game files only for language(s) (default: the language of your system, en if unknown)", nargs='*', default=[])
    g5.add_argument('-skiplang', action='extend', help='skip downloading game files for language(s)', nargs='*', default=[])
    g1.add_argument('-skippreallocation',action='store_true',help='do not preallocate space for files')
    g1.add_argument('-noblake3', action='store_true', help='do not record a BLAKE3 checksum for each downloaded file (needs the optional blake3 package)')
    add_common_flags(g1)



    g1 = sp1.add_parser('import', help='Import files with any matching MD5 checksums found in manifest')
    g1.add_argument('src_dir', action='store', help='source directory to import games from')
    g1.add_argument('dest_dir', action='store', help='directory to copy and name imported files to')
    g2 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g2.add_argument('-skipos', action='store', help='skip importing game files for operating system(s)', nargs='*', default=[])
    g2.add_argument('-os', action='store', help="import game files only for operating system(s) (default: the operating system of this computer)", nargs='*', default=[])
    g3 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g3.add_argument('-skiplang', action='store', help='skip importing game files for language(s)', nargs='*', default=[])
    g3.add_argument('-lang', action='store', help="import game files only for language(s) (default: the language of your system, en if unknown)", nargs='*', default=[])
    #Code path available but commented out and hardcoded as false due to lack of MD5s on extras.
    #g4 = g1.add_mutually_exclusive_group()
    #g4.add_argument('-skipextras', action='store_true', help='skip downloading of any GOG extra files')
    #g4.add_argument('-skipgames', action='store_true', help='skip downloading of any GOG game files (deprecated, use -skipgalaxy -skipstandalone -skipshared instead)')
    add_common_flags(g1)
    g1.add_argument('-skipgalaxy', action='store_true', help='skip downloading Galaxy installers')
    g1.add_argument('-skipstandalone', action='store_true', help='skip downloading standlone installers')
    g1.add_argument('-skipshared', action = 'store_true', help ='skip downloading installers shared between Galaxy and standalone')
    g5 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g5.add_argument('-ids', action='store', help='id(s) or title(s) of the game in the manifest to import', nargs='*', default=[])
    g5.add_argument('-skipids', action='store', help='id(s) or title(s) of the game(s) in the manifest to NOT import', nargs='*', default=[])
    g1.add_argument('-tags', action='store', help='only the games with one of these tags of your GOG library (any of them); with -ids: the games in both', nargs='*', default=[])
    g1.add_argument('-skiptags', action='store', help='skip the games with one of these tags of your GOG library', nargs='*', default=[])


    g1 = sp1.add_parser('backup', help='Perform an incremental backup to specified directory')
    g1.add_argument('src_dir', action='store', help='source directory containing gog items')
    g1.add_argument('dest_dir', action='store', help='destination directory to backup files to')
    g5 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g5.add_argument('-ids', action='store', help='id(s) or title(s) of the game in the manifest to backup', nargs='*', default=[])
    g5.add_argument('-skipids', action='store', help='id(s) or title(s) of the game(s) in the manifest to NOT backup', nargs='*', default=[])
    g1.add_argument('-tags', action='store', help='only the games with one of these tags of your GOG library (any of them); with -ids: the games in both', nargs='*', default=[])
    g1.add_argument('-skiptags', action='store', help='skip the games with one of these tags of your GOG library', nargs='*', default=[])
    g2 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g2.add_argument('-skipos', action='store', help='skip backup of game files for operating system(s)', nargs='*', default=[])
    g2.add_argument('-os', action='store', help="backup game files only for operating system(s) (default: the operating system of this computer)", nargs='*', default=[])
    g3 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g3.add_argument('-skiplang', action='store', help='skip backup of game files for language(s)', nargs='*', default=[])
    g3.add_argument('-lang', action='store', help="backup game files only for language(s) (default: the language of your system, en if unknown)", nargs='*', default=[] )
    g4 = g1.add_mutually_exclusive_group()
    g4.add_argument('-skipextras', action='store_true', help='skip backup of any GOG extra files')
    g4.add_argument('-skipgames', action='store_true', help='skip backup of any GOG game files')
    g1.add_argument('-skipgalaxy',action='store_true', help='skip backup of any GOG Galaxy installer files')
    g1.add_argument('-skipstandalone',action='store_true', help='skip backup of any GOG standalone installer files')
    g1.add_argument('-skipshared',action='store_true',help ='skip backup of any installers included in both the GOG Galalaxy and Standalone sets')
    add_common_flags(g1)


    g1 = sp1.add_parser('verify', help='Scan your downloaded GOG files and verify their size, MD5, and zip integrity')
    g1.add_argument('gamedir', action='store', help='directory containing games to verify', nargs='?', default=GAME_STORAGE_DIR)
    g1.add_argument('-permissivechangeclear', action='store_true', help='clear change marking for files that pass this test (default is to only clear on MD5 match) ')
    g1.add_argument('-forceverify', action='store_true', help='also verify files that are unchanged (by gogrepo) since they were last successfully verified')
    g1.add_argument('-skipmd5', action='store_true', help='do not perform MD5 check')
    g1.add_argument('-skipsize', action='store_true', help='do not perform size check')
    g1.add_argument('-skipzip', action='store_true', help='do not perform zip integrity check')
    g1.add_argument('-noblake3', action='store_true', help='do not record or compare BLAKE3 checksums (they need the optional blake3 package)')
    g7 = g1.add_mutually_exclusive_group()
    g7.add_argument('-highmemory', action='store_true', help='use in memory file to test multi-part zip files (instead of temporary file). At least 50 GB of unused memory is recommended to use this.')
    g7.add_argument('-lowtmpspace', action='store_true', help='do not test multi-part zip archives (due to not having enough space for a temporary file). Recommended if tmp file location has less than 50 GB of free space. ')
    g2 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g2.add_argument('-delete', action='store_true', help='delete any files which fail integrity test')
    g2.add_argument('-noclean', action='store_true', help='leave any files which fail integrity test in place')
    g2.add_argument('-clean', action='store_true', help='(deprecated) This is now the default behaviour and this option is provided only to maintain backwards compatibility with existings scripts')
    g3 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g3.add_argument('-ids', action='store', help='id(s) or title(s) of the game in the manifest to verify', nargs='*', default=[])
    g3.add_argument('-skipids', action='store', help='id(s) or title(s) of the game[s] in the manifest to NOT verify', nargs='*', default=[])
    g1.add_argument('-tags', action='store', help='only the games with one of these tags of your GOG library (any of them); with -ids: the games in both', nargs='*', default=[])
    g1.add_argument('-skiptags', action='store', help='skip the games with one of these tags of your GOG library', nargs='*', default=[])
    g3.add_argument('-id', action='store', help='(deprecated) id or title of the game in the manifest to verify')
    g1.add_argument('-skipfiles', action='store', help='file name (or glob patterns) to NOT verify', nargs='*', default=[])
    g4 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g4.add_argument('-skipos', action='store', help='skip verification of game files for operating system(s)', nargs='*', default=[])
    g4.add_argument('-os', action='store', help="verify game files only for operating system(s) (default: the operating system of this computer)", nargs='*', default=[])
    g5 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g5.add_argument('-skiplang', action='store', help='skip verification of game files for language(s)', nargs='*', default=[])
    g5.add_argument('-lang', action='store', help="verify game files only for language(s) (default: the language of your system, en if unknown)", nargs='*', default=[])
    g6 = g1.add_mutually_exclusive_group()
    g6.add_argument('-skipextras', action='store_true', help='skip verification of any GOG extra files')
    g6.add_argument('-skipgames', action='store_true', help='skip verification of any GOG game files')
    g1.add_argument('-skipgalaxy',action='store_true', help='skip verification of any GOG Galaxy installer files')
    g1.add_argument('-skipstandalone',action='store_true', help='skip verification of any GOG standalone installer files')
    g1.add_argument('-skipshared',action='store_true',help ='skip verification of any installers included in both the GOG Galalaxy and Standalone sets')

    add_common_flags(g1)


    g1 = sp1.add_parser('list', help='List the games in your manifest, or search them by words; shows the titles and ids to use with -ids')
    g1.add_argument('words', action='store', nargs='*', default=[], help='words to look for in the id, title and name of the games (all of them must be found, in any order); without words all games are listed. Put the words before the options: an option like -os takes everything after it as its values')
    g4 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g4.add_argument('-skipos', action='store', help='leave out games that only have files for operating system(s)', nargs='*', default=[])
    g4.add_argument('-os', action='store', help='only games that have files for operating system(s) (default: all)', nargs='*', default=[])
    g5 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g5.add_argument('-skiplang', action='store', help='leave out games that only have files for language(s)', nargs='*', default=[])
    g5.add_argument('-lang', action='store', help='only games that have files for language(s) (default: all)', nargs='*', default=[])
    g1.add_argument('-format', action='store', choices=['table', 'ids'], default='table', help='table (default), or ids: only the title of each game, one per line, for scripts')
    add_common_flags(g1)

    g1 = sp1.add_parser('export', help='Write the manifest as a spreadsheet (CSV file), one row per file, to see what your library contains')
    g1.add_argument('-output', action='store', default='gog-library.csv', help='file to write (default: gog-library.csv)')
    g1.add_argument('-savedir', action='store', default=None, help='also check which of the files exist in this game directory (adds an "on disk" column)')
    g1.add_argument('-delimiter', action='store', default=None, help="column separator; default is ';' for most languages (what their Excel expects) and ',' for English, Japanese, Chinese, Korean, Thai and Hebrew")
    add_common_flags(g1)

    g1 = sp1.add_parser('wishlist', help='Save your GOG wishlist (titles, store links, optionally prices) and show what changed since the last run')
    g1.add_argument('-output', action='store', default=WISHLIST_FILENAME, help='file to save the wishlist to, and to compare with the next time (default: %s)' % WISHLIST_FILENAME)
    g1.add_argument('-csv', action='store', nargs='?', const=WISHLIST_CSV_FILENAME, default=None, metavar='FILE', help='also write the wishlist as a spreadsheet (CSV file) to this file (default file name: %s)' % WISHLIST_CSV_FILENAME)
    g1.add_argument('-prices', action='store_true', help='also fetch the price of every game (one more request per game)')
    g1.add_argument('-country', action='store', default=None, help='two-letter country code the prices are for, like DE, GB or US (default: US)')
    g1.add_argument('-currency', action='store', default=None, help='currency to show when GOG gives several for the country, like EUR (default: the first one)')
    g1.add_argument('-delimiter', action='store', default=None, help="column separator of the CSV file; default is ';' for most languages (what their Excel expects) and ',' for English, Japanese, Chinese, Korean, Thai and Hebrew")
    add_common_flags(g1)

    g1 = sp1.add_parser('clean', help='Clean your games directory of files not known by manifest')
    g1.add_argument('cleandir', action='store', help='root directory containing gog games to be cleaned')
    g1.add_argument('-dryrun', action='store_true', help='do not move files, only display what would be cleaned')
    add_common_flags(g1)

    g1 = sp1.add_parser('clear_partial_downloads', help='Permanently remove all partially downloaded files from your game directory')
    g1.add_argument('gamedir', action='store', help='root directory containing gog games')
    g1.add_argument('-dryrun', action='store_true', help='do not move files, only display what would be cleaned')
    add_common_flags(g1)


    g1 = sp1.add_parser('trash', help='Permanently remove orphaned files in your game directory (removes only strict (matching file size and MD5 hash) duplicates of game files unless other parameters are set)')
    g1.add_argument('gamedir', action='store', help='root directory containing gog games')
    g1.add_argument('-dryrun', action='store_true', help='do not move files, only display what would be trashed')

    g1.add_argument('-installersonly', action='store_true', help='(Deprecated) Currently an alias for -installers')
    g1.add_argument('-folders', action='store_true', help='also deletes orphaned game folders (other options are permitted but redundant) that have a corresponding game folder. If -relaxed a corresponding game folder is not required.')
    g1.add_argument('-installers', action='store_true', help='also delete file types used as installers even if they are not duplicates.')
    g1.add_argument('-images', action='store_true', help='also delete !images subfolders that have a corresponding !images subfolder. If -relaxed a corresponding game is not required.' )
    g1.add_argument('-relaxed', action='store_true', help = 'more relaxed about what to delete. Does not verify an existing file is a true match before deleting. May effect other parameters, as detailed by them.')
    add_common_flags(g1)

    g1 = sp1.add_parser('diagnostics', help='Outputs diagnostic data for script maintenance & reports, only fully works if data is properly generated by appropriate update')
    g1.add_argument('-verbose', action='store_true', help = 'Outputs additional data that is not usually useful ( eg things behaving in a way that is expecteced if not optimal )')

    add_common_flags(g1)


    g1 = p1.add_argument_group('other')
    g1.add_argument('-h', '--help', action='help', help='show help message and exit')
    g1.add_argument('-v', '--version', action='version', help='show version number and exit',
                    version="%s (version %s)" % (__appname__, __version__))

    return p1, sp1


# ---------------------------------------------------------------------------------------------
# Config file: defaults for the command-line flags, and creating the file
# ---------------------------------------------------------------------------------------------
CONFIG_NOT_ALLOWED = (('login', 'username'), ('login', 'password'), ('list', 'words'))   # never read from the file (a password does not belong there)
CONFIG_BOOLEAN_WORDS = {'true': True, 'yes': True, 'on': True, '1': True, 'false': False, 'no': False, 'off': False, '0': False}


def _is_switch(action):
    return isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction))


def _is_list(action):
    return action.nargs in ('*', '+')


def config_options(subparser, command):
    """The actions of a command that can be set in the config file."""
    return [a for a in subparser._actions
            if not isinstance(a, (argparse._HelpAction, argparse._VersionAction)) and (command, a.dest) not in CONFIG_NOT_ALLOWED]


def parse_flag_value(action, text):
    """The value a config entry gives to a flag, or None if the entry says nothing (empty, or a switch set to false).
    Raises ValueError (with the reason) if the text cannot be used."""
    text = text.strip()
    if not text:
        return None
    if _is_switch(action):
        word = text.lower()
        if word not in CONFIG_BOOLEAN_WORDS:
            raise ValueError('%r is not yes or no (use true/false, yes/no, on/off or 1/0)' % text)
        return action.const if CONFIG_BOOLEAN_WORDS[word] else None
    if _is_list(action):
        items = text.split('\n') if '\n' in text else text.split(',')     # one item per line, or separated by commas
        return [item.strip() for item in items if item.strip()] or None
    convert = action.type or str
    try:
        value = convert(text)
    except (ValueError, TypeError):
        raise ValueError('%r is not %s' % (text, 'a number' if convert is float else 'a whole number' if convert is int else 'valid'))
    if action.choices and value not in action.choices:
        raise ValueError('%r is not one of: %s' % (text, ', '.join(str(c) for c in action.choices)))
    return value


def _explicit_dests(argv, build):
    """The names of the options and arguments that were really typed on the command line (not their defaults).
    Parses the line once more with a parser that has no defaults and whose arguments are all optional."""
    probe, probe_commands = build()
    for sub in probe_commands.choices.values():
        for action in sub._actions:
            if isinstance(action, (argparse._HelpAction, argparse._VersionAction)):
                continue
            if not action.option_strings and action.nargs is None:       # a required argument: may be left out (the config can fill it in)
                action.nargs, action.required = '?', False
            action.default = argparse.SUPPRESS
    return vars(probe.parse_args(argv[1:]))


def apply_config_flags(parser, commands, config, argv, path=None, build=None):
    """Makes the entries of the config file the defaults of the flags of the command being run. A flag typed on the command
    line always wins over the config file; so does a mutually exclusive partner of such a flag (config 'os' is dropped when
    -skipos is typed). Returns (notes, problems): what was set, and messages about entries that were ignored.
    Raises ConfigError for an entry that cannot be used."""
    path = path or user_config_path()
    explicit = _explicit_dests(argv, build or build_parser)
    command = explicit.get('command')
    problems, notes = [], []
    for section in config.sections():
        if section not in ('settings', 'common') and section not in commands.choices:
            problems.append("config file %s: [%s] is not a command, ignored (sections: settings, common, %s)"
                            % (path, section, ', '.join(commands.choices)))
    if command not in commands.choices:
        return notes, problems
    sub = commands.choices[command]
    options = config_options(sub, command)
    known = set(a.dest for a in options)
    everywhere = set(a.dest for name, other in commands.choices.items() for a in config_options(other, name))
    if config.has_section('common'):
        for key in config.options('common'):
            if key not in everywhere:       # [common] applies to the commands that have the option; the others ignore it
                problems.append("config file %s: [common] has no option '%s' (no command has it), ignored" % (path, key))
    if config.has_section(command):
        for key in config.options(command):
            if key not in known:
                problems.append("config file %s: [%s] has no option '%s' for the command %s, ignored" % (path, command, key, command))
    # a flag typed on the command line also switches off the config entries of the flags it excludes
    blocked = set(explicit)
    for group in sub._mutually_exclusive_groups:
        dests = set(a.dest for a in group._group_actions)
        if dests & blocked:
            blocked |= dests
    chosen = []
    for action in options:
        if action.dest in blocked:
            continue
        text = None
        for section in ('common', command):          # the command's own section beats [common]
            if config.has_option(section, action.dest) and config.get(section, action.dest).strip():
                text = config.get(section, action.dest)
                where = section
        if text is None:
            continue
        try:
            value = parse_flag_value(action, text)
        except ValueError as e:
            raise ConfigError('config file %s: [%s] %s = %s: %s%s' % (path, where, action.dest, text.strip(), e,
                                                                    ' (for the command %s)' % command if where == 'common' else ''))
        if value is not None:
            chosen.append((action, value, where))
    for group in sub._mutually_exclusive_groups:
        members = [c for c in chosen if c[0] in group._group_actions]
        if any(where == command for action, value, where in members):
            # an entry in the command's own section replaces the [common] entries of the options it excludes
            chosen = [c for c in chosen if not any(c is m and m[2] == 'common' for m in members)]
            members = [m for m in members if m[2] == command]
        if len(members) > 1:
            raise ConfigError('config file %s: [%s] %s cannot be used together (they exclude each other)'
                              % (path, command, ' and '.join(m[0].dest for m in members)))
    for action, value, where in chosen:
        if not action.option_strings:                # a required argument that the config file can fill in
            action.nargs, action.required = '?', False
        elif value == action.default:
            continue                                 # says what the program does anyway: nothing to report
        action.default = list(value) if isinstance(value, list) else value
        notes.append('%s=%s' % (action.dest, ','.join(value) if isinstance(value, list) else value))
    return notes, problems


# Short descriptions for the generated config file: (the commands it is for, or None for all of them, the options and their texts).
# Options that belong together share one comment; a comment is written once, where the option first appears, and the same option in
# later sections is listed without it. An option whose meaning differs between commands has an entry for each meaning.
CONFIG_NOTES = [
    (None, (('nolog', 'do not write the log file gogrepo.log'),
            ('debug', 'include debug messages'))),
    (None, (('manifestformat', 'format the manifest is saved in: json (fast, readable in a text editor) or legacy (the original '
                               'format, for other gogrepo versions); both can always be read'),)),
    (None, (('browser', 'sign in with a web browser instead of typing a user name and password here (use it when GOG shows a '
                        'captcha); you paste the address the browser ends up on'),)),
    (None, (('resumemode', 'how to handle resuming if necessary'),)),
    (None, (('strictverify', "clear 'verified' marks unless the MD5 matches"),
            ('strictdupe', 'missing MD5s only match other missing MD5s, not any value (instead of comparing only the file size)'))),
    (None, (('lenientdownloadsupdate', 'if size and name match but only the update time changed and MD5s are missing or '
                                       'different, do not mark installers for update'),
            ('strictextrasupdate', 'same situation, but do mark extras for update'))),
    (None, (('md5xmls', 'also download the MD5 XML files to !md5_xmls'),
            ('nochangelogs', 'do not save changelogs'))),
    (None, (('os', 'operating systems to include (default: the one of this computer; for list: all)'),
            ('skipos', 'operating systems to skip'))),
    (None, (('lang', 'game languages to include (default: the language of your system, en if unknown; for list: all)'),
            ('skiplang', 'game languages to skip'))),
    (None, (('skiphidden', 'skip games marked as hidden'),)),
    (('update',), (('installers', 'installer type to use (deprecated)'),)),
    (None, (('standard', 'new and updated games only (default unless ids are given)'),
            ('skipknown', 'skip games already in the manifest'),
            ('updateonly', 'only games marked with the update tag'),
            ('full', 'all games of your account (default if ids are given)'))),
    (None, (('ids', 'games to include, by id or title'),
            ('skipids', 'games to skip, by id or title'))),
    (None, (('tags', 'only games with one of these tags of your GOG library (update stores the tags in the manifest)'),
            ('skiptags', 'skip games with one of these tags'))),
    (None, (('wait', 'wait this many hours before starting'),)),
    (None, (('diagnostic', 'probe GOG more thoroughly for the diagnostics command (slower, more warnings)'),)),
    (None, (('savedir', 'folder the games are saved in (export: also checks which files exist there and adds an "on disk" column)'),)),
    (None, (('dryrun', 'only show what would be done: no files are downloaded or moved'),)),
    (None, (('skipgalaxy', 'skip Galaxy installers (deprecated for download)'),
            ('skipstandalone', 'skip standalone installers (deprecated for download)'),
            ('skipshared', 'skip installers shared by Galaxy and standalone (deprecated for download)'),
            ('skipextras', 'skip extra files'),
            ('skipgames', 'skip all game files (deprecated for download: use the three above)'))),
    (None, (('id', '(deprecated) one game by id or title: use ids'),)),
    (None, (('covers', 'download cover images'),
            ('backgrounds', 'download background images'),
            ('nocleanimages', 'delete old cover and background images instead of cleaning them'))),
    (None, (('skipfiles', 'file names or glob patterns to skip'),)),
    (None, (('downloadlimit', 'limit downloads to about this many MB'),
            ('skippreallocation', 'do not preallocate space for files'))),
    (('wishlist',), (('csv', 'also write the wishlist as a spreadsheet (CSV file) to this file (gog-wishlist.csv if no file name is given)'),
                     ('prices', 'also fetch the price of every game'),
                     ('country', 'two-letter country code the prices are for (default US)'),
                     ('currency', 'currency to show when GOG gives several for the country, like EUR'))),
    (('import',), (('src_dir', 'folder to import games from'),
                   ('dest_dir', 'folder to copy and name the imported files to'))),
    (('backup',), (('src_dir', 'folder containing the GOG items to back up'),
                   ('dest_dir', 'folder to back the files up to'))),
    (None, (('gamedir', 'root folder containing the GOG games'),)),
    (None, (('permissivechangeclear', 'clear the change mark of files that pass the test (default: only when the MD5 matches)'),
            ('forceverify', 'also verify files unchanged since their last successful verification'))),
    (None, (('skipmd5', 'do not check the MD5'),
            ('skipsize', 'do not check the size'),
            ('skipzip', 'do not check zip integrity'),
            ('noblake3', 'do not record or compare BLAKE3 checksums (optional blake3 package)'))),
    (None, (('highmemory', 'test multi-part zips in memory instead of a temporary file (at least 50 GB of unused memory advised)'),
            ('lowtmpspace', 'do not test multi-part zips (advised when the temp location has less than 50 GB free)'))),
    (None, (('delete', 'delete files that fail the integrity test'),
            ('noclean', 'leave files that fail the test in place'),
            ('clean', '(deprecated) now the default'))),
    (None, (('output', 'file to write'),
            ('delimiter', "column separator (default ';'; ',' for English, Japanese, Chinese, Korean, Thai and Hebrew)"))),
    (None, (('cleandir', 'root folder containing the GOG games to clean'),)),
    (('trash',), (('installers', 'also delete file types used as installers even if they are not duplicates'),)),
    (None, (('installersonly', '(deprecated) alias for installers'),)),
    (None, (('folders', 'also delete orphaned game folders that have a corresponding game folder'),
            ('images', 'also delete !images subfolders that have a corresponding !images subfolder'),
            ('relaxed', 'be more relaxed: no corresponding folder is needed and files are not verified as true matches before '
                        'deleting'))),
    (None, (('format', 'how list shows the games: a table, or just the title of each one per line'),)),
    (None, (('verbose', 'output additional data that is usually not useful'),)),
]


def _option_kind(action):
    """What an option is, as far as a config entry is concerned: a yes/no switch, a list, or a single value (with its type, the
    values it allows and, for an option, its default). Whether it is typed as an option or as an argument, and how argparse
    stores it, does not matter."""
    if _is_switch(action):
        return ('switch', action.const, action.default)
    if _is_list(action):
        return ('list',)
    default = repr(action.default) if action.option_strings and action.default is not None else None
    return ('value', action.type, tuple(action.choices or ()), default)


def shared_options(commands):
    """{option: [commands that have it]} for the options that the generated file lists once, in [common]: options that two or
    more commands have, that are of the same kind (type, values, default) and that mean the same thing in each (the same
    note in CONFIG_NOTES). An option that means something else in another command (installers, src_dir, dest_dir) stays in the
    sections of its commands."""
    seen = {}
    for command, sub in commands.choices.items():
        for action in config_options(sub, command):
            seen.setdefault(action.dest, []).append((command, action))
    shared = {}
    for dest, occurrences in seen.items():
        if len(occurrences) < 2:
            continue
        notes, kinds = set(), set()
        for command, action in occurrences:
            found = _note_for(command, dest)
            notes.add(found[0] if found else ('help', dest, action.help))
            kinds.add(_option_kind(action))
        if len(notes) == 1 and len(kinds) == 1:
            shared[dest] = [command for command, action in occurrences]
    return shared


def _wrapped_comment(text):
    return textwrap.fill(text, width=100, initial_indent='; ', subsequent_indent=';   ')


def _template_value(action):
    if not action.option_strings or _is_switch(action) or _is_list(action) or action.default is None:
        return 'false' if _is_switch(action) else ''
    return str(action.default)


def _note_for(section, dest):
    """(entry number, the texts of that entry) for an option in a section, or None if there is no note for it."""
    for number, (commands, members) in enumerate(CONFIG_NOTES):
        if (commands is None or section in commands) and dest in [m[0] for m in members]:
            return number, members
    return None


def _first_sentence(text):
    text = ' '.join((text or '').split())
    return re.split(r'(?<=[a-z\)])\. ', text)[0].rstrip('.')


def _section_lines(section, actions, explained, note_sections=None):
    """The lines of one section: related options together under one comment, options explained earlier without a comment.
    `explained` is shared by all sections (what has been explained already). `note_sections` says, for the options of [common],
    which command's note to use."""
    by_dest = dict((a.dest, a) for a in actions)
    lines, written = [], set()
    for action in actions:
        if action.dest in written:
            continue
        found = _note_for((note_sections or {}).get(action.dest, section), action.dest)
        if found:
            number, members = found
            group = [(d, t) for d, t in members if d in by_dest and d not in written]
        else:
            number = ('help', action.dest, action.help)       # no note for this option: the original help text, shortened
            group = [(action.dest, _first_sentence(action.help))]
        new = [(d, t) for d, t in group if (number, d) not in explained]
        if new:
            texts = []
            for d, t in new:
                choices = by_dest[d].choices
                if choices and not all(str(c) in t for c in choices):
                    t += ' [%s]' % '|'.join(str(c) for c in choices)
                texts.append(t)
            # one option: "name: text"; several that belong together: "name: text; name: text" (each part says whose it is)
            lines.append(_wrapped_comment('; '.join('%s: %s' % (d, t) for (d, _), t in zip(new, texts))))
        for d, t in group:
            lines.append('%s = %s' % (d, _template_value(by_dest[d])))
            written.add(d)
            explained.add((number, d))
    return lines


def default_config_text(commands):
    """The text of a new config file: every setting with its default, every option of every command, briefly explained."""
    lines = [_wrapped_comment(text) for text in (
        'gogrepo_delta settings and default options. Delete this file to get a fresh one; the values below are the built-in '
        'defaults.',
        '[common] holds the options that several commands have (os, lang, ids, dryrun, ...): set one there and it counts for every '
        'command that has it. A [command] section holds the options only that command has; it may also repeat an option from '
        '[common] to change it for that command alone.',
        'Order of precedence: typed on the command line, then the [command] section, then [common], then the built-in default. '
        'An empty value means "not set". An entry for os, lang or ids counts as typed. Passwords are never read from here.',
        'Yes/no options: true/false (true = as if typed; a typed option cannot switch it off, so set it to false here). '
        'Lists (os, lang, ids, ...): separate the entries with commas (not with spaces or semicolons), or write one per line, '
        'indented. Folders: give all folders of a command here, or none.',
        'Lower case: write the section names ([common], [update], ...) and the values of os and lang (windows, linux, mac; en, de, '
        '...) in lower case; option names may be written in any case.',
        'Comments go on their own line, never after a value.')]
    lines += ['', '[settings]']
    for keys, text in SETTING_GROUPS:
        lines.append(_wrapped_comment(text))
        for key in keys:
            kind, default = SETTING_KEYS[key][1], SETTING_KEYS[key][2]
            lines.append('%s = %s' % (key, format_setting(kind, default)))
    explained = set()
    shared = shared_options(commands)
    common, first_command = [], {}
    for command, sub in commands.choices.items():
        for action in config_options(sub, command):
            if action.dest in shared and action.dest not in first_command:
                first_command[action.dest] = command
                common.append(action)
    lines += ['', '[common]'] + _section_lines('common', common, explained, first_command)
    for command, sub in commands.choices.items():
        options = [a for a in config_options(sub, command) if a.dest not in shared]
        if options:          # a command that has nothing of its own gets no section; its options are in [common]
            lines += ['', '[%s]' % command] + _section_lines(command, options, explained)
    return '\n'.join(lines) + '\n'


def ensure_config_file():
    """Creates the config file, from scratch, if there is none. Returns True if it was created."""
    path = user_config_path()
    if os.path.exists(path):
        return False
    text = default_config_text(build_parser()[1])
    previous = consoleHandler.setStream(sys.stderr)       # not on stdout: the command that follows may write a list there
    try:
        try:
            atomic_write_text(path, lambda w: w.write(text))
        except OSError as e:
            warn('no config file %s found and a new one could not be written (%s); the built-in defaults are used', path, e)
            return False
        info('no config file found: created %s with all settings and options at their defaults (edit it to change them)', path)
        return True
    finally:
        consoleHandler.setStream(previous)



def version_line():
    """The first line of a run in the log: the version of the program, and the Python and system it ran on."""
    return '%s version %s (Python %s, %s)' % (__appname__, __version__, platform.python_version(), platform.platform())


def process_argv(argv):
    p1, sp1 = build_parser()
    config_notes, config_problems = [], []
    if not any(a in ('-h', '--help', '-v', '--version') for a in argv[1:]):     # help and version never depend on the config file
        try:
            config = read_user_config()
            if config is not None and config.sections():
                config_notes, config_problems = apply_config_flags(p1, sp1, config, argv)
        except ConfigError as e:
            error('error: %s', e)
            raise SystemExit(1)

    # parse the given argv.  raises SystemExit on error
    args = p1.parse_args(argv[1:])

    if not args.nolog:
        rootLogger.addHandler(loggingHandler)
        # The first line of the run in the log file (not on the console): which version of the program wrote it.
        loggingHandler.handle(rootLogger.makeRecord(rootLogger.name, logging.INFO, __file__, 0, version_line(), (), None))

    if not args.debug:
        rootLogger.setLevel(logging.INFO)

    for problem in config_problems:
        warn(problem)
    if config_notes:
        info('defaults from the config file %s: %s', user_config_path(), ', '.join(config_notes))

    if args.command in ('update', 'download', 'backup', 'import', 'verify', 'list'):
        validate_lang_and_os(args)

    return args

# --------
# Commands
# --------
def galaxy_auth_args():
    """Query string of GOG's Galaxy sign-in page. Used by the automatic login and by -browser."""
    return {'client_id': GOG_CLIENT_ID, 'redirect_uri': GOG_GALAXY_REDIRECT_URL + '?origin=client', 'response_type': 'code', 'layout': 'client2'}

def galaxy_auth_url():
    """The full address of GOG's sign-in page, to open in a browser. Builds the address only, no request is made."""
    return requests.Request('GET', GOG_AUTH_URL, params=galaxy_auth_args()).prepare().url

def login_form_has_captcha(login_form):
    """True if GOG's login form (an element tree node) asks for a captcha, in either form it has been seen in:
    the Google reCAPTCHA box, or the captcha field list (newer login page)."""
    return (len(login_form.findall('.//div[@class="g-recaptcha form__recaptcha"]')) > 0
            or len(login_form.findall('.//ol[@class="form__fieldset form__fieldset--captcha"]')) > 0)

def login_code_from_url(url):
    """The code= value of the address a browser ends up on after signing in (.../on_login_success?...&code=...),
    or None if there is none."""
    try:
        codes = parse_qs(urlparse(url.strip()).query).get('code')
    except (AttributeError, ValueError):
        return None
    return codes[0] if codes and codes[0] else None

def ask_for_signed_in_url():
    """Asks for the address of the page the browser ended up on after signing in. Returns the login code or None."""
    try:
        inputUrl = input("Signed In URL: ")
    except EOFError:
        error("There is no terminal to type the address into. Run the login command in a terminal.")
        return None
    login_code = login_code_from_url(inputUrl)
    if login_code is None:
        error("Could not parse entered URL (it must contain code=..., like https://embed.gog.com/on_login_success?origin=client&code=...). Try again later or report to the maintainer")
    return login_code

def browser_login():
    """Sign-in in a web browser (used when -browser is given): no password is typed into this program, so a captcha,
    changed login page or any other sign-in method GOG offers on its web page is handled by the browser.
    Returns the login code, or None."""
    auth_url = galaxy_auth_url()
    info("Browser login: you sign in on GOG's own page, this program never sees your password.")
    try:
        opened = webbrowser.open(auth_url)
    except Exception:
        opened = False
    if opened:
        info("Your browser should open now. If it did not, open this address yourself:")
    else:
        info("Could not open a browser automatically. Open this address in a browser yourself:")
    info(auth_url)
    info("Sign in there. Afterwards the browser ends up on an address that starts with " + GOG_GALAXY_REDIRECT_URL + " (the page may look empty or show an error, that is fine).")
    info("Copy the complete address from the browser's address bar and paste it below.")
    return ask_for_signed_in_url()

def _login_with_password(loginSession, token_data):
    """The automatic login: user name and password (and the two-step code if GOG asks for it).
    Returns the login code, or None if the login did not work (the reason has been logged).
    If GOG asks for a captcha, the person signs in with a browser and pastes the address."""
    # fetch the auth url
    info("attempting Galaxy login as '{}' ...".format(token_data['user']))

    page_response = request(loginSession,GOG_AUTH_URL,args=galaxy_auth_args())
    # fetch the login token
    etree = html5lib.parse(page_response.text, namespaceHTMLElements=False)
    # Bail if we find a request for a reCAPTCHA *in the login form*
    loginForm = etree.find('.//form[@name="login"]')
    if (loginForm is None) or login_form_has_captcha(loginForm):
        if loginForm is None:
            error("Could not locate login form on login page to test for reCAPTCHA, please contact the maintainer. In the meantime use a browser (Firefox recommended) to sign in at the below url and then copy & paste the full URL")
        else:
            error("gog is asking for a reCAPTCHA :(  Please use a browser (Firefox recommended) to sign in at the below url and then copy & paste the full URL")
        error(page_response.url)
        error("(or run the login command again with -browser to have the page opened for you)")
        token_data['login_code'] = ask_for_signed_in_url()
        if not token_data['login_code']:
            return None
    for elm in etree.findall('.//input'):
        if elm.attrib.get('id') == 'login__token':
            token_data['login_token'] = elm.attrib['value']
            break

    if not token_data['login_code']:

        # perform login and capture two-step token if required
        page_response = request(loginSession,GOG_LOGIN_URL, data={'login[username]': token_data['user'],
                                                   'login[password]': token_data['passwd'],
                                                   'login[login]': '',
                                                   'login[_token]': token_data['login_token']})
        etree = html5lib.parse(page_response.text, namespaceHTMLElements=False)
        if 'totp' in page_response.url:
            token_data['totp_url'] = page_response.url
            for elm in etree.findall('.//input'):
                if elm.attrib['id'] == 'two_factor_totp_authentication__token':
                    token_data['totp_token'] = elm.attrib['value']
                    break
        elif 'two_step' in page_response.url:
            token_data['two_step_url'] = page_response.url
            for elm in etree.findall('.//input'):
                if elm.attrib['id'] == 'second_step_authentication__token':
                    token_data['two_step_token'] = elm.attrib['value']
                    break
        elif 'on_login_success' in page_response.url:
            parsed = urlparse(page_response.url)
            query_parsed = parse_qs(parsed.query)
            token_data['login_code'] = query_parsed['code']


        # perform two-step if needed
        if token_data['totp_url'] is not None:
            token_data['totp_security_code'] = input("enter Authenticator security code: ")

            # Send the security code back to GOG
            page_response= request(loginSession,token_data['totp_url'],
                         data={'two_factor_totp_authentication[token][letter_1]': token_data['totp_security_code'][0],
                               'two_factor_totp_authentication[token][letter_2]': token_data['totp_security_code'][1],
                               'two_factor_totp_authentication[token][letter_3]': token_data['totp_security_code'][2],
                               'two_factor_totp_authentication[token][letter_4]': token_data['totp_security_code'][3],
                               'two_factor_totp_authentication[token][letter_5]': token_data['totp_security_code'][4],
                               'two_factor_totp_authentication[token][letter_6]': token_data['totp_security_code'][5],
                               'two_factor_totp_authentication[send]': "",
                               'two_factor_totp_authentication[_token]': token_data['totp_token']})
            if 'on_login_success' in page_response.url:
                parsed = urlparse(page_response.url)
                query_parsed = parse_qs(parsed.query)
                token_data['login_code'] = query_parsed['code']

        elif token_data['two_step_url'] is not None:
            token_data['two_step_security_code'] = input("enter two-step security code: ")

            # Send the security code back to GOG
            page_response= request(loginSession,token_data['two_step_url'],
                         data={'second_step_authentication[token][letter_1]': token_data['two_step_security_code'][0],
                               'second_step_authentication[token][letter_2]': token_data['two_step_security_code'][1],
                               'second_step_authentication[token][letter_3]': token_data['two_step_security_code'][2],
                               'second_step_authentication[token][letter_4]': token_data['two_step_security_code'][3],
                               'second_step_authentication[send]': "",
                               'second_step_authentication[_token]': token_data['two_step_token']})
            if 'on_login_success' in page_response.url:
                parsed = urlparse(page_response.url)
                query_parsed = parse_qs(parsed.query)
                token_data['login_code'] = query_parsed['code']

    if not token_data['login_code']:
        error('Galaxy login failed, verify your username/password and try again.')
        return None
    return token_data['login_code']

def _save_login_token(loginSession, login_code):
    """Swaps the login code for a token and saves it. Returns True if the token was saved."""
    token_start = time.time()
    try:
        token_response = request(loginSession,GOG_TOKEN_URL,args={'client_id':GOG_CLIENT_ID ,'client_secret':GOG_SECRET, 'grant_type': 'authorization_code','code': login_code,'redirect_uri': GOG_GALAXY_REDIRECT_URL + '?origin=client'})
        token_json = token_response.json()
        token_json['expiry'] = token_start + token_json['expires_in']
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        error('GOG did not give a token for this login (%s). A login code can only be used once and only for a short time, so please sign in again and paste the address right away.', e)
        return False
    save_token(token_json)
    return True

def cmd_login(user, passwd, browser=False):
    """Attempts to log into GOG Galaxy API and saves the resulting Token to disk.
    With browser=True the person signs in with a web browser instead of typing a password here.
    Returns True if a token was saved, False if not.
    """

    if browser:
        if user is not None or passwd is not None:
            warn("-browser: the username and password you gave are not used, you sign in on the GOG web page instead.")
        login_code = browser_login()
        if not login_code:
            return False
        return _save_login_token(makeGOGSession(True), login_code)

    login_data = {'user': user,
                  'passwd': passwd,
                  'auth_url': None,
                  'login_token': None,
                  'two_step_url': None,
                  'two_step_token': None,
                  'two_step_security_code': None,
                  'login_success': None
                  }


    # A password given on the command line is still honoured for existing
    # scripts, but it is exposed in shell history and process listings.
    if login_data['passwd'] is not None:
        warn("Passing the password on the command line is deprecated and insecure (it is visible in shell history and process lists). Omit it to be prompted without echo.")

    # prompt for login/password if needed
    if ( login_data['user'] is None ) or ( login_data['passwd'] ) is None:
        print("You must use a GOG or GOG Galaxy account, Google/Discord sign-ins are not currently supported.")
    if login_data['user'] is None:
        login_data['user'] = input("Username: ")
    if login_data['passwd'] is None:
        login_data['passwd'] = getpass.getpass("Password: ")

    token_data = {'user': login_data['user'],
                  'passwd': login_data['passwd'],
                  'auth_url': None,
                  'login_token': None,
                  'totp_url': None,
                  'totp_token': None,
                  'totp_security_code': None,
                  'two_step_url': None,
                  'two_step_token': None,
                  'two_step_security_code': None,
                  'login_code':None
                  }




    loginSession = makeGOGSession(True)

    login_code = _login_with_password(loginSession, token_data)
    if not login_code:
        return False
    return _save_login_token(loginSession, login_code)

def makeGitHubSession(authenticatedSession=False):
    gitSession = requests.Session()
    gitSession.headers={'User-Agent':USER_AGENT,'Accept':'application/vnd.github.v3+json'}
    return gitSession

def makeGOGSession(loginSession=False):
    gogSession = requests.Session()
    if not loginSession:
        gogSession.token = load_token()
        try:
            gogSession.headers={'User-Agent':USER_AGENT,'Authorization':'Bearer ' + gogSession.token['access_token']}
        except (KeyError, AttributeError):
            error('failed to find valid token (Please login and retry)')
            sys.exit(1)
    return gogSession

# Token storage defaults to password-protected AES-256-GCM. Set GOGREPO_TOKEN_MODE=plain
# explicitly for unattended machines; this writes readable JSON and is not encrypted.
TOKEN_MODE_ENV = 'GOGREPO_TOKEN_MODE'
_TOKEN_PASSWORD = None
_TOKEN_ENVELOPE_FORMAT = 'gogrepo-token'
_TOKEN_ENVELOPE_VERSION = 1
_TOKEN_SCRYPT_N = 2 ** 14
_TOKEN_SCRYPT_R = 8
_TOKEN_SCRYPT_P = 1


def _token_mode():
    mode = os.environ.get(TOKEN_MODE_ENV, 'encrypted').strip().lower()
    if mode not in ('encrypted', 'plain'):
        raise ValueError('%s must be "encrypted" or "plain"' % TOKEN_MODE_ENV)
    return mode


def _token_crypto():
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise RuntimeError('Encrypted token storage requires the "cryptography" package. Install it with: python -m pip install cryptography')
    return AESGCM


TOKEN_PASSWORD_ATTEMPTS = 3        # how often a wrong password is asked for again when someone is there to type it


class TokenPasswordError(ValueError):
    """The token file could not be decrypted with the passwords that were typed (or it is damaged)."""


def _forget_token_password():
    global _TOKEN_PASSWORD
    _TOKEN_PASSWORD = None


def _can_prompt_again():
    """True when the program is run from a terminal, so that asking for the password again makes sense (not in a scheduled task or a pipe)."""
    try:
        return bool(sys.stdin and sys.stdin.isatty())
    except (AttributeError, ValueError):
        return False


def _token_password(create=False):
    """Ask once per process; never persist the password or accept it on the command line."""
    global _TOKEN_PASSWORD
    if _TOKEN_PASSWORD is None:
        if create:
            first = getpass.getpass('Create password for gog-token.json: ')
            second = getpass.getpass('Confirm token password: ')
            if not first:
                raise ValueError('Token password must not be empty')
            if first != second:
                raise ValueError('Token passwords do not match')
            _TOKEN_PASSWORD = first
        else:
            typed = getpass.getpass('Password for gog-token.json: ')
            if not typed:                   # Refactoring: the empty answer used to stay in _TOKEN_PASSWORD, so a second call did not ask again
                raise ValueError('Token password must not be empty')
            _TOKEN_PASSWORD = typed
    return _TOKEN_PASSWORD


def _token_key(password, salt, n=_TOKEN_SCRYPT_N, r=_TOKEN_SCRYPT_R, p=_TOKEN_SCRYPT_P):
    return hashlib.scrypt(password.encode('utf-8'), salt=salt, n=n, r=r, p=p, dklen=32)


def _write_token_json(token, filepath):
    mode = _token_mode()
    envelope = {
        'format': _TOKEN_ENVELOPE_FORMAT,
        'version': _TOKEN_ENVELOPE_VERSION,
        'encryption': mode,
    }
    if mode == 'plain':
        envelope['token'] = token
    else:
        AESGCM = _token_crypto()
        salt = os.urandom(16)
        nonce = os.urandom(12)
        password = _token_password(create=not os.path.exists(filepath))
        key = _token_key(password, salt)
        ciphertext = AESGCM(key).encrypt(nonce, json.dumps(token, separators=(',', ':')).encode('utf-8'),
                                         _TOKEN_ENVELOPE_FORMAT.encode('ascii'))
        envelope.update({
            'kdf': 'scrypt',
            'kdf_n': _TOKEN_SCRYPT_N,
            'kdf_r': _TOKEN_SCRYPT_R,
            'kdf_p': _TOKEN_SCRYPT_P,
            'salt': __import__('base64').b64encode(salt).decode('ascii'),
            'nonce': __import__('base64').b64encode(nonce).decode('ascii'),
            'ciphertext': __import__('base64').b64encode(ciphertext).decode('ascii'),
        })
    atomic_write_text(filepath, lambda w: json.dump(envelope, w, indent=2, sort_keys=True), mode=0o600)


def _read_token_json(filepath):
    with open(filepath, mode='r', encoding='utf-8') as r:
        envelope = json.load(r)
    if not isinstance(envelope, dict) or envelope.get('format') != _TOKEN_ENVELOPE_FORMAT:
        raise ValueError('unrecognised token file format in %s' % filepath)
    if envelope.get('version') != _TOKEN_ENVELOPE_VERSION:
        raise ValueError('unsupported token file version in %s' % filepath)
    encryption = envelope.get('encryption')
    if encryption == 'plain':
        token = envelope.get('token')
    elif encryption == 'encrypted':
        if envelope.get('kdf') != 'scrypt':
            raise ValueError('unsupported token key derivation function')
        AESGCM = _token_crypto()
        import base64
        salt = base64.b64decode(envelope['salt'], validate=True)
        nonce = base64.b64decode(envelope['nonce'], validate=True)
        ciphertext = base64.b64decode(envelope['ciphertext'], validate=True)
        if len(salt) != 16 or len(nonce) != 12:
            raise ValueError('invalid encrypted token parameters')
        # A wrong (or empty) password is asked for again, up to TOKEN_PASSWORD_ATTEMPTS times, if there is a terminal; otherwise one attempt.
        attempts = TOKEN_PASSWORD_ATTEMPTS if _can_prompt_again() else 1
        for attempt in range(1, attempts + 1):
            try:
                password = _token_password()
            except ValueError:                                  # nothing was typed
                if attempt == attempts:
                    raise
                error('The password must not be empty. Please try again (%d of %d).' % (attempt, attempts))
                continue
            key = _token_key(password, salt, int(envelope['kdf_n']), int(envelope['kdf_r']), int(envelope['kdf_p']))
            try:
                plaintext = AESGCM(key).decrypt(nonce, ciphertext, _TOKEN_ENVELOPE_FORMAT.encode('ascii'))
                break
            except Exception:
                _forget_token_password()                        # the wrong one must not be kept and used again
                if attempt == attempts:
                    # Do not fall back to the legacy token file on a bad password or damaged ciphertext.
                    raise TokenPasswordError('could not decrypt token file (wrong password or damaged file)')
                error('Wrong password. Please try again (%d of %d).' % (attempt, attempts))
        token = json.loads(plaintext.decode('utf-8'))
    else:
        raise ValueError('unsupported token encryption mode: %r' % encryption)
    if not isinstance(token, dict):
        raise ValueError('token file does not contain a JSON object')
    return token


def save_token(token):
    info('saving token...')
    filepath = TOKEN_FILENAME
    try:
        _write_token_json(token, filepath)
        info('saved token')
    except KeyboardInterrupt:
        _write_token_json(token, filepath)
        info('saved token')
        raise


def load_token(filepath=None):
    """Read the new JSON token first; read the legacy .dat file only when JSON is absent."""
    info('loading token...')
    if filepath is not None:
        # Explicit paths are useful to callers/tests and refer to the new JSON format.
        try:
            return _read_token_json(filepath)
        except FileNotFoundError:
            return {}
    if os.path.exists(TOKEN_FILENAME):
        # A corrupt or undecryptable JSON file is an error, never a reason to use stale legacy data.
        return _read_token_json(TOKEN_FILENAME)
    if os.path.exists(LEGACY_TOKEN_FILENAME):
        with open(LEGACY_TOKEN_FILENAME, mode='r', encoding='utf-8') as r:
            legacy = _load_legacy_literal(r.read())
        if not isinstance(legacy, dict):
            raise ValueError('legacy token file does not contain a dictionary')
        # Migration writes only the new file; the legacy file is left untouched.
        save_token(legacy)
        return legacy
    return {}

def input_timeout(*ignore):
    raise TimeoutError



class UpdateNarrowing(object):
    """What an update with these operating-system and language lists would take out of the manifest (see update_narrowing)."""
    def __init__(self):
        self.files = 0             # installer entries that no longer fit
        self.games = 0             # in this many games
        self.os_types = set()      # entries dropped because of their operating system
        self.languages = set()     # entries dropped because of their language


def update_narrowing(gamesdb, os_list, lang_list, lang_fallback, ids, skipids):
    """The installer entries in the manifest that an update with these lists would drop, for the games it could fetch (all of them, or the
    ones named by ids, without skipids). An update replaces the installers of every game it fetches by the ones for the chosen operating
    systems and languages, with the same filter that it uses (filter_languages, with the English fallback of the default language);
    extras are not filtered by an update, so they do not count."""
    result = UpdateNarrowing()
    if not gamesdb or not os_list or not lang_list:
        return result
    valid_langs = [LANG_TABLE[lang] for lang in lang_list]
    fallback_name = LANG_TABLE[lang_fallback] if lang_fallback else None
    games = gamesdb
    if ids:
        selected = resolve_game_ids(gamesdb, ids).selected
        games = [game for game in games if game.id in selected]
    if skipids:
        skipped = resolve_game_ids(gamesdb, skipids).selected
        games = [game for game in games if game.id not in skipped]
    for game in games:
        dropped = []
        for kind in ('downloads', 'galaxyDownloads', 'sharedDownloads'):
            entries = getattr(game, kind, [])
            kept = set(id(entry) for entry in filter_languages([e for e in entries if e.os_type in os_list], valid_langs, fallback_name))
            dropped += [entry for entry in entries if id(entry) not in kept]
        if dropped:
            result.games += 1
            result.files += len(dropped)
            for entry in dropped:
                if entry.os_type not in os_list:
                    result.os_types.add(entry.os_type)
                else:
                    result.languages.add(entry.lang)
    return result


def warn_if_update_narrows_manifest(gamesdb, os_list, lang_list, lang_fallback, ids, skipids, partial):
    """Warns (only warns) when the update that is about to start would remove installer entries for other operating systems or
    languages from the manifest. The files stay on disk, but 'clean' would take them for orphans, and a later update that includes
    them adds the entries back as new ones, which download then has to check again (it does not download them again if they are right)."""
    found = update_narrowing(gamesdb, os_list, lang_list, lang_fallback, ids, skipids)
    if not found.files:
        return
    reasons = ' and '.join(part for part in (
        'operating system(s) %s' % ', '.join(sorted(found.os_types)) if found.os_types else '',
        'language(s) %s' % ', '.join(sorted(found.languages)) if found.languages else '') if part)
    warn('This update is limited to operating system(s) %s and language(s) %s, but the manifest also holds %s%d installer file(s) of %d game(s) '
         'for %s.' % (', '.join(os_list), ', '.join(lang_list), 'up to ' if partial else '', found.files, found.games, reasons))
    warn('For %s these entries are removed from the manifest. The files stay on disk, but \'clean\' would move them to %s, and a later update that '
         'includes them again has them added back as new entries (download then checks them, and fetches only what is not right).'
         % ('the games that this update fetches (the new and updated ones, or the ones named with -ids)' if partial
            else 'every game that this update fetches (all games, or the ones named with -ids)', ORPHAN_DIR_NAME))
    warn('If that is not what you want, stop now (Ctrl-C) and run update again with all the operating systems and languages that you use '
         '(-os, -lang), or put them into the config file.')


def cmd_update(os_list, lang_list, skipknown, updateonly, partial, ids, skipids,skipHidden,installers,resumemode,strict,strictDupe,strictDownloadsUpdate,strictExtrasUpdate,md5xmls,noChangeLogs,diagnostic,lang_fallback=None,tags=None,skiptags=None):
    media_type = GOG_MEDIA_TYPE_GAME
    tags, skiptags = list(tags or []), list(skiptags or [])    # entry 39: -tags / -skiptags (names of the tags of your GOG library)
    tag_wanted, tag_unwanted = tag_keys(tags), tag_keys(skiptags)
    tag_filter = bool(tags or skiptags)
    known_tag_keys, tags_refreshed, pages_complete, tag_skipped_count = set(), 0, False, 0
    items = []
    known_ids = []
    known_titles = []
    i = 0

    api_url  = GOG_ACCOUNT_URL
    api_url += "/getFilteredProducts"


    gamesdb = load_manifest()
    save_partial = partial
    save_skipknown = skipknown
    save_updateonly = updateonly

    if not gamesdb and not skipknown and not updateonly:
        partial = False;

    if partial:
        skipknown = True;
        updateonly = True;

    updateSession = makeGOGSession()

    try:
        resumedb = load_resume_manifest()
        resumeprops = resumedb.pop()
        needresume = resumemode != "noresume" and not resumeprops['complete']
        try:
            resume_manifest_syntax_version = resumeprops['resume_manifest_syntax_version']
        except KeyError:
            resume_manifest_syntax_version = -1
        if resume_manifest_syntax_version != RESUME_MANIFEST_SYNTAX_VERSION:
            warn('Incompatible Resume Manifest Version Detected.')
            if resumeprops['complete']:
                warn('Incompatible Resume Manifest Has Already Been Completed And Will Be Automatically Discarded')
                resumedb = None
                needresume = False
            else:
                inp = None

                while (inp not in ["D","d","A","a"]):
                    inp = input("(D)iscard incompatible manifest or (A)bort? (D/d/A/a): ")

                    if (inp in ["D","d"]):
                        warn("Discarding")
                        resumedb = None
                        needresume = False
                    elif (inp in ["A","a"]):
                        warn("Aborting")
                        sys.exit()
    except Exception:
        resumedb = None
        needresume = False

    if (needresume):
        info('incomplete update detected, resuming...')
        save_os_list = os_list
        os_list = resumeprops['os_list']
        save_lang_list = lang_list
        lang_list = resumeprops['lang_list']
        save_lang_fallback = lang_fallback
        lang_fallback = resumeprops.get('lang_fallback')   # old resume files have none: strict, as before
        save_installers = installers
        installers = resumeprops['installers']
        save_strict = strict
        strict = resumeprops['strict']
        save_strictDupe = strictDupe
        save_strictDownloadsUpdate = strictDownloadsUpdate
        save_strictExtrasUpdate = strictExtrasUpdate
        save_md5xmls = md5xmls
        save_noChangeLogs = noChangeLogs
        save_diagnostic = diagnostic
        try:
            partial = resumeprops['partial']
        except KeyError:
            pass
        try:
            skipknown = resumeprops['skipknown']
        except KeyError:
            pass
        try:
            updateonly = resumeprops['updateonly']
        except KeyError:
            pass
        try:
            strictDupe = resumeprops['strictDupe']
        except KeyError:
            strictDupe = True
        try:
           strictDownloadsUpdate = resumeprops['strictDownloadsUpdate']
        except KeyError:
            strictDownloadsUpdate = True
        try:
            strictExtrasUpdate = resumeprops['strictExtrasUpdate']
        except KeyError:
            strictExtrasUpdate = False
        try:
           md5xmls = resumeprops['md5xmls']
        except KeyError:
            md5xmls = True
        try:
            noChangeLogs = resumeprops['noChangeLogs']
        except KeyError:
            noChangeLogs = False
        try:
            diagnostic = resumeprops['diagnostic']
        except KeyError:
            diagnostic = False

        items = resumedb
        items_count = len(items)
        print_padding = len(str(items_count))

    else:
        # Make convenient list of known ids11
        for item in gamesdb:
            known_ids.append(item.id)

        idsOriginal = ids[:]

        for item in gamesdb:
            known_titles.append(item.title)

        narrow_ids, narrow_skipids = ids, skipids
        if tag_filter:      # the manifest's own tag data tells which games this update is likely to fetch
            guess = select_games_by_tags(gamesdb, tags, skiptags)
            if not guess.fatal:
                if guess.selected is not None and not ids:
                    narrow_ids = [str(game_id) for game_id in guess.selected] or ids
                narrow_skipids = list(skipids) + [str(game_id) for game_id in guess.skipped]
        warn_if_update_narrows_manifest(gamesdb, os_list, lang_list, lang_fallback, narrow_ids, narrow_skipids, partial)
        known_by_id = dict((game.id, game) for game in gamesdb)

        # Fetch shelf data
        done = False
        while not done:
            i += 1  # starts at page 1
            if i == 1:
                info('fetching game product data (page %d)...' % i)
            else:
                info('fetching game product data (page %d / %d)...' % (i, json_data['totalPages']))
            data_response = request(updateSession,api_url,args={'mediaType': media_type,'sortBy': 'title','page': str(i)})
#            with open("text.html","w+",encoding='utf-8') as f:
#                f.write(data_response.text)
            try:
                json_data = data_response.json()
            except ValueError:
                error('failed to load product data (are you still logged in?)')
                raise SystemExit(1)

            tag_map = tag_map_of(json_data)
            known_tag_keys.update(tag_key(name) for name in tag_map.values())
            # Parse out the interesting fields and add to items dict
            for item_json_data in json_data['products']:
                # skip games marked as hidden
                if skipHidden and (item_json_data.get('isHidden', False) is True):
                    continue

                item = AttrDict()
                item.id = item_json_data['id']
                item.title = item_json_data['slug']
                item.folder_name = item_json_data['slug']
                item.long_title = item_json_data['title']

                item.genre = item_json_data['category']
                item.image_url = item_json_data['image']
                #item.image_urls[item.long_title] = item_json_data['image']
                item.store_url = item_json_data['url']
                item.media_type = media_type
                item.rating = item_json_data['rating']
                item.has_updates = bool(item_json_data['updates'])
                item.old_title = None
                #mirror these so they appear at the top of the json entry
                item._title_mirror =  item.title
                item._long_title_mirror = item.long_title
                item._id_mirror =  item.id


                # entry 39: the tag names of this game; the manifest entry of a game that is not fetched again gets them too
                item.tag_names = product_tag_names(item_json_data, tag_map)
                known_game = known_by_id.get(item.id)
                if known_game is not None and getattr(known_game, 'tag_names', None) != item.tag_names:
                    known_game.tag_names = list(item.tag_names)
                    tags_refreshed += 1

                item.gog_data = AttrDict()
                for key in item_json_data:
                    try:
                        tmp_contents = item[key]
                        if tmp_contents != item_json_data[key]:
                            debug("GOG Data Key, %s , for item clashes with Item Data Key storing detailed info in secondary dict" % key)
                            item.gog_data[key] = item_json_data[key]
                    except Exception:
                        item[key] = item_json_data[key]


                if not done:
                    if item.title not in skipids and str(item.id) not in skipids:
                        if ids:
                            if (item.title  in ids or str(item.id) in ids):  # support by game title or gog id
                                info('scanning found "{}" in product data!'.format(item.title))
                                try:
                                    ids.remove(item.title)
                                except ValueError:
                                    try:
                                        ids.remove(str(item.id))
                                    except ValueError:
                                        warn("Somehow we have matched an unspecified ID. Huh ?")
                                if not ids:
                                    done = True
                            else:
                                continue


                        if tag_wanted and not game_has_any_tag(item, tag_wanted):
                            continue                # not one of the tagged games
                        if tag_unwanted and game_has_any_tag(item, tag_unwanted):
                            info('skipping "{}" (has a tag from -skiptags)'.format(item.title))
                            tag_skipped_count += 1
                            continue
                        if (not partial) or (updateonly and item.has_updates) or (skipknown and item.id not in known_ids):
                             items.append(item)
                    else:
                        info('skipping "{}" found in product data!'.format(item.title))


            if i >= json_data['totalPages']:
                done = True
                pages_complete = True


        if tags_refreshed:
            info('the tags of %d game(s) in the manifest were refreshed' % tags_refreshed)
            save_manifest(gamesdb)
        if pages_complete:
            for option, wanted in (('-tags', tags), ('-skiptags', skiptags)):
                for tag in wanted:
                    if tag_key(tag) and tag_key(tag) not in known_tag_keys:
                        error("%s '%s' is not a tag of your GOG library." % (option, tag))
                        run_report.fail('%s %s' % (option, tag), 'no such tag')

        if not idsOriginal and not tag_filter and not updateonly and not skipknown:     # a run limited by -ids or tags never removes games
            validIDs = [item.id for item in items]
            invalidItems = [itemID for itemID in known_ids if itemID not in validIDs and str(itemID) not in skipids]
            if len(invalidItems) != 0:
                warn('old games in manifest. Removing ...')
                for item in invalidItems:
                    warn('Removing id "{}" from manifest'.format(item))
                    item_idx = item_checkdb(item, gamesdb)
                    if item_idx is not None:
                        del gamesdb[item_idx]

        if ids and not updateonly and not skipknown:
            invalidTitles = [id for id in ids if id in known_titles]
            invalidIDs = [int(id) for id in ids if is_numeric_id(id) and int(id) in known_ids]
            invalids = invalidIDs + invalidTitles
            if invalids:
                formattedInvalids =  ', '.join(map(str, invalids))
                warn(' game id(s) from {%s} were in your manifest but not your product data ' % formattedInvalids)
                titlesToIDs = [(game.id,game.title) for game in gamesdb if game.title in invalidTitles]
                for invalidID in invalidIDs:
                    warn('Removing id "{}" from manifest'.format(invalidID))
                    item_idx = item_checkdb(invalidID, gamesdb)
                    if item_idx is not None:
                        del gamesdb[item_idx]
                for invalidID,invalidTitle in titlesToIDs:
                    warn('Removing id "{}" from manifest'.format(invalidTitle))
                    item_idx = item_checkdb(invalidID, gamesdb)
                    if item_idx is not None:
                        del gamesdb[item_idx]
                save_manifest(gamesdb)


        # bail if there's nothing to do
        if len(items) == 0:
            if partial:
                warn('no new game or updates found.')
            elif updateonly:
                warn('no new game updates found.')
            elif skipknown:
                warn('no new games found.')
            else:
                warn('nothing to do')
            if idsOriginal:
                formattedIds =  ', '.join(map(str, idsOriginal))
                warn('with game id(s) from {%s}' % formattedIds)
            return


        items_count = len(items)
        print_padding = len(str(items_count))
        if tag_filter:
            info('limited by tags: %d game(s) selected%s' % (items_count, ', %d skipped by -skiptags' % tag_skipped_count if skiptags else ''))
        if not idsOriginal and not tag_filter and not updateonly and not skipknown:
            info('found %d games !!%s' % (items_count, '!'*int(items_count/100)))  # teehee
            if skipids:
                formattedSkipIds =  ', '.join(map(str, skipids))
                info('not including game id(s) from {%s}' % formattedSkipIds)


    # fetch item details
    i = 0
    resumedb = sorted(items, key=lambda item: item.title)
    resumeprop = {'resume_manifest_syntax_version':RESUME_MANIFEST_SYNTAX_VERSION,'os_list':os_list,'lang_list':lang_list,'lang_fallback':lang_fallback,'installers':installers,'strict':strict,'complete':False,'skipknown':skipknown,'partial':partial,'updateonly':updateonly,'strictDupe':strictDupe,'strictDownloadsUpdate':strictDownloadsUpdate,'strictExtrasUpdate':strictExtrasUpdate,'md5xmls':md5xmls,'noChangeLogs':noChangeLogs,'diagnostic':diagnostic}
    resumedb.append(resumeprop)
    save_resume_manifest(resumedb)

    resumedbInitLength = len(resumedb)
    try:
        for item in sorted(items, key=lambda item: item.title):
            api_url  = GOG_ACCOUNT_URL
            api_url += "/gameDetails/{}.json".format(item.id)



            i += 1
            info("(%*d / %d) fetching game details for %s..." % (print_padding, i, items_count, item.title))

            processed_successfully = False
            try:
                response = request(updateSession,api_url)

                item_json_data = response.json()

                item.bg_url = item_json_data['backgroundImage']
                item.bg_urls = AttrDict()
                if urlparse(item.bg_url).path != "":
                    item.bg_urls[item.long_title] = item.bg_url
                item.serial = item_json_data['cdKey']
                if (not(item.serial.isprintable())): #Probably encoded in UTF-16
                    pserial = item.serial
                    if (len(pserial) % 2): #0dd
                        pserial=pserial+"\x00"
                    pserial = bytes(pserial,"UTF-8")
                    pserial = pserial.decode("UTF-16")
                    if pserial.isprintable():
                        item.serial = pserial
                    else:
                        warn('Game serial code is unprintable, storing raw')
                item.serials = AttrDict()
                if item.serial != '':
                    item.serials[item.long_title] = item.serial
                item.used_titles = [item.long_title]
                item.forum_url = item_json_data['forumLink']
                if (noChangeLogs):
                    item_json_data['changelog'] = '' #Doing it this way prevents it getting stored as Detailed GOG Data later (which causes problems because it then lacks the changelog_end demarcation and becomes almost impossible to parse)
                item.changelog = item_json_data['changelog']
                item.changelog_end = None
                item.release_timestamp = item_json_data['releaseTimestamp']
                item.gog_messages = item_json_data['messages']
                item.downloads = []
                item.galaxyDownloads = []
                item.sharedDownloads = []
                item.extras = []
                item.detailed_gog_data = AttrDict()
                for key in item_json_data:
                    if key not in ["downloads","extras","galaxyDownloads","dlcs"]: #DLCS lose some info in processing, need to fix that when extending.  #This data is going to be stored after filtering (#Consider storing languages / OSes in case new ones are added)
                        try:
                            tmp_contents = item[key]
                            if tmp_contents != item_json_data[key]:
                                debug("Detailed GOG Data Key, %s , for item clashes with Item Data Key attempting to store detailed info in secondary dict" % key)
                                try:
                                    tmp_contents = item.gog_data[key]
                                    if tmp_contents != item_json_data[key]:
                                        debug("GOG Data Key, %s  ,for item clashes with Item Secondary Data Key storing detailed info in tertiary dict" % key)
                                        item.detailed_gog_data[key] = item_json_data[key]
                                except Exception:
                                    item.gog_data[key] = item_json_data[key]
                        except Exception:
                            item[key] = item_json_data[key]
                # parse json data for downloads/extras/dlcs
                product_api_context = AttrDict(product_id=item.id, download_links=None)
                downloads_dict = dict(item_json_data['downloads'])
                available_langs = list(downloads_dict.keys())
                available_os_types = dict()
                for available_lang in available_langs:
                        available_os_types[available_lang] =  list(downloads_dict[available_lang].keys())
                item.available_langs = AttrDict()
                item.available_langs[item.long_title] = available_langs
                item.available_os_types = AttrDict()
                item.available_os_types[item.long_title] = available_os_types
                filter_downloads(item.downloads, item_json_data['downloads'], lang_list, os_list,md5xmls,updateSession,product_api_context,diagnostic,lang_fallback)
                filter_downloads(item.galaxyDownloads, item_json_data['galaxyDownloads'], lang_list, os_list,md5xmls,updateSession,product_api_context,diagnostic,lang_fallback)
                filter_extras(item.extras, item_json_data['extras'],md5xmls,updateSession,product_api_context,diagnostic)
                filter_dlcs(item, item_json_data['dlcs'], lang_list, os_list,md5xmls,updateSession,product_api_context,diagnostic,lang_fallback)


                #Indepent Deduplication to make sure there are no doubles within galaxyDownloads or downloads to avoid weird stuff with the comprehention.
                item.downloads = deDuplicateList(item.downloads,{},strictDupe)
                item.galaxyDownloads = deDuplicateList(item.galaxyDownloads,{},strictDupe)

                item.sharedDownloads = [x for x in item.downloads if x in item.galaxyDownloads]
                if (installers=='galaxy'):
                    item.downloads = []
                else:
                    item.downloads = [x for x in item.downloads if x not in item.sharedDownloads]
                if (installers=='standalone'):
                    item.galaxyDownloads = []
                else:
                    item.galaxyDownloads = [x for x in item.galaxyDownloads if x not in item.sharedDownloads]

                existingItems = {}
                item.downloads = deDuplicateList(item.downloads,existingItems,strictDupe)
                item.galaxyDownloads = deDuplicateList(item.galaxyDownloads,existingItems,strictDupe)
                item.sharedDownloads = deDuplicateList(item.sharedDownloads,existingItems,strictDupe)
                item.extras = deDuplicateList(item.extras,existingItems,strictDupe)

                # update gamesdb with new item
                item_idx = item_checkdb(item.id, gamesdb)
                if item_idx is not None:
                    handle_game_updates(gamesdb[item_idx], item,strict, strictDownloadsUpdate, strictExtrasUpdate)
                    gamesdb[item_idx] = item
                    run_report.count('known games re-checked')
                else:
                    gamesdb.append(item)
                    run_report.count('new games added')
                processed_successfully = True
            except Exception as e:
                warn("The handled exception was:")
                log_exception('error')
                warn("End exception report.")
                run_report.fail(str(getattr(item, 'title', item)), "could not be fetched or processed: %s: %s" % (type(e).__name__, e))
            # Keep failed games in the resume manifest. They can then be retried
            # on the next invocation instead of silently being marked complete.
            if processed_successfully:
                resumedb.remove(item)
            # Refactoring: this used to save after EVERY game in the default (-standard/-updateonly/-skipknown)
            # modes. Every save re-formats the whole manifest, which takes seconds on a large library and is far
            # more than fetching one game's details, so all modes now save every RESUME_SAVE_THRESHOLD games.
            # Manifest and resume manifest are always saved together, so an interrupted run resumes cleanly.
            if (resumedbInitLength - len(resumedb)) % RESUME_SAVE_THRESHOLD == 0:
                save_manifest(gamesdb)
                save_resume_manifest(resumedb)
    except KeyboardInterrupt:
        # Refactoring: with batched saves, Ctrl-C would lose the games fetched since the last save.
        # Save them now (the atomic save leaves the old files intact if this is interrupted again).
        warn('interrupted - saving the games fetched so far (press Ctrl-C again to skip)')
        save_manifest(gamesdb)
        save_resume_manifest(resumedb)
        raise

    global_dupes = []
    sorted_gamesdb =  sorted(gamesdb, key = lambda game : game.title)
    for game in sorted_gamesdb:
        if game not in global_dupes:
            index = sorted_gamesdb.index(game)
            dupes = [game]
            while (len(sorted_gamesdb)-1 >= index+1 and sorted_gamesdb[index+1].title == game.title):
                dupes.append(sorted_gamesdb[index+1])
                index = index + 1
            if len(dupes) > 1:
                global_dupes.extend(dupes)

    for dupe in global_dupes:
        dupe.folder_name = dupe.title + "_" + str(dupe.id)
    #Store stuff in the DB in alphabetical order
    sorted_gamesdb =  sorted(gamesdb, key = lambda game : game.title)
    # save the manifest to disk
    save_manifest(sorted_gamesdb,update_md5_xml=md5xmls,delete_md5_xml=md5xmls)
    # The resume manifest is complete only when its only remaining entry is
    # the properties record. Failed game entries intentionally remain pending.
    resumeprop['complete'] = len(resumedb) == 1
    save_resume_manifest(resumedb)
    flush_summarised()
    if not resumeprop['complete']:
        pending_count = len(resumedb) - 1
        warn('%d game(s) could not be processed and remain in the resume manifest; run update again to retry them.' % pending_count)
    elif needresume:
        info('resume completed')
        if (resumemode != 'onlyresume'):
            info('returning to specified download request...')
            cmd_update(save_os_list, save_lang_list, save_skipknown, save_updateonly, save_partial, ids, skipids,skipHidden,save_installers,resumemode,save_strict,save_strictDupe,save_strictDownloadsUpdate,save_strictExtrasUpdate,save_md5xmls,save_noChangeLogs,save_diagnostic,lang_fallback=save_lang_fallback,tags=tags,skiptags=skiptags)

def cmd_output_diagnostic_data(verbose):
    gamesdb = load_manifest()
    output_diagnostic_data(gamesdb,verbose)

def output_diagnostic_data(sorted_gamesdb,verbose=False):
    known_languages = sorted(list(LANG_TABLE.values()))

    used_languages = []
    missing_galaxy_items = {}
    missing_md5s_expected = {}
    missing_md5s_unexpected = {}
    md5s_unexpected = {}
    extension_md5_count = {}
    extension_missing_md5_count = {}
    broken_links = {}
    strange_items = {}
    for game in sorted_gamesdb:
        game_missing_md5s_expected = {}
        game_missing_md5s_unexpected = {}
        game_md5s_unexpected = {}
        game_missing_galaxy_items = {}
        game_broken_links = []
        game_strange_items = {}
        for sub_item in game.get('available_langs') or {}:
            used_languages = list(set(used_languages + game.available_langs[sub_item]))
            for used_language in game.available_langs[sub_item]:
                if not ( used_language in known_languages):
                    info("Unknown language in manifest: " + used_language + " in game " + str(game.id) + " : " + game.title)
        for download in game.downloads + game.extras:
            if download.name:
                extension = os.path.splitext(download.name)[1].lower()
                if not extension_md5_count.get(extension):
                    extension_md5_count[extension] = 0
                if not extension_missing_md5_count.get(extension):
                    extension_missing_md5_count[extension] = 0
                if download.gog_data.get('api_downlink_fallback'):
                    game_missing_galaxy_items[download.name] = download.manualUrl
                    if not download.gog_data.get('api_downlink'):
                        game_strange_items[download.name] = download.manualUrl
                if not download.md5:
                    if extension in SKIP_MD5_FILE_EXT:
                        game_missing_md5s_expected[download.name] = download.manualUrl
                    else:
                        game_missing_md5s_unexpected[download.name] = download.manualUrl
                    extension_missing_md5_count[extension] += 1
                else:
                    if extension in SKIP_MD5_FILE_EXT:
                        game_md5s_unexpected[download.name] = download.manualUrl
                    extension_md5_count[extension] += 1
            elif not download.unreleased:
                game_broken_links.append((download.get('provisional_name'),download.manualUrl))
        if game_missing_galaxy_items:
            missing_galaxy_items[game.id] = (game.title,game_missing_galaxy_items)
        if game_missing_md5s_expected:
            missing_md5s_expected[game.id] = (game.title,game_missing_md5s_expected)
        if game_missing_md5s_unexpected:
            missing_md5s_unexpected[game.id] = (game.title,game_missing_md5s_unexpected)
        if game_md5s_unexpected:
            md5s_unexpected[game.id] = (game.title,game_md5s_unexpected)
        if game_broken_links:
            broken_links[game.id] = (game.title,game_broken_links)
        if game_strange_items:
            strange_items[game.id] = (game.title,game_strange_items)
    info('--')
    used_languages = sorted(used_languages)
    info('Languages used in your manifest:' + str(used_languages))
    info('--')
    if missing_galaxy_items:
        info("The following items are available to download on the GOG website but not the Galaxy Extras tab")
        for game_id in missing_galaxy_items:
            title, items = missing_galaxy_items[game_id]
            info("  From game: " +  title + " : " + str(game_id))
            for item_name in items:
                info("    " +  items[item_name] + " : " + item_name)
        info('--')

    if strange_items:
        info("The following items are available to download on the GOG website but not the Galaxy Extras tab and cannot generate a fallback Galaxy API link because the fully resolved website download URL does not include the (sub)-product ID")
        for game_id in strange_items:
            title, items = strange_items[game_id]
            info("  From game: " +  title + " : " + str(game_id))
            for item_name in items:
                info("    " +  items[item_name] + " : " + item_name)
        info('--')

    if broken_links:
        info("The following items are (theoretically) available to download on the GOG website but have broken links that stop them being downloaded")
        for game_id in broken_links:
            title, items = broken_links[game_id]
            info("  From game: " +  title + " : " + str(game_id))
            for (provisional_name,manualURL) in items:
                info("    " +  manualURL + " : " + provisional_name)
        info('--')
    if md5s_unexpected:
        info("The following items unexpectedly for their type have MD5s available:")
        for game_id in md5s_unexpected:
            title, items = md5s_unexpected[game_id]
            info("  From game: " +  title + " : " + str(game_id))
            for item_name in items:
                info("    " +  items[item_name] + " : " + item_name)
        info('--')
    if missing_md5s_unexpected:
        info("The following item unexpectedly for their type do not have MD5s available")
        for game_id in missing_md5s_unexpected:
            title, items =missing_md5s_unexpected[game_id]

            info("  From game: " +  title + " : " + str(game_id))
            for item_name in items:
                    info("    " +  items[item_name] + " : " + item_name)
        info('--')

    if verbose and missing_md5s_expected:
        info("The following item expectedly for their type do not have MD5s available")
        for game_id in missing_md5s_expected:
            title, items =missing_md5s_expected[game_id]

            info("  From game: " +  title + " : " + str(game_id))
            for item_name in items:
                    info("    " +  items[item_name] + " : " + item_name)
        info('--')
    info('Extension MD5 count:' + str(extension_md5_count))
    info('Extension Missing MD5 count:' + str(extension_missing_md5_count))



def cmd_import(src_dir, dest_dir,os_list,lang_list,skipextras,skipids,ids,skipgalaxy,skipstandalone,skipshared,destructive,lang_fallback=None):
    """Recursively finds all files within root_dir and compares their MD5 values
    against known md5 values from the manifest.  If a match is found, the file will be copied
    into the game storage dir.
    """
    if destructive:
        stringOperation = "move"
        stringOperationP = "moving"
    else:
        stringOperation = "copy"
        stringOperationP = "copying"
    gamesdb = load_manifest()
    selected_ids = resolve_ids_and_report(gamesdb, ids, '-ids') if ids else None       # the games that -ids means ...
    skipped_ids = resolve_ids_and_report(gamesdb, skipids, '-skipids') if skipids else set()   # ... and -skipids

    info("collecting md5 data out of the manifest")
    size_info = {} #holds dicts of entries with size as key
    #md5_info = {}  # holds tuples of (title, filename) with md5 as key

    valid_langs = []
    for lang in lang_list:
        valid_langs.append(LANG_TABLE[lang])

    for game in gamesdb:
        try:
            _ = game.galaxyDownloads
        except AttributeError:
            game.galaxyDownloads = []

        try:
            a = game.sharedDownloads
        except AttributeError:
            game.sharedDownloads = []

        try:
            _ = game.folder_name
        except AttributeError:
            game.folder_name = game.title

        downloads = game.downloads
        galaxyDownloads = game.galaxyDownloads
        sharedDownloads = game.sharedDownloads
        extras = game.extras

        if skipgalaxy:
            galaxyDownloads = []
        if skipstandalone:
            downloads = []
        if skipshared:
            sharedDownloads = []
        if skipextras:
            extras = []


        if selected_ids is not None and game.id not in selected_ids:
            continue
        if game.id in skipped_ids:
            continue
        fallback_name = LANG_TABLE[lang_fallback] if lang_fallback else None
        language_ok = set(id(x) for x in (filter_languages(downloads, valid_langs, fallback_name) + filter_languages(galaxyDownloads, valid_langs, fallback_name)
                                          + filter_languages(sharedDownloads, valid_langs, fallback_name)))
        for game_item in downloads+galaxyDownloads+sharedDownloads:
            if game_item.md5 is not None:
                if id(game_item) in language_ok:
                    if game_item.os_type in os_list:
                        try:
                            md5_info = size_info[game_item.size]
                        except KeyError:
                            md5_info = {}
                        try:
                            items = md5_info[game_item.md5]
                        except Exception:
                            items = {}
                        try:
                            entry = items[(game.folder_name,game_item.name)]
                        except Exception:
                            entry = game_item
                        items[(game.folder_name,game_item.name)] = entry
                        md5_info[game_item.md5] = items
                        size_info[game_item.size] = md5_info
        #Note that Extras currently have unusual Lang / OS entries that are also accepted.
        valid_langs_extras = valid_langs + ['']
        valid_os_extras = os_list + ['extra']
        for extra_item in extras:
            if extra_item.md5 is not None:
                if extra_item.lang in valid_langs_extras:
                    if extra_item.os_type in valid_os_extras:
                        try:
                            md5_info = size_info[extra_item.size]
                        except KeyError:
                            md5_info = {}
                        try:
                            items = md5_info[extra_item.md5]
                        except Exception:
                            items = {}
                        try:
                            entry = items[(extra_item.folder_name,extra_item.name)]
                        except Exception:
                            entry = extra_item
                        items[(game.folder_name,extra_item.name)] = entry
                        md5_info[extra_item.md5] = items
                        size_info[extra_item.size] = md5_info

    info("searching for files within '%s'" % src_dir)
    file_list = []
    for (root, dirnames, filenames) in os.walk(src_dir):
        for f in filenames:
            if (os.extsep + f.rsplit(os.extsep,1)[1]).lower() not in SKIP_MD5_FILE_EXT: #Need to extend this to cover tar.gz too
                file_list.append(os.path.join(root, f))

    info("comparing md5 file hashes")
    for f in file_list:
        fname = os.path.basename(f)
        info("calculating filesize for '%s'" % fname)
        s = os.path.getsize(f)
        if s in size_info:
            info("calculating md5 for '%s'" % fname)
            md5_info = size_info[s]
            h = hashfile(f)
            if h in md5_info:
                info('found match(es) for file %s with size [%s] and MD5 [%s]' % (fname,s, h))
                items = md5_info[h]
                for (folder_name,file_name) in items:
                    game_dest_dir = os.path.join(dest_dir, folder_name)
                    dest_file = os.path.join(game_dest_dir, file_name)
                    info('match! %s' % (dest_file))
                    if os.path.isfile(dest_file):
                        if s == os.path.getsize(dest_file) and h == hashfile(dest_file):
                            info('destination file already exists with the same size and md5 value. skipping %s.' % stringOperation)
                            run_report.count('files already in the library')
                            continue
                    info("%s to %s..." % (stringOperationP, dest_file))
                    if not os.path.isdir(game_dest_dir):
                        os.makedirs(game_dest_dir)
                    if destructive:
                        shutil.move(f, dest_file)
                    else:
                        shutil.copy(f, dest_file)
                    run_report.count('files imported', 1, s)
                    entry = items[(folder_name,file_name)]
                    changed = False
                    try:
                        if entry.force_change == True:
                            entry.has_changed = False
                            changed = True
                    except AttributeError:
                        setattr(entry,"has_changed",False)
                        changed = True
                    try:
                        if entry.old_updated != entry.updated:
                            entry.old_updated = entry.updated
                            changed = True
                    except AttributeError:
                        setattr(entry,"updated",None)
                        setattr(entry,"old_updated",None)
                        changed = True
                    try:
                        if entry.prev_verified == False:
                            entry.prev_verified = True # This isn't guaranteed to actually be the file but anything that makes it this far will pass the verify check anyway
                            changed = True
                    except AttributeError:
                        setattr(entry,"prev_verified",True)
                        changed = True
                    if changed:
                        save_manifest(gamesdb)

# ---------------------------------------------------------------------------------------------
# cmd_download and its helpers
#
# Refactoring: cmd_download used to be a single ~925 line function with nested closures. It is now
# a short orchestrator that calls the helpers below. Behaviour, log messages and file effects are
# unchanged (see CHANGELOG.md for the few intended differences).
#
#   selection / bookkeeping   _select_download_items, _index_items_by_title, _clean_work_dir
#   per game                  _process_download_item -> _item_download_lists, _write_info_file,
#                             _write_serial_file, _download_item_images, _queue_item_downloads
#   download worker threads   _download_worker -> _prepare_download_file (-> _preallocate),
#                             _download_with_chunk_verification / _download_without_chunk_verification
#                             (-> _download_ioloop), _report_progress
#   finishing                 _finish_provisional_downloads, _remove_empty_subdirs
# ---------------------------------------------------------------------------------------------

def _display_name(path):
    """'game folder/file' for messages and the run summary."""
    return "%s/%s" % (os.path.basename(os.path.dirname(path)), os.path.basename(path))


def _megs(b):
    return '%.1fMB' % (b / float(1024**2))

def _gigs(b):
    return '%.2fGB' % (b / float(1024**3))


class _DownloadJob(object):
    """State shared by the pieces of one cmd_download run.
    Refactoring: these used to be local variables of cmd_download captured by its nested functions."""
    def __init__(self, session, skippreallocation, downloadLimit):
        self.session = session                    # authenticated requests session (None for a dry run)
        self.skippreallocation = skippreallocation
        self.downloadLimit = downloadLimit
        self.sizes, self.rates, self.errors = {}, {}, {}
        self.transferred = {}                     # dest_file -> bytes really received from GOG in this run (for the run summary)
        self.work = Queue()                       # files still to download
        self.work_provisional = Queue()           # completed files waiting to be moved to their final place
        self.work_dict = dict()                   # dest_file -> work item, becomes self.work
        self.completed = set()                    # dest files that arrived (for the run summary)
        self.failed = set()                       # dest files that failed (for the run summary)
        self.provisional_dict = dict()            # dest_file -> work item, becomes self.work_provisional
        self.lock = threading.Lock()
        self.abort = threading.Event()            # set by a worker whose login expired: the others stop taking new files
        self.use_blake3 = False                   # Entry 42: record a BLAKE3 for each file that arrived (set by cmd_download)
        self.blake3 = {}                          # dest_file -> BLAKE3 computed by the worker, stored in the manifest by _finish_provisional_downloads


def _select_download_items(items, ids, skipids, skipfiles):
    """Apply -ids / -skipids to the manifest items (and announce -skipfiles); exits if nothing is left."""
    all_items = items          # -ids and -skipids are looked up among all games, not only among the ones left after -ids
    if ids:
        formattedIds =  ', '.join(map(str, ids))
        info("downloading games with id(s): {%s}" % formattedIds)
        selected = resolve_ids_and_report(all_items, ids, '-ids')       # also reports what matches no game
        items = [item for item in items if item.id in selected]

    if skipids:
        formattedSkipIds =  ', '.join(map(str, skipids))
        info("skipping games with id(s): {%s}" % formattedSkipIds)
        skipped = resolve_ids_and_report(all_items, skipids, '-skipids')
        items = [item for item in items if item.id not in skipped]

    if skipfiles:
        formattedSkipFiles = "'" + "', '".join(skipfiles) + "'"
        info("skipping files that match: {%s}" % formattedSkipFiles)

    if not items:
        if ids and skipids:
            error('no game(s) with id(s) in "{}" was found'.format(ids) + 'after skipping game(s) with id(s) in "{}".'.format(skipids))
        elif ids:
            error('no game with id in "{}" was found.'.format(ids))
        elif skipids:
            error('no game was found was found after skipping game(s) with id(s) in "{}".'.format(skipids))
        else:
            error('no game found')
        exit(1)
    return items


def _index_items_by_title(all_items):
    """Return a dict folder_name -> item (folder_name defaults to the title).
    Refactoring: the unused id -> item dict that used to be built here was dropped."""
    all_items_by_title = {}

    # make convenient dict with title/dirname as key
    for item in all_items:
        try:
            _ = item.folder_name
        except AttributeError:
            item.folder_name = item.title
        all_items_by_title[item.folder_name] = item
    return all_items_by_title


def _clean_work_dir(work_dir, all_items_by_title, dryrun, skip_dir=None):
    """Remove folders and files from !downloading (or !downloading/!provisional) that no longer belong to the manifest.
    skip_dir is a sub folder that is left alone (the provisional folder when cleaning !downloading).
    Refactoring: replaces two copies of the same loop."""
    if os.path.isdir(work_dir):
        info ("Cleaning up " + work_dir)
        for cur_dir in sorted(os.listdir(work_dir)):
            cur_fulldir = os.path.join(work_dir, cur_dir)
            if os.path.isdir(cur_fulldir):
                if cur_dir != skip_dir: #Leave the provisional directory alone
                    if cur_dir not in all_items_by_title:
                        #ToDo: Maybe try to rename ? Content file names will probably change when renamed (and can't be recognised by md5s as partial downloads) so maybe not wortwhile ?
                        info("Removing outdated directory " + cur_fulldir)
                        if not dryrun:
                            shutil.rmtree(cur_fulldir)
                    else:
                        # dir is valid game folder, check its files
                        expected_filenames = []
                        for game_item in all_items_by_title[cur_dir].downloads + all_items_by_title[cur_dir].galaxyDownloads +all_items_by_title[cur_dir].sharedDownloads + all_items_by_title[cur_dir].extras:
                            expected_filenames.append(game_item.name)
                        for cur_dir_file in os.listdir(cur_fulldir):
                            if os.path.isdir(os.path.join(work_dir, cur_dir, cur_dir_file)):
                                info("Removing subdirectory(?!) " + os.path.join(work_dir, cur_dir, cur_dir_file))
                                if not dryrun:
                                    shutil.rmtree(os.path.join(work_dir, cur_dir, cur_dir_file)) #There shouldn't be subdirectories here ?? Nuke to keep clean.
                            else:
                                if cur_dir_file not in expected_filenames:
                                    info("Removing outdated file " + os.path.join(work_dir, cur_dir, cur_dir_file))
                                    if not dryrun:
                                        os.remove(os.path.join(work_dir, cur_dir, cur_dir_file))


def _item_download_lists(item, skipextras, skipstandalone, skipgalaxy, skipshared, os_list, lang_list,lang_fallback=None):
    """Return (downloads, galaxyDownloads, sharedDownloads, extras) of a game after applying the skip flags and the os/language filters."""
    try:
        _ = item.galaxyDownloads
    except AttributeError:
        item.galaxyDownloads = []

    try:
        a = item.sharedDownloads
    except AttributeError:
        item.sharedDownloads = []

    filtered_extras = item.extras
    filtered_downloads = item.downloads
    filtered_galaxyDownloads = item.galaxyDownloads
    filtered_sharedDownloads = item.sharedDownloads

    if skipextras:
        filtered_extras = []

    if skipstandalone:
        filtered_downloads = []

    if skipgalaxy:
        filtered_galaxyDownloads = []

    if skipshared:
        filtered_sharedDownloads = []


    downloadsOS = [game_item for game_item in filtered_downloads if game_item.os_type in os_list]
    filtered_downloads= downloadsOS

    downloadsOS = [game_item for game_item in filtered_galaxyDownloads if game_item.os_type in os_list]
    filtered_galaxyDownloads = downloadsOS

    downloadsOS = [game_item for game_item in  filtered_sharedDownloads if game_item.os_type in os_list]
    filtered_sharedDownloads = downloadsOS


    # hold list of valid languages languages as known by gogapi json stuff
    valid_langs = []
    for lang in lang_list:
        valid_langs.append(LANG_TABLE[lang])


    fallback_name = LANG_TABLE[lang_fallback] if lang_fallback else None
    filtered_downloads = filter_languages(filtered_downloads, valid_langs, fallback_name)
    filtered_galaxyDownloads = filter_languages(filtered_galaxyDownloads, valid_langs, fallback_name)
    filtered_sharedDownloads = filter_languages(filtered_sharedDownloads, valid_langs, fallback_name)
    return filtered_downloads, filtered_galaxyDownloads, filtered_sharedDownloads, filtered_extras


def _write_info_entries(fd_info, header, entries):
    """Write one section (standalone / galaxy / shared) of the !info.txt game item list.
    Refactoring: replaces three copies of the same loop."""
    if len(entries) > 0:
        fd_info.write(header.format(lineSep))
    for game_item in entries:
        fd_info.write('        [{}] -- {}{}'.format(game_item.name, game_item.desc, lineSep))
        if game_item.version:
            fd_info.write('            version: {}{}'.format(game_item.version, lineSep))


def _write_info_file(item, item_homedir, filtered_downloads, filtered_galaxyDownloads, filtered_sharedDownloads, filtered_extras):
    """Generate and save a game info text file."""
    with ConditionalWriter(os.path.join(item_homedir, INFO_FILENAME)) as fd_info:
        fd_info.write('{0}-- {1} --{0}{0}'.format(lineSep, item.long_title))
        fd_info.write('title.......... {}{}'.format(item.title, lineSep))
        if item.genre:
            fd_info.write('genre.......... {}{}'.format(item.genre, lineSep))
        fd_info.write('game id........ {}{}'.format(item.id, lineSep))
        fd_info.write('url............ {}{}'.format(GOG_HOME_URL + item.store_url, lineSep))
        if item.rating > 0:
            fd_info.write('user rating.... {}%{}'.format(item.rating * 2, lineSep))
        if item.release_timestamp > 0:
            rel_date = datetime.datetime.fromtimestamp(item.release_timestamp).strftime('%B %d, %Y')
            fd_info.write('release date... {}{}'.format(rel_date, lineSep))
        if hasattr(item, 'gog_messages') and item.gog_messages:
            fd_info.write('{0}gog messages...:{0}'.format(lineSep))
            for gog_msg in item.gog_messages:
                fd_info.write('{0}{1}{0}'.format(lineSep, html2text(gog_msg).strip().replace("\n",lineSep)))
        fd_info.write('{0}game items.....:{0}{0}'.format(lineSep))
        _write_info_entries(fd_info, '{0}    standalone...:{0}{0}', filtered_downloads)
        _write_info_entries(fd_info, '{0}    galaxy.......:{0}{0}', filtered_galaxyDownloads)
        _write_info_entries(fd_info, '{0}    shared.......:{0}{0}', filtered_sharedDownloads)
        if len(filtered_extras) > 0:
            fd_info.write('{0}extras.........:{0}{0}'.format(lineSep))
            for game_item in filtered_extras:
                fd_info.write('    [{}] -- {}{}'.format(game_item.name, game_item.desc, lineSep))
        if item.changelog:
            fd_info.write('{0}changelog......:{0}{0}'.format(lineSep))
            fd_info.write(html2text(item.changelog).strip().replace("\n",lineSep))
            fd_info.write(lineSep)


def _write_serial_file(item, item_homedir):
    """Generate and save a game serial text file."""
    try:
        if len(item.serials) != 0:
            with ConditionalWriter(os.path.join(item_homedir, SERIAL_FILENAME)) as fd_serial:
                for key in item.serials.keys():
                    serial = item.serials[key]
                    fd_serial.write(key + ":" + lineSep + lineSep )
                    serial = serial.replace('<span>', '')
                    serial = serial.replace('</span>', lineSep)
                    serial = serial.rstrip(lineSep)
                    fd_serial.write(serial)
                    fd_serial.write(lineSep + lineSep)
    except AttributeError:
            if item.serial != '':
                with ConditionalWriter(os.path.join(item_homedir, SERIAL_FILENAME)) as fd_serial:
                    item.serial = item.serial.replace('<span>', '')
                    item.serial = item.serial.replace('</span>', lineSep)
                    fd_serial.write(item.serial)


def _download_image_from_item_key(session,item,key,images_dir_name,image_orphandir,clean_existing):
    # Refactoring: was a closure inside cmd_download, the session is now a parameter.
    images_key_dir_name = os.path.join(images_dir_name,key)
    key_local_path = item[key].lstrip("/") + ".jpg"
    key_url = 'https://' + key_local_path
    (dir,file) = os.path.split(key_local_path)
    key_local_path_dir = os.path.join(images_key_dir_name,dir)
    key_local_path_file = os.path.join(key_local_path_dir,file)
    modified_images_key_dir_name = images_key_dir_name
    if not os.path.exists(key_local_path_file):
        if os.path.exists(modified_images_key_dir_name):
            try:
                if (clean_existing):
                    if not os.path.exists(image_orphandir):
                        os.makedirs(image_orphandir)
                    move_with_increment_on_clash(modified_images_key_dir_name, image_orphandir)
                else:
                    shutil.rmtree(modified_images_key_dir_name)
            except Exception as e:
                error("Could not remove potential old image file, aborting update attempt. Please make sure folder and files are writeable and that nothing is accessing the !image folder")
                raise
        response = request(session,key_url)
        os.makedirs(key_local_path_dir)
        with open(key_local_path_file,"wb") as out:
            out.write(response.content)


def _download_image_from_item_keys(session,item,keys,images_dir_name,image_orphandir,clean_existing):
    # Refactoring: was a closure inside cmd_download, the session is now a parameter.
    images_key_dir_name = os.path.join(images_dir_name,keys)
    images_key_orphandir_name = os.path.join(image_orphandir,keys)
    if not os.path.exists(images_key_dir_name):
        os.makedirs(images_key_dir_name)
    mkeys = item[keys]
    validPaths = []
    for key in mkeys.keys():
        partial_key_local_path = mkeys[key].lstrip("/") + ".jpg"
        leading_partial_key_local_path = slugify(key,True)
        leading_partial_key_local_path_dir = os.path.join(images_key_dir_name, leading_partial_key_local_path)
        validPaths.append(leading_partial_key_local_path)
        (trailing_partial_key_local_path_dir,trailing_partial_key_local_path_file) =  os.path.split(partial_key_local_path)
        longpath_safe_leading_partial_key_local_path_dir = leading_partial_key_local_path_dir
        if not os.path.exists(longpath_safe_leading_partial_key_local_path_dir):
            os.makedirs(longpath_safe_leading_partial_key_local_path_dir)
        full_key_local_path_dir = os.path.join(leading_partial_key_local_path_dir,trailing_partial_key_local_path_dir)
        full_key_local_path_file = os.path.join(full_key_local_path_dir,trailing_partial_key_local_path_file)
        key_url = 'https://' + partial_key_local_path
        if not os.path.exists(full_key_local_path_file):
            if os.path.exists(full_key_local_path_dir):
                images_full_key_local_path_orphandir = os.path.join(images_key_orphandir_name,leading_partial_key_local_path)
                try:
                    if (clean_existing):
                        if not os.path.exists( images_full_key_local_path_orphandir):
                            os.makedirs( images_full_key_local_path_orphandir)
                        move_with_increment_on_clash(full_key_local_path_dir,  images_full_key_local_path_orphandir)
                    else:
                        shutil.rmtree(full_key_local_path_dir)
                except Exception as e:
                    error("Could not remove potential old image files, aborting update attempt. Please make sure folder and files are writeable and that nothing is accessing the !image folder")
                    raise
            try:
                response = request(session,key_url)
                os.makedirs(full_key_local_path_dir)
                with open(full_key_local_path_file,"wb") as out:
                    out.write(response.content)
            except requests.HTTPError:
                error('Could not download background image ' + full_key_local_path_file)
    for potential_old_folder in sorted(os.listdir(images_key_dir_name)):
        if potential_old_folder not in validPaths:
            potential_old_folder_path = os.path.join(images_key_dir_name,potential_old_folder)
            try:
                if (clean_existing):
                    if not os.path.exists(images_key_orphandir_name):
                        os.makedirs(images_key_orphandir_name)
                    move_with_increment_on_clash(potential_old_folder_path, images_key_orphandir_name)
                else:
                    shutil.rmtree(potential_old_folder_path)
            except Exception as e:
                error("Could not remove potential old image files, aborting update attempt. Please make sure folder and files are writeable and that nothing is accessing the !image folder")
                raise


def _download_item_images(session, item, item_homedir, item_orphandir, backgrounds, covers, clean_old_images):
    """Download the cover and background images of a game into its !images folder."""
    images_dir_name = os.path.join(item_homedir, IMAGES_DIR_NAME)
    image_orphandir = os.path.join(item_orphandir,IMAGES_DIR_NAME)

    if not os.path.exists(images_dir_name):
        os.makedirs(images_dir_name)
    try:
        if len(item.bg_urls) != 0 and backgrounds:
            images_old_bg_url_dir_name = os.path.join(images_dir_name,"bg_url")
            modified_image_orphandir =  image_orphandir
            if os.path.exists(images_old_bg_url_dir_name):
                try:
                    if (clean_old_images):
                        if not os.path.exists( modified_image_orphandir):
                            os.makedirs( modified_image_orphandir)
                        move_with_increment_on_clash(images_old_bg_url_dir_name , modified_image_orphandir)
                    else:
                        shutil.rmtree(images_old_bg_url_dir_name )
                except Exception as e:
                    error("Could not delete potential old bg_url files, aborting update attempt. Please make sure folder and files are writeable and that nothing is accessing the !image folder")
                    raise
            try:
                _download_image_from_item_keys(session,item,"bg_urls",images_dir_name,image_orphandir,clean_old_images)
            except KeyboardInterrupt:
                warn("Interrupted during download of background image(s)")
                raise
            except Exception:
                warn("Could not download background image")

    except AttributeError:
        if item.bg_url != '' and backgrounds:
            try:
                _download_image_from_item_key(session,item,"bg_url",images_dir_name,image_orphandir,clean_old_images)
            except KeyboardInterrupt:
                warn("Interrupted during download of background image")
                raise
            except Exception:
                warn("Could not download background image")

    if item.image_url != '' and covers:
        try:
            _download_image_from_item_key(session,item,"image_url",images_dir_name,image_orphandir,clean_old_images)
        except KeyboardInterrupt:
            warn("Interrupted during download of cover image")
            raise
        except Exception:
            warn("Could not download cover image")


def _queue_item_downloads(job, item, game_items, item_homedir, item_downloaddir, item_provisionaldir, skipfiles, all_items):
    """Check the files of one game on disk and put the ones that need (re-)downloading into job.work_dict.
    Files left in the provisional folder by an interrupted run go into job.provisional_dict instead."""
    # Populate queue with all files to be downloaded
    for game_item in game_items:
        if game_item.name is None:
            continue  # no game name, usually due to 404 during file fetch

        try:
            _ = game_item.force_change
        except AttributeError:
            game_item.force_change = False

        try:
            _ = game_item.updated
        except AttributeError:
            game_item.updated = None

        try:
            _ = game_item.old_updated
        except AttributeError:
            game_item.old_updated = None

        skipfile_skip = check_skip_file(game_item.name, skipfiles)
        if skipfile_skip:
            info('     skip       %s (matches "%s")' % (game_item.name, skipfile_skip))
            run_report.count('files skipped')
            continue

        dest_file = os.path.join(item_homedir, game_item.name)
        downloading_file = os.path.join(item_downloaddir, game_item.name)
        provisional_file = os.path.join(item_provisionaldir,game_item.name)

        if game_item.size is None:
            warn('     unknown    %s has no size info.  skipping' % game_item.name)
            run_report.count('files skipped')
            continue

        if os.path.isfile(provisional_file):
            if os.path.isfile(dest_file):
                #I don't know how you got it here, but if you did , clean up your mess! This is not my problem. But more politely.
                warn('     error      %s has both provisional and destination file. Please remove one.' % game_item.name)
                run_report.fail(_display_name(dest_file), 'has both a provisional and a final file, remove one of them')
                continue
            else:
                info('     working    %s' % game_item.name)
                job.provisional_dict[dest_file] = (dest_file,provisional_file,game_item,all_items)
                continue


        if os.path.isfile(dest_file):
            if game_item.size != os.path.getsize(dest_file):
                warn('     fail       %s has incorrect size.' % game_item.name)
            elif game_item.force_change == True:
                warn('     fail       %s has been marked for change.' % game_item.name)
            else:
                info('     pass       %s' % game_item.name)
                run_report.count('files already up to date')
                continue  # move on to next game item

        if job.downloadLimit is not None and ((sum(job.sizes.values()) + game_item.size) > job.downloadLimit):
            info('     skip       %s (size %s would exceed download limit (%s/%s) )' % (game_item.name, _megs(game_item.size),_megs(sum(job.sizes.values())),_megs(job.downloadLimit)))
            run_report.count('files skipped (download limit)')
            continue


        info('     download   %s' % game_item.name)
        job.sizes[dest_file] = game_item.size


        job.work_dict[dest_file] = (game_item.href, game_item.size, 0, game_item.size-1, dest_file,downloading_file,provisional_file,game_item,all_items)


def _process_download_item(job, item, savedir, downloadingdir, provisionaldir, orphandir, all_items,
                           skipextras, skipstandalone, skipgalaxy, skipshared, os_list, lang_list,
                           skipfiles, covers, backgrounds, clean_old_images, dryrun, lang_fallback=None):
    """Everything cmd_download does for one game: folders, !info/!serial files, images, and queueing its files."""
    info("{%s}" % item.folder_name)
    item_homedir = os.path.join(savedir, item.folder_name)
    item_downloaddir = os.path.join(downloadingdir, item.folder_name)
    item_provisionaldir =os.path.join(provisionaldir, item.folder_name)
    item_orphandir = os.path.join(orphandir,item.folder_name)
    if not dryrun:
        if not os.path.isdir(item_homedir):
            os.makedirs(item_homedir)

    filtered_downloads, filtered_galaxyDownloads, filtered_sharedDownloads, filtered_extras = _item_download_lists(
        item, skipextras, skipstandalone, skipgalaxy, skipshared, os_list, lang_list, lang_fallback)

    if not dryrun:
        _write_info_file(item, item_homedir, filtered_downloads, filtered_galaxyDownloads, filtered_sharedDownloads, filtered_extras)
        _write_serial_file(item, item_homedir)
        _download_item_images(job.session, item, item_homedir, item_orphandir, backgrounds, covers, clean_old_images)

    _queue_item_downloads(job, item, filtered_downloads + filtered_galaxyDownloads + filtered_sharedDownloads + filtered_extras,
                          item_homedir, item_downloaddir, item_provisionaldir, skipfiles, all_items)


def _kill_response(response):
    response.close()


class _StallWatchdog(object):
    """Closes `response` if no data arrives for `timeout` seconds.

    Refactoring (CPU): the old code created, started and cancelled a new threading.Timer (a new OS thread) for
    every chunk that was received. This uses one timer thread per response, which only re-arms itself when it
    fires. Same rule as before: time spent processing a chunk (pause()..resume()) does not count as waiting."""
    def __init__(self, response, timeout):
        self.response, self.timeout = response, timeout
        self.last, self.paused, self.stopped = time.monotonic(), False, False
        self.timer = None
        self._arm(timeout)

    def _arm(self, delay):
        self.timer = threading.Timer(delay, self._check)
        self.timer.daemon = True
        self.timer.start()

    def _check(self):
        if self.stopped:
            return
        idle = time.monotonic() - self.last
        if self.paused:
            self._arm(self.timeout)
        elif idle < self.timeout:
            self._arm(self.timeout - idle)
        else:
            _kill_response(self.response)

    def pause(self):
        self.paused = True

    def resume(self):
        self.last, self.paused = time.monotonic(), False

    def stop(self):
        self.stopped = True
        if self.timer is not None:
            self.timer.cancel()


def _download_ioloop(job, tid, path, response, out):
    """Copy the body of a ranged response into the open file `out`; returns the number of bytes written."""
    # Refactoring: was the closure 'ioloop' inside cmd_download.
    #info("Entering I/O Loop - " + path)
    sz, t0 = True, time.time()
    dlsz = 0
    watchdog = _StallWatchdog(response, HTTP_TIMEOUT)
    try:
        for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
            watchdog.pause()
            if (chunk):
                t = time.time()
                out.write(chunk)
                sz, dt, t0 = len(chunk), t - t0, t
                dlsz = dlsz + sz
                with job.lock:
                    job.sizes[path] -= sz
                    job.transferred[path] = job.transferred.get(path, 0) + sz
                    job.rates.setdefault(path, []).append((tid, (sz, dt)))
            watchdog.resume()
    except (requests.exceptions.ConnectionError,requests.packages.urllib3.exceptions.ProtocolError) as e:
        error("server response issue while downloading content for %s" % (path))
    except (requests.exceptions.SSLError) as e:
        error("SSL issue while downloading content for %s" % (path))
    except (requests.exceptions.ChunkedEncodingError) as e:
        error("Encoding Error In Chunk for %s" %  (path))
    finally:
        watchdog.stop()
        close = getattr(response, 'close', None)
        if close is not None:
            close()
    #info("Exiting I/O Loop - " + path)
    return dlsz


def _preallocate(downloading_path, compat_downloading_path, sz, create, windows_fs_path):
    """Reserve disk space for a download where the file system supports it.

    create=True preallocates a new file (CREATE_NEW / mode "wb"), create=False grows an existing partial file.
    windows_fs_path is the path used for the Windows file system type lookup (callers differ, see _prepare_download_file).
    Refactoring: replaces three near identical copies of this logic. The Windows handle is now always initialised
    to -1, so a failure before CreateFileW returns can no longer raise UnboundLocalError in the error handler."""
    if platform.system() == "Darwin":
        #MacOS doesn't support posix.fallocate
        return
    elif platform.system() == "Windows":
        fs = get_fs_type(windows_fs_path,True)
        if fs in WINDOWS_PREALLOCATION_FS:
            preH = -1
            try:
                if create:
                    info("preallocating '%d' bytes for '%s' " % (sz,downloading_path))
                else:
                    info("increasing preallocation to '%d' bytes for '%s' " % (sz,downloading_path))
                preH = ctypes.windll.kernel32.CreateFileW(compat_downloading_path, GENERIC_READ | GENERIC_WRITE, 0, None, CREATE_NEW if create else OPEN_EXISTING, 0, None)
                if preH==-1:
                    warn("could not get filehandle")
                    raise OSError()
                c_sz = ctypes.wintypes.LARGE_INTEGER(sz)
                ctypes.windll.kernel32.SetFilePointerEx(preH,c_sz,None,FILE_BEGIN)
                ctypes.windll.kernel32.SetEndOfFile(preH)
                ctypes.windll.kernel32.CloseHandle(preH)
            except Exception:
                warn("preallocation failed")
                warn("The handled exception was:")
                log_exception('')
                warn("End exception report.")
                if preH != -1:
                    warn('failed - closing outstanding handle')
                    ctypes.windll.kernel32.CloseHandle(preH)
    else:
        fs = get_fs_type(downloading_path)
        if fs.lower() in POSIX_PREALLOCATION_FS:
            if create:
                info("attempting preallocating '%d' bytes for '%s' using posix_fallocate " % (sz,downloading_path))
            else:
                info("increasing preallocation to '%d' bytes for '%s' using posix_fallocate " % (sz,downloading_path))
            with open(downloading_path, "wb" if create else "r+b") as f:
                try:
                    os.posix_fallocate(f.fileno(),0,sz)
                except Exception:
                    warn("posix preallocation failed")


def _fit_partial_file(job, downloading_path, compat_downloading_path, sz, windows_fs_path):
    """Make an existing partial download exactly sz bytes: truncate it if too large, preallocate if too small."""
    file_sz = os.path.getsize(downloading_path)
    if file_sz > sz:  # if needed, truncate file if ours is larger than expected size
        with open_notrunc(downloading_path) as f:
            f.truncate(sz)
    if file_sz < sz: #preallocate extra space
        if not job.skippreallocation:
            _preallocate(downloading_path, compat_downloading_path, sz, False, windows_fs_path)


def _prepare_download_file(job, path, downloading_path, provisional_path, sz):
    """Create the folders for a download and get its working file into shape: reuse the existing file or
    a partial download (truncate / preallocate it), or preallocate a new one."""
    dest_dir = os.path.dirname(path)
    downloading_dir = os.path.dirname(downloading_path)
    provisional_dir = os.path.dirname(provisional_path)
    compat_downloading_path = process_path(downloading_path)
    with job.lock:
        if not os.path.isdir(dest_dir):
            os.makedirs(dest_dir)
        if not os.path.isdir(downloading_dir):
            os.makedirs(downloading_dir)
        if not os.path.isdir(provisional_dir):
            os.makedirs(provisional_dir)
        if (os.path.exists(path)):
            info("moving existing file '%s' to '%s' for downloading " % (path,downloading_path))
            shutil.move(path,downloading_path)
            # Note: the Windows file system lookup uses the \\?\ style path for a moved file but the plain path for a partial file.
            _fit_partial_file(job, downloading_path, compat_downloading_path, sz, compat_downloading_path)
        else:
            if (os.path.exists(downloading_path)):
                _fit_partial_file(job, downloading_path, compat_downloading_path, sz, downloading_path)
            else:
                if not job.skippreallocation:
                    _preallocate(downloading_path, compat_downloading_path, sz, True, downloading_path)


def _download_with_chunk_verification(job, tid, href, path, downloading_path, sz, chunk_tree):
    """Verify the working file chunk by chunk against GOG's MD5 data and re-download only the chunks that differ.
    Returns True if every chunk is good afterwards."""
    succeed = False
    name = chunk_tree.attrib['name']
    expected_size = int(chunk_tree.attrib['total_size'])
    if (expected_size != sz):
        with job.lock:
            warn("XML verification data size does not match manifest size for %s. manifest %d, received %d, skipping. "
                  % (name, sz, expected_size))
    else:
        expected_no_of_chunks = int(chunk_tree.attrib['chunks'])
        actual_no_of_chunks = len(list(chunk_tree))
        if (expected_no_of_chunks != actual_no_of_chunks):
            with job.lock:
                warn("XML verification chunk data for %s is not sane skipping." % name)
        else:
            succeed = True
            for elem in list(chunk_tree):
                method = elem.attrib["method"]
                if (method != "md5"):
                    warn("XML chunk verification method for %s is not md5. skipping. " %name)
                    succeed = succeed and False
                else:
                    start = int(elem.attrib["from"])
                    end =   int(elem.attrib["to"])
                    se = start,end
                    md5 = elem.text
                    with open_notruncwrrd(downloading_path) as out:
                        valid = hashstream(out,start,end) == md5
                        if (valid):
                            with job.lock:
                                job.sizes[path] -= (end - start)+1
                        else:
                            retries = HTTP_RETRY_COUNT
                            downloadSegmentSuccess = False
                            while (not downloadSegmentSuccess and retries >= 0):
                                try:
                                    response = request(job.session,href, byte_range=(start,end),stream=True)
                                    hdr = response.headers['Content-Range'].split()[-1]
                                    if hdr != '%d-%d/%d' % (start, end, sz):
                                        with job.lock:
                                            error("chunk request has unexpected Content-Range. "
                                                  "expected '%d-%d/%d' received '%s'. skipping."
                                                  % (start, end, sz, hdr))
                                            succeed = succeed and False
                                            retries = -1
                                    else:
                                        out.seek(start)
                                        assert out.tell() == start
                                        dlsz = _download_ioloop(job, tid, path, response, out)
                                        if (dlsz == (end - start)+1 and out.tell() == end + 1):
                                            downloadSegmentSuccess= True;
                                            succeed = succeed and True
                                        else:
                                            with job.lock:
                                                job.sizes[path] += dlsz
                                            if (retries > 0):
                                                warn("failed to download %s, byte_range=%s (%d retries left) -- will retry in %ds..." % (os.path.basename(path), str(se),retries,HTTP_RETRY_DELAY))
                                                time.sleep(HTTP_RETRY_DELAY)     # as the plain download loop does (this one does not hold job.lock meanwhile)
                                            else:
                                                error("failed to download %s, byte_range=%s" % (os.path.basename(path), str(se)))
                                                succeed = succeed and False;
                                        retries = retries -1
                                except requests.HTTPError as e:
                                    with job.lock:
                                        error("failed to download %s, byte_range=%s" % (os.path.basename(path), str(se)))
                                        succeed = succeed and False
                                        retries = -1
                                except Exception as e:
                                     with job.lock:
                                        warn("The unhandled exception was:")
                                        log_exception('')
                                        warn("End exception report.")
                                        raise
    return succeed


def _download_without_chunk_verification(job, tid, href, path, downloading_path, sz, start, end):
    """Download the whole byte range [start, end] into the working file (used when GOG has no MD5 data for the file).
    Returns True on success."""
    succeed = False
    with open_notrunc(downloading_path) as out:
        se = start, end
        retries = HTTP_RETRY_COUNT
        downloadSuccess = False
        while ((not downloadSuccess) and retries >= 0):
            try:
                response = request(job.session,href, byte_range=(start,end),stream=True)
                hdr = response.headers['Content-Range'].split()[-1]
                if hdr != '%d-%d/%d' % (start, end, sz):
                    with job.lock:
                        error("chunk request has unexpected Content-Range. "
                              "expected '%d-%d/%d' received '%s'. skipping."
                              % (start, end, sz, hdr))
                        succeed = False
                        retries = -1
                    close = getattr(response, 'close', None)
                    if close is not None:
                        close()
                else:
                    out.seek(start)
                    assert out.tell() == start
                    dlsz = _download_ioloop(job, tid, path, response, out)
                    if (dlsz == (end - start)+1 and out.tell() == end + 1):
                        downloadSuccess= True;
                        succeed = True
                    else:
                        with job.lock:
                            job.sizes[path] += dlsz
                            if retries > 0:
                                warn("failed to download %s, byte_range=%s (%d retries left) -- will retry in %ds..." % (os.path.basename(path), str(se), retries, HTTP_RETRY_DELAY))
                            else:
                                error("failed to download %s, byte_range=%s" % (os.path.basename(path), str(se)))
                                succeed = False
                            retries -= 1
                        if retries >= 0:
                            time.sleep(HTTP_RETRY_DELAY)
            except requests.HTTPError as e:
                error("failed to download %s, byte_range=%s" % (os.path.basename(path), str(se)))
                succeed = False
                retries = -1
            except Exception as e:
                 with job.lock:
                    warn("The unhandled exception was:")
                    log_exception('')
                    warn("End exception report.")
                    raise
    return succeed


def _download_blake3(item, file_path):
    """Entry 42: the BLAKE3 of a file that has just arrived, or None if there is nothing to record (the caller keeps the download either way).
    The same rule as in verify: a baseline only exists for confirmed content. With an md5 in the manifest, md5 and BLAKE3 are computed in one read
    pass and the BLAKE3 is kept only if the md5 matches; without one (types GOG gives no md5 for), the known size must match."""
    try:
        if getattr(item, 'md5', None) is not None:
            hashes = hash_file(file_path, md5=True, blake3=True)
            if hashes['md5'] != item.md5:
                warn('no BLAKE3 recorded for %s: its md5 differs from the manifest (run verify to check it)' % os.path.basename(file_path))
                return None
            return hashes['blake3']
        size = getattr(item, 'size', None)
        if size is None or os.path.getsize(file_path) != size:
            return None
        return hash_file(file_path, md5=False, blake3=True)['blake3']
    except Exception as e:          # a failure here must never turn a good download into a failed one
        warn('no BLAKE3 recorded for %s (%s)' % (os.path.basename(file_path), e))
        return None


def _download_worker(job):
    """Main loop of a downloader thread: takes files from job.work until it is empty."""
    # Refactoring: was the closure 'worker' inside cmd_download.
    tid = threading.current_thread().ident
    while not job.abort.is_set():
        # Refactoring: was 'while not job.work.empty(): job.work.get()'. With several threads, two of them could both see one file left;
        # the second then waited in get() forever and the run never ended.
        try:
            (href, sz, start, end, path,downloading_path,provisional_path,writable_game_item,work_writable_items) = job.work.get_nowait()
        except Empty:
            break
        try:
            _prepare_download_file(job, path, downloading_path, provisional_path, sz)
            succeed = False
            response = request_head(job.session,href)
            try:
                api_downlink = writable_game_item.gog_data.api_downlink
            except (AttributeError, TypeError):
                api_downlink = None
            chunk_tree = fetch_chunk_tree(response,job.session,api_downlink)
            if (chunk_tree is not None):
                succeed = _download_with_chunk_verification(job, tid, href, path, downloading_path, sz, chunk_tree)
            else:
                succeed = _download_without_chunk_verification(job, tid, href, path, downloading_path, sz, start, end)
            if succeed and job.sizes[path]==0:
                with job.lock:
                    info("moving provisionally completed download '%s' to '%s'  " % (downloading_path,provisional_path))
                    shutil.move(downloading_path,provisional_path)
                #This should be thread safe so should be fine outside the lock, doing it after the lock so we don't add this if something went wrong.
                job.work_provisional.put((path,provisional_path,writable_game_item,work_writable_items))
                if job.use_blake3 and writable_game_item is not None:
                    # Entry 42: hashed here, in the thread, while the file is still in the disk cache and the other threads keep downloading
                    b3 = _download_blake3(writable_game_item, provisional_path)
                    if b3:
                        with job.lock:
                            job.blake3[path] = b3
            else:
                with job.lock:
                    info("not moving uncompleted download '%s', success: %s remaining bytes: %d / %d " % (downloading_path,str(succeed),job.sizes[path],sz))
                    job.failed.add(path)
                    run_report.fail(_display_name(path), "incomplete, %d of %d bytes missing" % (job.sizes[path], sz))
        except AuthExpired:
            with job.lock:
                job.abort.set()
                job.failed.add(path)
                run_report.fail(_display_name(path), "login expired, run the login command again")
        except IOError as e:
            with job.lock:
                warn("The handled exception was:")
                log_exception('')
                warn("End exception report.")
                error("! %s", path)
                job.errors.setdefault(path, []).append(e)
                job.failed.add(path)
                run_report.fail(_display_name(path), str(e) or type(e).__name__)
        except Exception as e:
             with job.lock:
                warn("The unhandled exception was:")
                log_exception('')
                warn("End exception report.")
                job.failed.add(path)
                run_report.fail(_display_name(path), "unexpected error (%s), see the messages above" % type(e).__name__)
                raise
        #debug
        #info("thread completed")
        job.work.task_done()


def _report_progress(job):
    """Detailed progress report, printed about once a second while downloading."""
    # Refactoring: was the closure 'progress' inside cmd_download.
    with job.lock:
        left = sum(job.sizes.values())
        for path, flowrates in sorted(job.rates.items()):
            flows = {}
            for tid, (sz, t) in flowrates:
                szs, ts = flows.get(tid, (0, 0))
                flows[tid] = sz + szs, t + ts
            bps = sum(szs/ts for szs, ts in list(flows.values()) if ts > 0)
            info('%10s %8.1fMB/s %2dx  %s' % \
                (_megs(job.sizes[path]), bps / 1024.0**2, len(flows), "%s/%s" % (os.path.basename(os.path.split(path)[0]), os.path.split(path)[1])))
        if len(job.rates) != 0:  # only update if there's change
            info('%s remaining' % _gigs(left))
        job.rates.clear()


def _finish_provisional_downloads(job):
    """Move completed downloads from !provisional to their final place and reset their 'needs update' flags in the manifest.
    This is done in the main thread after all downloader threads have finished."""
    wChanged = False;
    work_writable_items = None

    #Everything here would be done inside a lock so may as well process it in the main thread.
    while not job.work_provisional.empty():
        (path,provisional_path,writable_game_item,work_writable_items) = job.work_provisional.get()
        info("moving provisionally completed download '%s' to '%s'  " % (provisional_path,path))
        shutil.move(provisional_path,path)
        job.completed.add(path)
        size = getattr(writable_game_item, 'size', None) if writable_game_item is not None else None
        if path in job.provisional_dict:
            run_report.count('files recovered from an earlier run', 1, size)
        elif job.transferred.get(path, 0) > 0:
            run_report.count('files downloaded', 1, job.transferred[path])        # the data that really came from GOG
        else:                                         # marked for change, but chunk by chunk it was already right: no transfer
            run_report.count('files verified in place (nothing downloaded)', 1, size)
        if writable_game_item != None:
            try:
                _ = writable_game_item.force_change
            except AttributeError:
                writable_game_item.force_change = False
            try:
                _ = writable_game_item.updated
            except AttributeError:
                writable_game_item.updated = None
            try:
                _ = writable_game_item.old_updated
            except AttributeError:
                writable_game_item.old_updated = None
            try:
                _ = writable_game_item.prev_verified
            except AttributeError:
                writable_game_item.prev_verified = False


            if writable_game_item.force_change:
                writable_game_item.force_change = False
                writable_game_item.old_updated = writable_game_item.updated
                wChanged = True
            if writable_game_item.prev_verified:
                writable_game_item.prev_verified = False
                wChanged = True
            # Entry 42: the BLAKE3 of the file that has just arrived. A file recovered from an earlier run was not hashed by a worker: do it now.
            b3 = job.blake3.pop(path, None) if job.use_blake3 else None
            if b3 is None and job.use_blake3 and path in job.provisional_dict:
                b3 = _download_blake3(writable_game_item, path)
            if b3:
                if getattr(writable_game_item, 'blake3', None) != b3:
                    writable_game_item.blake3 = b3
                    wChanged = True
            elif getattr(writable_game_item, 'blake3', None) and job.transferred.get(path, 0) > 0:
                writable_game_item.blake3 = None     # new content came in and no new BLAKE3 could be recorded: the old one no longer describes the file
                wChanged = True
    if wChanged:
        save_manifest(work_writable_items)


def _remove_empty_subdirs(root_dir, skip_dir=None):
    """Remove empty sub folders of root_dir (except skip_dir). Failures are ignored.
    Refactoring: replaces two copies of the same loop."""
    for dir in os.listdir(root_dir):
        if dir != skip_dir:
            testdir= os.path.join(root_dir,dir)
            if os.path.isdir(testdir):
                if not os.listdir(testdir):
                    try:
                        os.rmdir(testdir)
                    except Exception:
                        pass


def cmd_download(savedir, skipextras,skipids, dryrun, ids,os_list, lang_list,skipgalaxy,skipstandalone,skipshared, skipfiles,covers,backgrounds,skippreallocation,clean_old_images,downloadLimit = None, lang_fallback=None, use_blake3=True):
    downloadSession = None
    if not dryrun:
        downloadSession = makeGOGSession()
    job = _DownloadJob(downloadSession, skippreallocation, downloadLimit)
    if use_blake3 and not dryrun:
        if blake3_available():
            job.use_blake3 = True
        else:
            info('the blake3 package is not installed, so no BLAKE3 checksums are recorded for the downloads (python -m pip install blake3; -noblake3 hides this message)')

    items = load_manifest()
    all_items = items

    items = _select_download_items(items, ids, skipids, skipfiles)

    handle_game_renames(savedir,items,dryrun)

    all_items_by_title = _index_items_by_title(all_items)

    downloadingdir = os.path.join(savedir, DOWNLOADING_DIR_NAME)
    provisionaldir = os.path.join(downloadingdir,PROVISIONAL_DIR_NAME )
    orphandir =  os.path.join(savedir, ORPHAN_DIR_NAME)

    _clean_work_dir(downloadingdir, all_items_by_title, dryrun, skip_dir=PROVISIONAL_DIR_NAME)
    _clean_work_dir(provisionaldir, all_items_by_title, dryrun)

    for item in items:
        try:
            _ = item.folder_name
        except AttributeError:
            item.folder_name = item.title


    # Find all items to be downloaded and push into work queue
    for item in sorted(items, key=lambda g: g.folder_name):
        _process_download_item(job, item, savedir, downloadingdir, provisionaldir, orphandir, all_items,
                               skipextras, skipstandalone, skipgalaxy, skipshared, os_list, lang_list,
                               skipfiles, covers, backgrounds, clean_old_images, dryrun, lang_fallback)

    for work_item in job.work_dict:
        job.work.put(job.work_dict[work_item])

    for provisional_item in job.provisional_dict:
        job.work_provisional.put(job.provisional_dict[provisional_item])

    if dryrun:
        info("{} left to download".format(_gigs(sum(job.sizes.values()))))
        run_report.count('files that would be downloaded', len(job.work_dict), sum(job.sizes.values()))
        return  # bail, as below just kicks off the actual downloading

    if job.work.empty():
        if job.work_provisional.empty():
            info("nothing to download")
            return
        # Nothing is left to download, but an interrupted earlier run had finished some files that are still in !provisional.
        info("nothing else needs downloading; moving %d completed file(s) that an earlier run left in '%s' to their place"
             % (job.work_provisional.qsize(), os.path.join(DOWNLOADING_DIR_NAME, PROVISIONAL_DIR_NAME)))
        _finish_provisional_downloads(job)
        _remove_empty_subdirs(downloadingdir, skip_dir=PROVISIONAL_DIR_NAME)
        _remove_empty_subdirs(provisionaldir)
        return

    downloading_root_dir = os.path.join(savedir, DOWNLOADING_DIR_NAME)
    if not os.path.isdir(downloading_root_dir):
        os.makedirs(downloading_root_dir)

    provisional_root_dir = os.path.join(savedir, DOWNLOADING_DIR_NAME,PROVISIONAL_DIR_NAME)
    if not os.path.isdir(provisional_root_dir):
        os.makedirs(provisional_root_dir)

    info('-'*60)

    # process work items with a thread pool
    pool = []
    for i in range(HTTP_GAME_DOWNLOADER_THREADS):
        t = threading.Thread(target=_download_worker, args=(job,))
        t.daemon = True
        t.start()
        pool.append(t)
    try:
        while any(t.is_alive() for t in pool):
            _report_progress(job)
            time.sleep(DOWNLOAD_PROGRESS_INTERVAL)
    except KeyboardInterrupt:
        raise
    except Exception:
        with job.lock:
            warn("The unhandled exception was:")
            log_exception('')
            warn("End exception report.")
        raise

    _finish_provisional_downloads(job)
    for queued_path in job.work_dict:                       # anything that neither arrived nor was reported as failed
        if queued_path not in job.completed and queued_path not in job.failed:
            run_report.fail(_display_name(queued_path), "not downloaded (login expired, run the login command again)" if job.abort.is_set()
                            else "not downloaded (a download thread stopped unexpectedly)")

    _remove_empty_subdirs(downloading_root_dir, skip_dir=PROVISIONAL_DIR_NAME)
    _remove_empty_subdirs(provisional_root_dir)

    # Refactoring: like cmd_update, report the combined MD5 warnings now instead of only at interpreter exit
    # (where they appeared after the final "exiting..." line).
    flush_summarised()

def default_csv_delimiter():
    """The column separator the user's spreadsheet program most likely expects: ',' for English, Japanese, Chinese,
    Korean, Thai and Hebrew, ';' for the languages that write decimals with a comma (so German Excel needs ';')."""
    lang, _ = detect_lang()
    return ',' if lang in ('en', 'jp', 'cn', 'zh', 'ko', 'th', 'he') else ';'


def cmd_export(output='gog-library.csv', savedir=None, delimiter=None):
    """Write the manifest as a CSV spreadsheet, one row per file (installers, galaxy installers, shared files and extras).
    With savedir an extra column says whether each file exists there with the right size (no checksums are computed)."""
    items = load_manifest()
    delimiter = delimiter or default_csv_delimiter()
    columns = ['game id', 'title', 'folder', 'kind', 'file', 'operating system', 'language', 'version', 'size (bytes)', 'size', 'md5', 'updated']
    if savedir:
        columns.append('on disk')
    rows = 0
    # utf-8 with a byte order mark so that Excel shows umlauts and other special characters correctly
    with open(output, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter=delimiter)
        writer.writerow(columns)
        for item in sorted(items, key=lambda i: str(i.get('folder_name') or i.get('title') or '').lower()):
            folder = item.get('folder_name') or item.get('title')
            for kind, entries in (('standalone', item.get('downloads', [])), ('galaxy', item.get('galaxyDownloads', [])),
                                  ('shared', item.get('sharedDownloads', [])), ('extra', item.get('extras', []))):
                for entry in entries:
                    size = entry.get('size')
                    row = [item.get('id'), item.get('title'), folder, kind, entry.get('name') or '', entry.get('os_type') or '', entry.get('lang') or '',
                           entry.get('version') or '', size if size is not None else '', pretty_size(size) if isinstance(size, int) else '',
                           entry.get('md5') or '', entry.get('updated') or '']
                    if savedir:
                        path = os.path.join(savedir, str(folder), entry.get('name') or '')
                        if not entry.get('name'):
                            row.append('')
                        elif not os.path.isfile(path):
                            row.append('no')
                        elif size is not None and os.path.getsize(path) != size:
                            row.append('wrong size')
                        else:
                            row.append('yes')
                    writer.writerow(row)
                    rows += 1
    info("wrote %d files of %d games to %s (column separator '%s')" % (rows, len(items), output, delimiter))


# ---------------------------------------------------------------------------------------------------------------------
# wishlist (entry 44): the games on the GOG wishlist are not owned, so there is nothing to download for them; this saves the list
# (titles, store links, optionally prices) and shows what changed since the last run.
# The endpoints are not officially documented: embed.gog.com/user/wishlist.json answers {"wishlist": {"<id>": true, ...}, "checksum": ...};
# api.gog.com/products/<id> has the title; api.gog.com/products/<id>/prices?countryCode=DE lists the prices per currency as
# "<amount in cents> <currency>" strings (for example "999 EUR" for 9.99 EUR).
WISHLIST_FILENAME = r'gog-wishlist.json'
WISHLIST_CSV_FILENAME = r'gog-wishlist.csv'      # what -csv without a file name writes
WISHLIST_FORMAT = 1


class WishlistError(Exception):
    pass


def parse_gog_money(text):
    """('1999 EUR') -> (1999, 'EUR'): GOG writes prices as the amount in the smallest unit (cents) and the currency code. None if it is not that."""
    match = re.match(r'^\s*(-?\d+)\s+([A-Za-z]{3})\s*$', text) if isinstance(text, str) else None
    return (int(match.group(1)), match.group(2).upper()) if match else None


def choose_price(price_list, currency=None):
    """The price entry of GOG's list (one per currency) as {'currency', 'base', 'final', 'promo'} in cents, for the wanted currency or, without one,
    the first usable entry. None if there is none."""
    wanted = currency.upper() if currency else None
    for entry in price_list or []:
        base, final = parse_gog_money(entry.get('basePrice')), parse_gog_money(entry.get('finalPrice'))
        code = ((entry.get('currency') or {}).get('code') or '').upper()
        if base is None or final is None or not code or (wanted and code != wanted):
            continue
        return {'currency': code, 'base': base[0], 'final': final[0], 'promo': entry.get('promoId') or None}
    return None


def format_release_date(text):
    """The date part of GOG's release date ('2026-06-23T18:59:00+0200') as 2026-06-23, in every country. The day is the one in the text (no time zone
    conversion). Something that is not a date comes back unchanged.
    The ISO form is on purpose: a spreadsheet reads a date in the order of the computer's language, so '11/05/2026' becomes 11 May on a German
    Excel and '06/23/2026' stays text; 2026-11-05 is understood everywhere and then shown the local way."""
    match = re.match(r'^(\d{4}-\d{2}-\d{2})', text) if isinstance(text, str) else None
    return match.group(1) if match else (text or '')


def format_money(cents, currency, decimal='.'):
    return ('%d.%02d' % divmod(cents, 100)).replace('.', decimal) + ((' ' + currency) if currency else '')


def fetch_wishlist_ids(session):
    """The product ids on the wishlist of the logged-in account, as strings."""
    response = request(session, GOG_EMBED_URL + '/user/wishlist.json')
    try:
        data = response.json()
    except ValueError:
        raise WishlistError('GOG did not answer with a wishlist (the login may have expired: run the login command again)')
    wishlist = data.get('wishlist') if isinstance(data, dict) else None
    if isinstance(wishlist, list):          # an empty wishlist comes as [] and not as {} (a list of ids is accepted too)
        wishlist = {str(i): True for i in wishlist}
    if not isinstance(wishlist, dict):
        raise WishlistError('the answer of GOG has no "wishlist" list')
    ids = [str(key) for key, wanted in wishlist.items() if wanted]
    return sorted(ids, key=lambda i: (0, int(i)) if i.isdigit() else (1, i))


def fetch_wishlist_details(session, product_id):
    """{'title', 'slug', 'release_date', 'store_url'} of a product, or None if GOG does not know it (any more)."""
    try:
        data = request(session, GOG_API_URL + '/products/{}'.format(product_id), quiet_statuses=(404,)).json()
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            return None
        raise
    slug = data.get('slug')
    store_url = (data.get('links') or {}).get('product_card') or (('https://www.gog.com/game/' + slug) if slug else None)
    return {'title': data.get('title'), 'slug': slug, 'release_date': data.get('release_date'), 'store_url': store_url}


def fetch_wishlist_price(session, product_id, country, currency=None):
    """The price of a product (see choose_price), or None if it has none (not on sale in the store, or not for that country)."""
    try:
        data = request(session, GOG_API_URL + '/products/{}/prices'.format(product_id), args={'countryCode': country}, quiet_statuses=(400, 404),
                       no_retry_statuses=(400,)).json()
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else None
        if status == 404:
            return None
        if status == 400:       # GOG's answer to a country it does not know, for example UK (the code is GB)
            raise WishlistError("GOG does not accept '%s' as a country for the prices; use the two-letter ISO code, for example GB for the United Kingdom" % country)
        raise
    return choose_price(((data.get('_embedded') or {}).get('prices')), currency)


def load_wishlist(path):
    """{id: entry} of the last saved wishlist, or None for a first run (no file, or one that cannot be read)."""
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        games = data['games']
        if not isinstance(games, dict):
            raise ValueError('"games" is not a list')
        return games
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError) as e:
        warn("the saved wishlist '%s' cannot be read (%s); treating this as a first run" % (path, e))
        return None


def wishlist_changes(old, new, library_ids=()):
    """What changed between two saved wishlists ({id: entry}): lists of ids 'added', 'removed', 'now_owned' (removed and in the library),
    'cheaper' and 'dearer' (the final price in the same currency changed)."""
    library_ids = set(str(i) for i in library_ids)
    changes = {'added': [], 'removed': [], 'now_owned': [], 'cheaper': [], 'dearer': []}
    for game_id in new:
        if game_id not in old:
            changes['added'].append(game_id)
            continue
        before, after = old[game_id].get('price'), new[game_id].get('price')
        if before and after and before.get('currency') == after.get('currency') and before.get('final') != after.get('final'):
            changes['cheaper' if after['final'] < before['final'] else 'dearer'].append(game_id)
    for game_id in old:
        if game_id not in new:
            changes['removed'].append(game_id)
            if game_id in library_ids:
                changes['now_owned'].append(game_id)
    return changes


def write_wishlist_csv(path, games, library_ids, delimiter):
    decimal = ',' if delimiter == ';' else '.'          # a spreadsheet that wants ';' between columns writes decimals with a comma
    columns = ['game id', 'title', 'release date', 'store url', 'in library', 'currency', 'regular price', 'price', 'discount %', 'promo']
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f, delimiter=delimiter)
        writer.writerow(columns)
        for game_id, game in sorted(games.items(), key=lambda kv: str(kv[1].get('title') or '').lower()):
            price = game.get('price') or {}
            discount = ''
            if price and price.get('base'):
                discount = int(round(100.0 * (price['base'] - price['final']) / price['base']))
            writer.writerow([game_id, game.get('title') or '', format_release_date(game.get('release_date')), game.get('store_url') or '',
                             'yes' if str(game_id) in library_ids else 'no', price.get('currency', ''),
                             format_money(price['base'], '', decimal) if price else '', format_money(price['final'], '', decimal) if price else '',
                             discount, price.get('promo') or ''])


def file_write_message(path, error_found):
    """The message for a file that cannot be written; on Windows a spreadsheet program that has the file open is the usual reason."""
    return ('cannot write %s (%s). If the file is open in another program, for example Excel, please close it and run the command again.'
            % (path, getattr(error_found, 'strerror', None) or error_found))


def file_write_problem(path):
    """None if the file can be written (opening it for appending changes nothing), else the OSError. A file that is open in a spreadsheet program
    is refused here (PermissionError on Windows). A file that did not exist is not left behind."""
    existed = os.path.exists(path)
    try:
        open(path, 'a').close()
    except OSError as e:
        return e
    if not existed:
        try:
            os.remove(path)
        except OSError:
            pass
    return None


def cmd_wishlist(output=WISHLIST_FILENAME, csv_output=None, prices=False, country=None, currency=None, delimiter=None):
    """Save the GOG wishlist to a JSON file and say what changed since the last run: new games, removed games (and those that are now in the
    library), and with prices the games that became cheaper or dearer. The details of a game are fetched once and kept in the file."""
    country = (country or '').strip().upper()
    if country == 'UK':
        info("'UK' is not an ISO country code; using GB")
        country = 'GB'
    if country and not re.match(r'^[A-Z]{2}$', country):
        error("-country must be a two-letter country code like DE or US (got '%s')" % country)
        run_report.fail('wishlist', 'invalid country')
        return
    price_country = country or 'US'                       # the prices need a country
    if csv_output:                                        # before anything is fetched: a CSV file that is open in Excel cannot be written
        problem = file_write_problem(csv_output)
        if problem is not None:
            error(file_write_message(csv_output, problem))
            run_report.fail('csv', 'file cannot be written')
            return
    session = makeGOGSession()
    previous = load_wishlist(output)
    try:
        ids = fetch_wishlist_ids(session)
    except (WishlistError, requests.RequestException) as e:
        error('could not read the wishlist: %s' % e)
        run_report.fail('wishlist', 'could not be read')
        return
    try:
        library_ids = set(str(g.id) for g in load_manifest())
    except Exception:                                          # the comparison with the library is a bonus
        library_ids = set()
    games = {}
    for game_id in ids:
        old = (previous or {}).get(game_id) or {}
        entry = dict(old) if old.get('title') else {}
        entry['id'] = game_id
        if not entry.get('title'):
            try:
                details = fetch_wishlist_details(session, game_id)
            except requests.RequestException as e:
                warn('no details for wishlist game %s: %s' % (game_id, e))
                run_report.fail(game_id, 'details not available')
                details = None
            if details is None:
                warn('GOG has no details for wishlist game %s (not in the store any more?)' % game_id)
            else:
                entry.update(details)
        if prices:
            try:
                entry['price'] = fetch_wishlist_price(session, game_id, price_country, currency)
            except WishlistError as e:                          # GOG does not accept the country: asking again for every game would not help
                error(str(e))
                run_report.fail('prices', 'country not accepted')
                prices = False
                entry['price'] = old.get('price')
            except requests.RequestException as e:
                warn('no price for %s: %s' % (entry.get('title') or game_id, e))
                run_report.fail(entry.get('title') or game_id, 'price not available')
                entry['price'] = old.get('price')               # keep what was known, so that no change is reported by mistake
        else:
            entry['price'] = old.get('price')
        games[game_id] = entry
    run_report.count('wishlist games', len(games))

    def name(game_id):
        return (games.get(game_id) or (previous or {}).get(game_id) or {}).get('title') or game_id

    def money(price):
        return format_money(price['final'], price['currency']) if price else 'no price'

    info('the wishlist has %d games' % len(games))
    if previous is None:
        info('first run: nothing to compare with yet')
    else:
        changes = wishlist_changes(previous, games, library_ids)
        for game_id in changes['added']:
            info('new on the wishlist: %s%s' % (name(game_id), (' (' + money(games[game_id].get('price')) + ')') if games[game_id].get('price') else ''))
        for game_id in changes['removed']:
            info('no longer on the wishlist: %s%s' % (name(game_id), ' (now in your library)' if game_id in changes['now_owned'] else ''))
        for label, key in (('cheaper', 'cheaper'), ('dearer', 'dearer')):
            for game_id in changes[key]:
                info('%s: %s -> %s (%s)' % (name(game_id), money(previous[game_id].get('price')), money(games[game_id].get('price')), label))
        if not any(changes.values()):
            info('no changes since the last run')
    # The CSV is written before the saved list is updated: if it cannot be (the file was opened in the meantime), the next run still reports the changes.
    if csv_output:
        delimiter = delimiter or default_csv_delimiter()
        try:
            write_wishlist_csv(csv_output, games, library_ids, delimiter)
        except OSError as e:
            error(file_write_message(csv_output, e))
            run_report.fail('csv', 'file cannot be written')
            return
        info("wrote %d games to %s (column separator '%s')" % (len(games), csv_output, delimiter))
    state = {'format': WISHLIST_FORMAT, 'saved': datetime.datetime.now().replace(microsecond=0).isoformat(), 'country': price_country if prices else None,
             'games': games}
    try:
        atomic_write_text(output, lambda w: json.dump(state, w, indent=2, ensure_ascii=False, sort_keys=True))
    except OSError as e:
        error(file_write_message(output, e))
        run_report.fail('wishlist', 'file cannot be written')
        return
    info("saved the wishlist to %s" % output)


def cmd_backup(src_dir, dest_dir,skipextras,os_list,lang_list,ids,skipids,skipgalaxy,skipstandalone,skipshared,lang_fallback=None):
    gamesdb = load_manifest()
    selected_ids = resolve_ids_and_report(gamesdb, ids, '-ids') if ids else None       # the games that -ids means ...
    skipped_ids = resolve_ids_and_report(gamesdb, skipids, '-skipids') if skipids else set()   # ... and -skipids

    for game in gamesdb:
        try:
            _ = game.folder_name
        except AttributeError:
            game.folder_name = game.title

    info('finding all known files in the manifest')
    for game in sorted(gamesdb, key=lambda g: g.folder_name):
        touched = False

        try:
            _ = game.galaxyDownloads
        except AttributeError:
            game.galaxyDownloads = []

        try:
            a = game.sharedDownloads
        except AttributeError:
            game.sharedDownloads = []


        if skipextras:
            game.extras = []

        if skipstandalone:
            game.downloads = []

        if skipgalaxy:
            game.galaxyDownloads = []

        if skipshared:
            game.sharedDownloads = []

        if selected_ids is not None and game.id not in selected_ids:
            continue
        if game.id in skipped_ids:
            continue


        downloadsOS = [game_item for game_item in game.downloads if game_item.os_type in os_list]
        game.downloads = downloadsOS

        downloadsOS = [game_item for game_item in game.galaxyDownloads if game_item.os_type in os_list]
        game.galaxyDownloads = downloadsOS

        downloadsOS = [game_item for game_item in game.sharedDownloads if game_item.os_type in os_list]
        game.sharedDownloads = downloadsOS


        valid_langs = []
        for lang in lang_list:
            valid_langs.append(LANG_TABLE[lang])

        fallback_name = LANG_TABLE[lang_fallback] if lang_fallback else None
        game.downloads = filter_languages(game.downloads, valid_langs, fallback_name)
        game.galaxyDownloads = filter_languages(game.galaxyDownloads, valid_langs, fallback_name)
        game.sharedDownloads = filter_languages(game.sharedDownloads, valid_langs, fallback_name)


        for itm in game.downloads + game.galaxyDownloads + game.sharedDownloads + game.extras:
            if itm.name is None:
                continue



            src_game_dir = os.path.join(src_dir, game.folder_name)
            src_file = os.path.join(src_game_dir, itm.name)
            dest_game_dir = os.path.join(dest_dir, game.folder_name)
            dest_file = os.path.join(dest_game_dir, itm.name)

            if os.path.isfile(src_file):
                if itm.size != os.path.getsize(src_file):
                    warn('source file %s has unexpected size. skipping.' % src_file)
                    run_report.fail(src_file, 'source file has an unexpected size, not backed up')
                    continue
                if not os.path.isdir(dest_game_dir):
                    os.makedirs(dest_game_dir)
                if not os.path.exists(dest_file) or itm.size != os.path.getsize(dest_file):
                    info('copying to %s...' % dest_file)
                    shutil.copy(src_file, dest_file)
                    run_report.count('files copied', 1, itm.size)
                    touched = True
                else:
                    run_report.count('files already in the backup')

        # backup the info and serial files too
        if touched and os.path.isdir(dest_game_dir):
            for extra_file in [INFO_FILENAME, SERIAL_FILENAME]:
                if os.path.exists(os.path.join(src_game_dir, extra_file)):
                    shutil.copy(os.path.join(src_game_dir, extra_file), dest_game_dir)


def cmd_verify(gamedir, skipextras, skipids,  check_md5, check_filesize, check_zips, delete_on_fail, clean_on_fail, ids, os_list, lang_list, skipgalaxy,skipstandalone,skipshared, skipfiles, force_verify, permissive_change_clear,high_memory,free_tmp_space,lang_fallback=None,use_blake3=True):
    """Verifies all game files match manifest with any available md5 & file size info.

    Entry 38 - BLAKE3 (optional, needs the blake3 package; use_blake3=False switches it off): a file that passes its checks gets
    its BLAKE3 recorded in the manifest ("trust on first verify"). A later full verification (-forceverify) compares only that
    BLAKE3 - fast, and it detects changes since the file last passed. If the BLAKE3 differs and the MD5 is known, the MD5 decides
    (a matching MD5 means the recorded BLAKE3 was stale and is refreshed)."""
    item_count = 0
    missing_cnt = 0
    bad_md5_cnt = 0
    bad_size_cnt = 0
    bad_zip_cnt = 0
    del_file_cnt = 0
    clean_file_cnt = 0
    prev_verified_cnt = 0
    skip_cnt = 0
    bad_b3_cnt = 0
    b3_match_cnt = 0
    b3_recorded_cnt = 0
    b3_on = False
    if use_blake3:
        if blake3_available():
            b3_on = True
        else:
            info('the blake3 package is not installed, so no BLAKE3 checksums are recorded or compared (python -m pip install blake3; -noblake3 hides this message)')

    items = load_manifest()

    save_manifest_needed = False;

    for item in items:
        try:
            _ = item.folder_name
        except AttributeError:
            item.folder_name = item.title

    games_to_check_base = sorted(items, key=lambda g: g.folder_name)

    if skipids:
        formattedSkipIds =  ', '.join(map(str, skipids))
        info('skipping files with ids in {%s}' % formattedSkipIds)
        skipped = resolve_ids_and_report(games_to_check_base, skipids, '-skipids')    # also reports what matches no game
        games_to_check = [game for game in games_to_check_base if game.id not in skipped]
    elif ids:
        selected = resolve_ids_and_report(games_to_check_base, ids, '-ids')
        games_to_check = [game for game in games_to_check_base if game.id in selected]
        if not games_to_check:
            formattedIds =  ', '.join(map(str, ids))
            warn('no known files with ids in {%s} where found' % formattedIds)
            return
    else:
        info('verifying all known files in the manifest')
        games_to_check =  games_to_check_base

    if skipfiles:
        formattedSkipFiles = "'" + "', '".join(skipfiles) + "'"
        info("skipping files that match: {%s}" % formattedSkipFiles)

    handle_game_renames(gamedir,items,False)


    if clean_on_fail:
        # create orphan root dir
        orphan_root_dir = os.path.join(gamedir, ORPHAN_DIR_NAME)
        if not os.path.isdir(orphan_root_dir):
            os.makedirs(orphan_root_dir)



    for game in games_to_check:
        game_changed = False
        try:
            _ = game.galaxyDownloads
        except AttributeError:
            game.galaxyDownloads = []
            game_changed = True;

        try:
            a = game.sharedDownloads
        except AttributeError:
            game.sharedDownloads = []
            game_changed = True;


        if skipextras:
            verify_extras = []
        else:
            verify_extras = game.extras

        if skipstandalone:
            verify_downloads = []
        else:
            verify_downloads = game.downloads

        if skipgalaxy:
           verify_galaxyDownloads = []
        else:
            verify_galaxyDownloads = game.galaxyDownloads

        if skipshared:
            verify_sharedDownloads = []
        else:
            verify_sharedDownloads = game.sharedDownloads


        downloadsOS = [game_item for game_item in verify_downloads if game_item.os_type in os_list]
        verify_downloads = downloadsOS

        downloadsOS = [game_item for game_item in verify_galaxyDownloads if game_item.os_type in os_list]
        verify_galaxyDownloads = downloadsOS

        downloadsOS = [game_item for game_item in verify_sharedDownloads if game_item.os_type in os_list]
        verify_sharedDownloads = downloadsOS


        valid_langs = []
        for lang in lang_list:
            valid_langs.append(LANG_TABLE[lang])

        fallback_name = LANG_TABLE[lang_fallback] if lang_fallback else None
        verify_downloads = filter_languages(verify_downloads, valid_langs, fallback_name)
        verify_galaxyDownloads = filter_languages(verify_galaxyDownloads, valid_langs, fallback_name)
        verify_sharedDownloads = filter_languages(verify_sharedDownloads, valid_langs, fallback_name)

        zipSplitArchiveFailCache = []

        game_missing = []      # Refactoring: the files of this game that are missing, reported together after the loop below
        game_files = len(verify_downloads + verify_galaxyDownloads + verify_sharedDownloads + verify_extras)
        for itm in verify_downloads + verify_galaxyDownloads + verify_sharedDownloads +verify_extras:
            try:
                _ = itm.prev_verified
            except AttributeError:
                itm.prev_verified = False
                game_changed = True;

            try:
                _ = itm.unreleased
            except AttributeError:
                itm.unreleased = False

            if itm.unreleased:
                continue

            if itm.name is None:
                warn('no known filename for "%s (%s)"' % (game.title, itm.desc))
                continue

            item_count += 1

            skipfile_skip = check_skip_file(itm.name, skipfiles)
            if skipfile_skip:
                info('skipping %s (matches %s)' % (itm.name, skipfile_skip))
                skip_cnt += 1
                continue

            itm_dirpath = os.path.join(game.folder_name, itm.name)
            itm_file = os.path.join(gamedir, game.folder_name, itm.name)



            if os.path.isfile(itm_file):
                info('verifying %s...' % itm_dirpath)


                if itm.prev_verified and not force_verify:
                    info('skipping previously verified %s' % itm_dirpath)
                    prev_verified_cnt += 1
                    continue


                fail = False
                if check_filesize and itm.size is not None:
                    if itm.size != os.path.getsize(itm_file):
                        warn('mismatched file size for %s' % itm_dirpath)
                        run_report.fail(itm_dirpath, 'wrong file size')
                        bad_size_cnt += 1
                        fail = True
                # Entry 38: BLAKE3 is not used for a file without md5 that is flagged as changed (the recorded one may be of the old content)
                item_b3 = b3_on and not (itm.md5 is None and getattr(itm, 'force_change', False))
                stored_b3 = (getattr(itm, 'blake3', None) or None) if item_b3 else None
                want_md5 = check_md5 and itm.md5 is not None
                md5_proven = False      # the content is known to equal what the manifest's md5 describes
                record_b3 = None        # a BLAKE3 to store in the manifest if the file passes everything
                if not fail and stored_b3:
                    current_b3 = hash_file(itm_file, md5=False, blake3=True)['blake3']
                    if current_b3 == stored_b3:
                        b3_match_cnt += 1
                        md5_proven = itm.md5 is not None    # a recorded BLAKE3 only exists for content that passed the md5 check
                    elif want_md5:
                        if itm.md5 == hashfile(itm_file):
                            warn('the recorded blake3 of %s was stale (the md5 matches); it is refreshed' % itm_dirpath)
                            record_b3 = current_b3
                            md5_proven = True
                        else:
                            warn('mismatched md5 for %s' % itm_dirpath)
                            run_report.fail(itm_dirpath, 'wrong checksum (md5)')
                            bad_md5_cnt += 1
                            fail = True
                    else:
                        warn('blake3 of %s differs from the one recorded when it last passed verification' % itm_dirpath)
                        run_report.fail(itm_dirpath, 'changed since last verification (blake3)')
                        bad_b3_cnt += 1
                        fail = True
                elif not fail:
                    # Both hashes in one read pass. A BLAKE3 baseline is only recorded for a file whose content was actually
                    # confirmed: by its md5, or - for types without md5 - by a known size (the zip test follows below).
                    hash_md5 = want_md5
                    hash_b3 = item_b3 and (want_md5 or (itm.md5 is None and check_filesize and itm.size is not None))
                    if hash_md5 or hash_b3:
                        hashes = hash_file(itm_file, md5=hash_md5, blake3=hash_b3)  #MD5 is not reliable if size doesn't match
                        if hash_md5:
                            if itm.md5 != hashes['md5']:
                                warn('mismatched md5 for %s' % itm_dirpath)
                                run_report.fail(itm_dirpath, 'wrong checksum (md5)')
                                bad_md5_cnt += 1
                                fail = True
                            else:
                                md5_proven = True
                        if hash_b3 and not fail:
                            record_b3 = hashes['blake3']
                if not fail and check_zips:
                     #Doesn't matter if it's a valid zip if size / MD5 are wrong, it's not the right zip
                    if (itm.name.lower().endswith('.zip.001')):
                            badZipException = zipfile.BadZipFile

                            multiZipNames = _multi_zip_parts(itm.name, itm_file)
                            multiZipNamesSort = []
                            for multiZipName in multiZipNames:
                                ext = os.path.splitext(multiZipName)[1].lstrip('.')
                                if ext.isdigit():
                                    multiZipNamesSort.append((int(ext), multiZipName))
                            multiZipNamesSort.sort(key=lambda x: x[0])
                            multiZipNames = [x for _,x in multiZipNamesSort]
                            multiZip = [os.path.join(gamedir, game.folder_name, x) for x in multiZipNames]
                            if (high_memory or free_tmp_space):
                                blocksize = 65536
                                try:
                                    with (io.BytesIO() if high_memory else tempfile.TemporaryFile()) as tmpfullzip:
                                        for zipName in multiZip:
                                            with open(zipName, "rb") as z:
                                                buf = z.read(blocksize)
                                                debug("Reading: " + zipName)
                                                while len(buf) > 0:
                                                    tmpfullzip.write(buf)
                                                    buf = z.read(blocksize)

                                        zipfile.ZipFile(tmpfullzip).testzip()
                                except (badZipException,zlib.error) as e:
                                    zipSplitArchiveFailCache = zipSplitArchiveFailCache + multiZipNames
                                    warn('zip test failed for %s' % itm_dirpath)
                                    run_report.fail(itm_dirpath, 'zip test failed')
                                    fail = True
                                    bad_zip_cnt += 1
                                except MemoryError:
                                    warn('Not enough memory to test zip archive set, falling back to name/size check for %s' % itm_dirpath)
                                except IOError as e:
                                    if e.errno == errno.ENOSPC:
                                        warn('Not enough disk space to test zip archive set, falling back to name/size check for %s' % itm_dirpath)
                                    elif e.errno == errno.EDQUOT:
                                        warn('Not enough disk quota to test zip archive set, falling back to name/size check for %s' % itm_dirpath)
                                    else:
                                        raise
                                except NotImplementedError: #Temp work around until implement support
                                    warn('Unsupported file compression method, falling back to name/size check for %s' % itm_dirpath)
                    elif itm.name in zipSplitArchiveFailCache:
                        warn('zip test failed for %s' % itm_dirpath)
                        run_report.fail(itm_dirpath, 'zip test failed')
                        fail = True
                        bad_zip_cnt += 1
                    elif itm.name.lower().endswith('.zip'):
                        try:
                            if not test_zipfile(itm_file):
                                warn('zip test failed for %s' % itm_dirpath)
                                run_report.fail(itm_dirpath, 'zip test failed')
                                bad_zip_cnt += 1
                                fail = True
                        except NotImplementedError: #Temp work around until implement support
                            warn('Unsupported file compression method, falling back to name/size check for %s' % itm_dirpath)
                if delete_on_fail and fail:
                    info('deleting %s' % itm_dirpath)
                    os.remove(itm_file)
                    del_file_cnt += 1
                if clean_on_fail and fail:
                    info('cleaning %s' % itm_dirpath)
                    clean_file_cnt += 1
                    dest_dir = os.path.join(orphan_root_dir, game.title)
                    if not os.path.isdir(dest_dir):
                        os.makedirs(dest_dir)
                    move_with_increment_on_clash(itm_file, os.path.join(dest_dir,itm.name))
                old_verify = itm.prev_verified
                try:
                    old_force_change = itm.force_change
                except AttributeError:
                    itm.force_change = False
                    old_force_change = False
                try:
                    old_last_updated = itm.old_updated
                except AttributeError:
                    itm.old_updated = None
                    old_last_updated = None
                if not fail:
                    itm.prev_verified= True;
                    if md5_proven:
                        itm.force_change = False #Verified as correct by MD5 match (or by the BLAKE3 recorded for an MD5-verified file)
                        itm.old_updated = itm.updated
                    if record_b3 and getattr(itm, 'blake3', None) != record_b3:
                        itm.blake3 = record_b3
                        b3_recorded_cnt += 1
                        game_changed = True
                    if permissive_change_clear:
                        itm.force_change = False #Flag has been set to accept matching name / size and passing the zip test as the correct file
                        itm.old_updated = itm.updated
                else:
                    itm.prev_verified=False;
                if (old_verify != itm.prev_verified or old_last_updated != itm.old_updated or itm.force_change != old_force_change):
                    game_changed = True;
            else:
                if itm.prev_verified:
                    itm.prev_verified=False;
                    game_changed = True
                game_missing.append(itm_dirpath)
                run_report.fail(itm_dirpath, 'missing')
                missing_cnt += 1
        if game_missing:
            # Refactoring: a game that has not been downloaded (yet) printed one warning per file, 99 lines for 14 games. Up to
            # MISSING_FILES_LISTED files are still named; beyond that one line per game says how many, and the names go to debug.
            if len(game_missing) <= MISSING_FILES_LISTED:
                for missing_path in game_missing:
                    warn('missing file %s' % missing_path)
            else:
                warn('%s: %d of %d files missing' % (game.folder_name, len(game_missing), game_files))
                for missing_path in game_missing:
                    debug('missing file %s' % missing_path)
        if (game_changed):
            item_idx = item_checkdb(game.id, items)
            if item_idx is not None:
                items[item_idx] = game
                save_manifest(items)
            else:
                warn("We are verifying an item that's not in the DB ???")

    info('')
    info('--totals------------')
    info('known items......... %d' % item_count)
    if not force_verify:
        info('pre-verified items.. %d' % prev_verified_cnt)
    run_report.count('files in the manifest', item_count)
    run_report.count('files present', item_count - missing_cnt - del_file_cnt - clean_file_cnt)
    info('have items.......... %d' % (item_count - missing_cnt - del_file_cnt - clean_file_cnt))
    info('skipped items....... %d' % skip_cnt)
    info('missing items....... %d' % (missing_cnt + del_file_cnt + clean_file_cnt))
    if check_md5:
        info('md5 mismatches...... %d' % bad_md5_cnt)
    if b3_on:
        info('blake3 matches...... %d' % b3_match_cnt)
        info('blake3 recorded..... %d' % b3_recorded_cnt)
        info('blake3 mismatches... %d' % bad_b3_cnt)
    if check_filesize:
        info('size mismatches..... %d' % bad_size_cnt)
    if check_zips:
        info('zipfile failures.... %d' % bad_zip_cnt)
    if delete_on_fail:
        info('deleted items....... %d' % del_file_cnt)
    if clean_on_fail:
        info('cleaned items....... %d' % clean_file_cnt)

def cmd_trash(cleandir,installers,images,folders,relaxed,dryrun):
    orphaned_root_dir = os.path.join(cleandir, ORPHAN_DIR_NAME)
    for dir in os.listdir(orphaned_root_dir):
        testdir= os.path.join(orphaned_root_dir,dir)
        if os.path.isdir(testdir):
            reference_dir = os.path.join(cleandir,dir)
            refresh_contents = False
            if folders:
                if relaxed or os.path.isdir(reference_dir):
                    try:
                        if (not dryrun):
                            shutil.rmtree(testdir)
                            run_report.count('folders deleted')
                        info("Deleting " + testdir)
                    except Exception as e:
                        error("Failed to delete directory: " + testdir)
                        run_report.fail(testdir, 'could not be deleted: ' + str(e))
            if os.path.isdir(testdir):
                contents = os.listdir(testdir)
                if images:
                    images_folder = os.path.join(testdir,IMAGES_DIR_NAME)
                    if os.path.isdir(images_folder):
                        if relaxed or os.path.isdir(os.path.join(reference_dir,IMAGES_DIR_NAME)):
                            if (not dryrun):
                                shutil.rmtree(images_folder)
                                run_report.count('image folders deleted')
                                refresh_contents=True
                            info("Deleting " + images_folder )
                if (refresh_contents):
                    contents = os.listdir(testdir)
                    refresh_contents = False
                if installers:
                    deletecontents = [x for x in contents if (len(x.rsplit(os.extsep,1)) > 1 and (os.extsep + x.rsplit(os.extsep,1)[1]) in INSTALLERS_EXT)]
                    for content in deletecontents:
                        contentpath = os.path.join(testdir,content)
                        if (not dryrun):
                            os.remove(contentpath)
                            run_report.count('files deleted', 1)
                            refresh_contents=True
                        info("Deleting " + contentpath )
                if (refresh_contents):
                    contents = os.listdir(testdir)
                    refresh_contents = False
                if not os.path.isdir(reference_dir):
                    info("Reference directory does not exist so {} can't have duplicates. ".format(testdir))
                else:
                    for content in contents:
                        content_path = os.path.join(testdir,content)
                        reference_content_path = os.path.join(reference_dir,content)
                        if os.path.isfile(reference_content_path):
                            if relaxed or ( os.path.getsize(content_path) == os.path.getsize(reference_content_path) and hashfile(content_path) == hashfile(reference_content_path)):
                                if (not dryrun):
                                    os.remove(content_path)
                                    run_report.count('files deleted', 1)
                                    refresh_contents=True
                                info("Deleting " + content_path )
                if (refresh_contents):
                    contents = os.listdir(testdir)
                    refresh_contents = False
                if (len(contents) == 0):
                    try:
                        if (not dryrun):
                            os.rmdir(testdir)
                        info("Removed empty directory " + testdir)
                    except OSError:
                        pass


def cmd_clear_partial_downloads(cleandir,dryrun):
    downloading_root_dir = os.path.join(cleandir, DOWNLOADING_DIR_NAME)
    for dir in os.listdir(downloading_root_dir):
        if dir != PROVISIONAL_DIR_NAME:
            testdir= os.path.join(downloading_root_dir,dir)
            if os.path.isdir(testdir):
                try:
                    if (not dryrun):
                        shutil.rmtree(testdir)
                        run_report.count('partial download folders deleted')
                    info("Deleting " + testdir)
                except Exception as e:
                    error("Failed to delete directory: " + testdir)
                    run_report.fail(testdir, 'could not be deleted: ' + str(e))

    provisional_root_dir = os.path.join(cleandir, DOWNLOADING_DIR_NAME,PROVISIONAL_DIR_NAME)
    for dir in os.listdir(provisional_root_dir):
        testdir= os.path.join(downloading_root_dir,dir)
        if os.path.isdir(testdir):
            try:
                if (not dryrun):
                    shutil.rmtree(testdir)
                    run_report.count('partial download folders deleted')
                info("Deleting " + testdir)
            except Exception as e:
                error("Failed to delete directory: " + testdir)
                run_report.fail(testdir, 'could not be deleted: ' + str(e))


def cmd_clean(cleandir, dryrun):
    items = load_manifest()
    items_by_title = {}
    total_size = 0  # in bytes
    have_cleaned = False


    # make convenient dict with title/dirname as key
    for item in items:
        try:
            _ = item.folder_name
        except AttributeError:
            item.folder_name = item.title
        items_by_title[item.folder_name] = item

    # create orphan root dir
    orphan_root_dir = os.path.join(cleandir, ORPHAN_DIR_NAME)
    if not os.path.isdir(orphan_root_dir):
        if not dryrun:
            os.makedirs(orphan_root_dir)

    info("scanning local directories within '{}'...".format(cleandir))
    handle_game_renames(cleandir,items,dryrun)
    for cur_dir in sorted(os.listdir(cleandir)):
        changed_game_items = {}
        cur_fulldir = os.path.join(cleandir, cur_dir)
        if os.path.isdir(cur_fulldir) and cur_dir not in ORPHAN_DIR_EXCLUDE_LIST:
            if cur_dir not in items_by_title:
                info("orphaning dir  '{}'".format(cur_dir))
                have_cleaned = True
                total_size += get_total_size(cur_fulldir)
                if not dryrun:
                    move_with_increment_on_clash(cur_fulldir, os.path.join(orphan_root_dir,cur_dir))
                    run_report.count('folders moved to the orphan folder')
            else:
                # dir is valid game folder, check its files
                expected_filenames = []
                for game_item in items_by_title[cur_dir].downloads + items_by_title[cur_dir].galaxyDownloads + items_by_title[cur_dir].sharedDownloads + items_by_title[cur_dir].extras:
                    try:
                        _ = game_item.force_change
                    except AttributeError:
                        game_item.force_change = False
                    try:
                        _ = game_item.updated
                    except AttributeError:
                        game_item.updated = None
                    try:
                        _ = game_item.old_updated
                    except AttributeError:
                        game_item.old_updated = None
                    expected_filenames.append(game_item.name)

                    if game_item.force_change == True:
                        changed_game_items[game_item.name] = game_item
                for cur_dir_file in os.listdir(cur_fulldir):
                    if os.path.isdir(os.path.join(cleandir, cur_dir, cur_dir_file)):
                        continue  # leave subdirs alone
                    if cur_dir_file not in expected_filenames and cur_dir_file not in ORPHAN_FILE_EXCLUDE_LIST:
                        info("orphaning file '{}'".format(os.path.join(cur_dir, cur_dir_file)))
                        dest_dir = os.path.join(orphan_root_dir, cur_dir)
                        if not os.path.isdir(dest_dir):
                            if not dryrun:
                                os.makedirs(dest_dir)
                        file_to_move = os.path.join(cleandir, cur_dir, cur_dir_file)
                        if not dryrun:
                            try:
                                file_size = os.path.getsize(file_to_move)
                                move_with_increment_on_clash(file_to_move, os.path.join(dest_dir,cur_dir_file))
                                have_cleaned = True
                                total_size += file_size
                                run_report.count('files moved to the orphan folder', 1, file_size)
                            except Exception as e:
                                error(str(e))
                                error("could not move to destination '{}'".format(os.path.join(dest_dir,cur_dir_file)))
                                run_report.fail(os.path.join(cur_dir, cur_dir_file), 'could not be moved to the orphan folder: ' + str(e))
                        else:
                            have_cleaned = True
                            total_size += os.path.getsize(file_to_move)
                    #print(changed_game_items.keys())
                    #print(cur_dir_file)
                    if cur_dir_file in changed_game_items.keys() and cur_dir_file in expected_filenames:
                        info("orphaning file '{}' as it has been marked for change.".format(os.path.join(cur_dir, cur_dir_file)))
                        dest_dir = os.path.join(orphan_root_dir, cur_dir)
                        if not os.path.isdir(dest_dir):
                            if not dryrun:
                                os.makedirs(dest_dir)
                        file_to_move = os.path.join(cleandir, cur_dir, cur_dir_file)
                        if not dryrun:
                            try:
                                file_size = os.path.getsize(file_to_move)
                                move_with_increment_on_clash(file_to_move, os.path.join(dest_dir,cur_dir_file))
                                have_cleaned = True
                                total_size += file_size
                                run_report.count('files moved to the orphan folder', 1, file_size)
                                changed_item =  changed_game_items[cur_dir_file]
                                #changed_item.old_updated = changed_item.updated
                                #changed_item.force_change = False
                                #changed_item.prev_verified = False
                            except Exception as e:
                                error(str(e))
                                error("could not move to destination '{}'".format(os.path.join(dest_dir,cur_dir_file)))
                                run_report.fail(os.path.join(cur_dir, cur_dir_file), 'could not be moved to the orphan folder: ' + str(e))

    if have_cleaned:
        info('')
        info('total size of newly orphaned files: {}'.format(pretty_size(total_size)))
        if not dryrun:
            info('orphaned items moved to: {}'.format(orphan_root_dir))
            save_manifest(items)
    else:
        info('nothing to clean. nice and tidy!')

def update_self():
    #To-Do: add auto-update to main using Last-Modified (repo for rolling, latest release for standard)
    #Add a dev mode which skips auto-updates and a manual update command which can specify rolling/standard
    # Since 302 is not an error can use the standard session handling for this. Rewrite appropriately
    gitSession = makeGitHubSession()
    #if mode = Standard
    response = gitSession.get(REPO_HOME_URL+NEW_RELEASE_URL,stream="False",timeout=HTTP_TIMEOUT,headers={'If-Modified-Since':'Mon, 16 Jul 2018 08:51:22 GMT'})
    response.raise_for_status()
    if response.status_code == 304:
        info("Not Modified")
        sys.exit()
    debug("%s", response.headers)
    jsonResponse = response.json()
    debug("%s", response.headers)
    debug("%s", jsonResponse)
    with open('updatetest.test', mode='w', encoding='utf-8') as w:
        debug("%s", response.headers)
        print(jsonResponse, file=w)
    response = gitSession.get(jsonResponse['tarball_url'],stream="False",timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    rawResponse = response.content
    debug("%s", response.headers)
    with open('tarballupdatetest.test', mode='w', encoding='utf-8') as w:
        print(response.headers,file=w)
    with open_notrunc('update.tar.gz') as w:
        w.write(rawResponse)

    #if mode = Rolling
    response = gitSession.get(REPO_HOME_URL,stream="False",timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    jsonResponse = response.json()
    debug("%s", response.headers)
    debug("%s", jsonResponse)
    with open('rollingupdatetest.test', mode='w', encoding='utf-8') as w:
        print(response.headers,file=w)
        print(jsonResponse, file=w)
    response = gitSession.get(REPO_HOME_URL+"/tarball/master",stream="False",timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    rawResponse = response.content
    debug("%s", response.headers)
    with open('tarballrollingupdatetest.test', mode='w', encoding='utf-8') as w:
        print(response.headers,file=w)
    with open_notrunc('rolling.tar.gz') as w:
        w.write(rawResponse)

def purge_md5_chunkdata():
    all_games = load_manifest()
    for game in all_games:
        for item in game.downloads + game.galaxyDownloads + game.extras + game.sharedDownloads:
            try:
                del item.gog_data["md5_xml"]
            except KeyError:
                pass
    save_manifest(all_games)

def main(args):
    """Run the command. Returns the exit status: 0, or 1 if something failed (see the summary at the end of the run)."""
    global MANIFEST_FORMAT
    MANIFEST_FORMAT = getattr(args, 'manifestformat', MANIFEST_FORMAT)
    run_report.reset(args.command)
    stime = datetime.datetime.now()
    if args.command == 'list':
        consoleHandler.setStream(sys.stderr)    # the list itself goes to stdout, so it can be piped or redirected; messages to stderr

    if args.command in ('download', 'verify', 'import', 'backup') and (args.tags or args.skiptags):
        if getattr(args, 'id', None):
            args.ids = [args.id]
        if not apply_tag_options(args):      # nothing to do, or no tag data: stop here, never fall through to 'all games'
            etime = datetime.datetime.now()
            run_report.log()
            info('--')
            info('total time: %s' % (etime - stime))
            return run_report.exit_status()

    if args.command == 'login':
        login_ok = cmd_login(args.username, args.password, browser=args.browser)
        return 0 if login_ok else 1  # no need to see time stats
    elif args.command == 'update':
        apply_os_lang_defaults(args)
        if (not args.skipknown) and (not args.updateonly) and (not args.standard):
            if (args.ids):
                args.full = True
        if args.wait > 0.0:
            info('sleeping for %.2fhr...' % args.wait)
            time.sleep(args.wait * 60 * 60)
        if not args.installers:
            args.installers = "standalone"
        cmd_update(args.os, args.lang, args.skipknown, args.updateonly, not args.full, args.ids, args.skipids,args.skiphidden,args.installers,args.resumemode,args.strictverify,args.strictdupe,args.lenientdownloadsupdate,args.strictextrasupdate,args.md5xmls,args.nochangelogs,args.diagnostic,lang_fallback=args.lang_fallback,tags=args.tags,skiptags=args.skiptags)
    elif args.command == 'download':
        if (args.id):
            args.ids = [args.id]
        apply_os_lang_defaults(args)
        if args.skipgames:
            args.skipstandalone = True
            args.skipgalaxy = True
            args.skipshared = True
        if args.wait > 0.0:
            info('sleeping for %.2fhr...' % args.wait)
            time.sleep(args.wait * 60 * 60)
        if args.downloadlimit is not None:
            args.downloadlimit = args.downloadlimit*1024.0*1024.0 #Convert to Bytes
        cmd_download(args.savedir, args.skipextras, args.skipids, args.dryrun, args.ids,args.os,args.lang,args.skipgalaxy,args.skipstandalone,args.skipshared, args.skipfiles,args.covers,args.backgrounds,args.skippreallocation,not args.nocleanimages,args.downloadlimit,lang_fallback=args.lang_fallback,use_blake3=not args.noblake3)
    elif args.command == 'import':
        args.skipgames = False
        args.skipextras = False
        apply_os_lang_defaults(args)
        if args.skipgames:
            args.skipstandalone = True
            args.skipgalaxy = True
            args.skipshared = True
        cmd_import(args.src_dir, args.dest_dir,args.os,args.lang,args.skipextras,args.skipids,args.ids,args.skipgalaxy,args.skipstandalone,args.skipshared,False,lang_fallback=args.lang_fallback)
    elif args.command == 'verify':
        #Hardcode these as false since extras currently do not have MD5s as such skipgames would give nothing and skipextras would change nothing. The logic path and arguments are present in case this changes, though commented out in the case of arguments)
        if args.clean:
            warn("The -clean option is deprecated, as the default behaviour has been changed to clean files that fail the verification checks. -noclean now exists for leaving files in place. Please update your scripts accordingly. ")
        if (args.id):
            args.ids = [args.id]
        apply_os_lang_defaults(args)
        if args.skipgames:
            args.skipstandalone = True
            args.skipgalaxy = True
            args.skipshared = True
        check_md5 = not args.skipmd5
        check_filesize = not args.skipsize
        check_zips = not args.skipzip
        free_tmp_space = not args.lowtmpspace
        cmd_verify(args.gamedir, args.skipextras,args.skipids,check_md5, check_filesize, check_zips, args.delete,not args.noclean,args.ids,  args.os, args.lang,args.skipgalaxy,args.skipstandalone,args.skipshared, args.skipfiles, args.forceverify,args.permissivechangeclear,args.highmemory,free_tmp_space,lang_fallback=args.lang_fallback,use_blake3=not args.noblake3)
    elif args.command == 'backup':
        apply_os_lang_defaults(args)
        if args.skipgames:
            args.skipstandalone = True
            args.skipgalaxy = True
            args.skipshared = True
        cmd_backup(args.src_dir, args.dest_dir,args.skipextras,args.os,args.lang,args.ids,args.skipids,args.skipgalaxy,args.skipstandalone,args.skipshared,lang_fallback=args.lang_fallback)
    elif args.command == 'clear_partial_downloads':
        cmd_clear_partial_downloads(args.gamedir,args.dryrun)
    elif args.command == 'clean':
        cmd_clean(args.cleandir, args.dryrun)
    elif args.command == 'list':
        cmd_list(args.words, args.os, args.skipos, args.lang, args.skiplang, args.format)
    elif args.command == 'export':
        cmd_export(args.output, args.savedir, args.delimiter)
    elif args.command == 'wishlist':
        cmd_wishlist(args.output, args.csv, args.prices, args.country, args.currency, args.delimiter)
    elif args.command == "trash":
        if (args.installersonly):
            args.installers = True
        cmd_trash(args.gamedir,args.installers,args.images,args.folders,args.relaxed,args.dryrun)
    elif args.command == "diagnostics":
        cmd_output_diagnostic_data(args.verbose)

    etime = datetime.datetime.now()
    run_report.log()
    info('--')
    info('total time: %s' % (etime - stime))
    return run_report.exit_status()

class Wakelock:
    #Mac Sleep support based on caffeine : https://github.com/jpn--/caffeine by Jeffrey Newman

    def __init__(self):

        if (platform.system() == "Windows"):
            self.ES_CONTINUOUS        = 0x80000000
            self.ES_AWAYMODE_REQUIRED = 0x00000040
            self.ES_SYSTEM_REQUIRED   = 0x00000001
            self.ES_DISPLAY_REQUIRED  = 0x00000002
            #Windows is not particularly consistent on what is required for a wakelock for a script that often uses a USB device, so define WAKELOCK for easy changing. This works on Windows 10 as of the October 2017 update.
            self.ES_WAKELOCK = self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED | self.ES_DISPLAY_REQUIRED

        if (platform.system() == "Darwin"):

            self.PM_NODISPLAYSLEEP = 'NoDisplaySleepAssertion'
            self.PM_NOIDLESLEEP = "NoIdleSleepAssertion"
            self.PM_WAKELOCK = self.PM_NOIDLESLEEP
            self._kIOPMAssertionLevelOn = 255

            self.libIOKit = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/IOKit.framework/IOKit')
            self.libIOKit.IOPMAssertionCreateWithName.argtypes = [ ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32) ]
            self.libIOKit.IOPMAssertionRelease.argtypes = [ ctypes.c_uint32 ]
            self._PMassertion = None
            self._PMassertID = ctypes.c_uint32(0)
            self._PMerrcode = None
            self._IOPMAssertionRelease = self.libIOKit.IOPMAssertionRelease


    def _macos_modules_available(self):
        """False (with one warning per run) when PyObjC is missing: the sleep inhibitor is then skipped, the program itself runs."""
        if CoreFoundation is not None and objc is not None:
            return True
        if not getattr(self, '_warned_no_pyobjc', False):
            self._warned_no_pyobjc = True
            warn("PyObjC is not installed, so the computer is not kept awake during the run (python -m pip install pyobjc-framework-Cocoa)")
        return False

    def _CFSTR(self,py_string):
        return CoreFoundation.CFStringCreateWithCString(None, py_string.encode('utf-8'), CoreFoundation.kCFStringEncodingUTF8)

    def raw_ptr(self,pyobjc_string):
        return objc.pyobjc_id(pyobjc_string.nsstring())

    def _IOPMAssertionCreateWithName(self,assert_name, assert_level, assert_msg):
        assertID = ctypes.c_uint32(0)
        p_assert_name = self.raw_ptr(self._CFSTR(assert_name))
        p_assert_msg = self.raw_ptr(self._CFSTR(assert_msg))
        errcode = self.libIOKit.IOPMAssertionCreateWithName(p_assert_name,
            assert_level, p_assert_msg, ctypes.byref(assertID))
        return (errcode, assertID)


    def _get_inhibitor(self):
        #try:
        #    return GnomeSessionInhibitor()
        #except Exception as e:
        #    debug("Could not initialise the gnomesession inhibitor: %s" % e)

        #try:
        #    return DBusSessionInhibitor('org.gnome.PowerManager',"/org/gnome/PowerManager",'org.gnome.PowerManager')
        #except Exception as e:
        #    debug("Could not initialise the gnome power manager inhibitor: %s" % e)


        #try:
        #    return DBusSessionInhibitor('.org.freedesktop.PowerManagement','/org/freedesktop/PowerManagement/Inhibit','org.freedesktop.PowerManagement.Inhibit')
        #except Exception as e:
        #    debug("Could not initialise the freedesktop power management inhibitor: %s" % e)


        try:
            return DBusSystemInhibitor('org.freedesktop.login1','/org/freedesktop/login1','org.freedesktop.login1.Manager')
        except Exception as e:
            warn("Could not initialise the systemd session inhibitor: %s" % e)


        return None


    def take_wakelock(self):
        if platform.system() == "Windows":
            ctypes.windll.kernel32.SetThreadExecutionState(self.ES_WAKELOCK)
        if platform.system() == "Darwin":
            if not self._macos_modules_available():
                return
            a = self.PM_WAKELOCK
            if self._PMassertion is not None and a != self._PMassertion:
                self.release_wakelock()
            if self._PMassertID.value ==0:
                self._PMerrcode, self._PMassertID = self._IOPMAssertionCreateWithName(a,self._kIOPMAssertionLevelOn,"gogrepoc")
                self._PMassertion = a
        if (not (platform.system() == "Windows" or platform.system() == "Darwin")) and  ('PyQt5.QtDBus' in sys.modules):
            self.inhibitor = self._get_inhibitor()
            if (self.inhibitor != None):
                self.inhibitor.inhibit()

    def release_wakelock(self):
        if platform.system() == "Windows":
            ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)
        if platform.system() == "Darwin":
            if not self._macos_modules_available():
                return
            self._PMerrcode = self._IOPMAssertionRelease(self._PMassertID)
            self._PMassertID.value = 0
            self._PMassertion = None

class DBusSystemInhibitor:

    def __init__(self,name,path,interface,method=["Inhibit"]):
        self.name = name
        self.path = path
        self.interface_name = interface
        self.method = method
        self.cookie = None
        self.APPNAME = "GOGRepo Gamma"
        self.REASON = "Using Internet and USB Connection"
        bus = PyQt5.QtDBus.QDBusConnection.systemBus()
        introspection = PyQt5.QtDBus.QDBusInterface(self.name,self.path,"org.freedesktop.DBus.Introspectable",bus)
        serviceIntrospection = xml.etree.ElementTree.fromstring(PyQt5.QtDBus.QDBusReply(introspection.call("Introspect")).value())
        methodExists = False;
        for interface in serviceIntrospection.iter("interface"):
            if interface.get('name') == self.interface_name:
                for method in interface.iter("method"):
                    if method.get('name') == self.method[0]:
                        methodExists = True
        if not methodExists:
            raise AttributeError(self.interface_name + "has no method " + self.method[0])
        self.iface = PyQt5.QtDBus.QDBusInterface(self.name,self.path,self.interface_name,bus)

    def inhibit(self):
        if self.cookie is None:
            reply = PyQt5.QtDBus.QDBusReply(self.iface.call(self.method[0],"idle",self.APPNAME, self.REASON,"block"))
            if reply.isValid():
                self.cookie = reply.value()

    def uninhibit(self):
        if (self.cookie is not None):
            pass #It's not possible to release this file handle in QtDBus (since the QDUnixFileDescriptor is a copy). The file handle is automatically released when the program exits.




class DBusSessionInhibitor:
    def __init__(self,name, path, interface, methods=["Inhibit", "UnInhibit"] ):
        self.name = name
        self.path = path
        self.interface_name = interface
        self.methods = methods
        self.cookie = None
        self.APPNAME = "GOGRepo Gamma"
        self.REASON = "Using Internet and USB Connection"

        bus = PyQt5.QtDBus.QDBusConnection.sessionBus()
        self.iface = PyQt5.QtDBus.QDBusInterface(self.name,self.path,self.interface_name,bus)


    def inhibit(self):
        if self.cookie is None:
            self.cookie = PyQt5.QtDbus.QDBusReply(self.iface.call(self.methods[0],self.APPNAME, self.REASON)).value()

    def uninhibit(self):
        if self.cookie is not None:
            self.iface.call(self.methods[1],self.cookie)
            self.cookie = None

class GnomeSessionInhibitor(DBusSessionInhibitor):
    TOPLEVEL_XID = 0
    INHIBIT_SUSPEND = 4

    def __init__(self):
        DBusSessionInhibitor.__init__(self, 'org.gnome.SessionManager',
                                '/org/gnome/SessionManager',
                                "org.gnome.SessionManager",
                                ["Inhibit", "Uninhibit"])

    def inhibit(self):
        if self.cookie is None:
            self.cookie = PyQt5.QtDbus.QDBusReply(self.iface.call(self.methods[0],self.APPNAME,GnomeSessionInhibitor.TOPLEVEL_XID, self.REASON),GnomeSessionInhibitor.INHIBIT_SUSPEND).value()



if __name__ == "__main__":
    exit_status = 0
    try:
        wakelock = Wakelock()
        wakelock.take_wakelock()
        ensure_config_file()
        exit_status = main(process_argv(sys.argv))
        info('exiting...')
    except KeyboardInterrupt:
        run_report.log(interrupted=True)
        info('exiting...')
        sys.exit(1)
    except SystemExit:
        raise
    except TokenPasswordError as e:
        error('%s' % e)         # no traceback: it is not a program error
        error("If you have forgotten the password, delete %s and run the login command again." % TOKEN_FILENAME)
        sys.exit(1)
    except Exception:
        log_exception('fatal...')
        sys.exit(1)
    finally:
        wakelock.release_wakelock()
    if exit_status:
        sys.exit(exit_status)     # 1: the run finished but something failed (listed in the summary)

