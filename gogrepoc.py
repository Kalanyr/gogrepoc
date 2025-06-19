# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import division
from __future__ import unicode_literals
# The following code block between #START# and #END#
# generates an error message if this script is called as a shell script.
# Using a "shebang" instead would fail on Windows.
#START#
if False:
    print("Please start this script with a python interpreter: python /path/to/gogrepoc.py")
#END#
__appname__ = 'gogrepoc.py'
__author__ = 'eddie3,kalaynr'
__version__ = '0.4.0-a'
__url__ = 'https://github.com/kalanyr/gogrepoc'


# imports
from pathlib import Path
import subprocess
import unicodedata
import os
import sys
import threading
import logging
import html5lib
import pprint
import time
import zipfile
import hashlib
import getpass
import argparse
import codecs
import io
import datetime
import shutil
import xml.etree.ElementTree
import copy
import logging.handlers
import ctypes
import requests 
import re
#import OpenSSL
import platform
import locale
import zlib
from fnmatch import fnmatch
import email.utils
import signal
import PySimpleGUI as sg

import psutil
minPy2 = [2,7]
minPy3 = [3,8]

if sys.version_info[0] < 3:
    if sys.version_info[0] < minPy2[0] or sys.version_info[1] < minPy2[1]:
        print("Your Python version is not supported, please update to 2.7+" )
        sys.exit(1)
elif sys.version_info[0] < 4:
    if sys.version_info[0] < minPy3[0] or sys.version_info[1] < minPy3[1]:
        print("Your Python version is not supported, please update to 3.8+")
        sys.exit(1)

if sys.version_info[0] < 3:
    import dateutil #pip package name is python-dateutil
    import dateutil.parser
    import pytz
    import string
# python 2 / 3 imports
try:
    # python 2
    from Queue import Queue
    from urlparse import urlparse,unquote,urlunparse,parse_qs
    from itertools import izip_longest as zip_longest
    from StringIO import StringIO
except ImportError:
    # python 3
    from queue import Queue
    from urllib.parse import urlparse, unquote, urlunparse,parse_qs
    from itertools import zip_longest
    from io import StringIO
    
if (platform.system() == "Windows"):
    import ctypes.wintypes
    
if (platform.system() == "Darwin"):
    import CoreFoundation #import CFStringCreateWithCString, CFRelease, kCFStringEncodingASCII
    import objc #import pyobjc_id

if not ((platform.system() == "Darwin") or (platform.system() == "Windows")):
    try:
        import PyQt5.QtDBus
    except ImportError:
        pass
    


# python 2 / 3 renames
try: input = raw_input
except NameError: pass

# optional imports
try:
    from html2text import html2text
except ImportError:
    def html2text(x): return x

    
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
CREATE_NEW = 0x1    
OPEN_EXISTING = 0x3
FILE_BEGIN = 0x0


# lib mods
# configure logging
LOG_MAX_MB = 180
LOG_BACKUPS = 9 
logFormatter = logging.Formatter("%(asctime)s | %(message)s", datefmt='%H:%M:%S')
rootLogger = logging.getLogger('ws')
rootLogger.setLevel(logging.DEBUG)
consoleHandler = logging.StreamHandler(sys.stdout)
loggingHandler = logging.handlers.RotatingFileHandler('gogrepo.log', mode='a+', maxBytes = 1024*1024*LOG_MAX_MB , backupCount = LOG_BACKUPS,  encoding=None, delay=True)
loggingHandler.setFormatter(logFormatter)
consoleHandler.setFormatter(logFormatter)
rootLogger.addHandler(consoleHandler)

# logging aliases
info = rootLogger.info
warn = rootLogger.warning
debug = rootLogger.debug
error = rootLogger.error
log_exception = rootLogger.exception

# filepath constants
GAME_STORAGE_DIR = r'.'
TOKEN_FILENAME = r'gog-token.dat'
MANIFEST_FILENAME = r'gog-manifest.dat'
RESUME_MANIFEST_FILENAME = r'gog-resume-manifest.dat'
TEMP_EXT = r'.tmp'
BACKUP_EXT = r'.bak'
CONFIG_FILENAME = r'gog-config.dat'
SERIAL_FILENAME = r'!serial.txt'
INFO_FILENAME = r'!info.txt'


#github API URLs
REPO_HOME_URL = "https://api.github.com/repos/kalanyr/gogrepoc" 
NEW_RELEASE_URL = "/releases/latest"

# GOG URLs
GOG_HOME_URL = r'https://www.gog.com'
GOG_ACCOUNT_URL = r'https://www.gog.com/account'
GOG_LOGIN_URL = r'https://login.gog.com/login_check'

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
HTTP_RETRY_DELAY = 5   # in seconds #If you reduce this such that the wait between the first and third try is less than 10 seconds, you're gonna have a bad time with the 503 error. 
HTTP_RETRY_COUNT = 4
HTTP_TIMEOUT = 60

HTTP_GAME_DOWNLOADER_THREADS = 4
HTTP_PERM_ERRORCODES = (404, 403) #503 was in here GOG uses it as a request to wait for a bit when it's under stress. The time out appears to be ~10 seconds in such cases.  
USER_AGENT = 'GOGRepoC/' + str(__version__)

# Language table that maps two letter language to their unicode gogapi json name
LANG_TABLE = {'en': u'English',   # English
              'bl': u'\u0431\u044a\u043b\u0433\u0430\u0440\u0441\u043a\u0438',  # Bulgarian
              'ru': u'\u0440\u0443\u0441\u0441\u043a\u0438\u0439',              # Russian
              'gk': u'\u0395\u03bb\u03bb\u03b7\u03bd\u03b9\u03ba\u03ac',        # Greek
              'sb': u'\u0421\u0440\u043f\u0441\u043a\u0430',                    # Serbian
              'ar': u'\u0627\u0644\u0639\u0631\u0628\u064a\u0629',              # Arabic
              'br': u'Portugu\xeas do Brasil',  # Brazilian Portuguese
              'jp': u'\u65e5\u672c\u8a9e',      # Japanese
              'ko': u'\ud55c\uad6d\uc5b4',      # Korean
              'fr': u'fran\xe7ais',             # French
              'cn': u'\u4e2d\u6587',            # Chinese
              'cz': u'\u010desk\xfd',           # Czech
              'hu': u'magyar',                  # Hungarian
              'pt': u'portugu\xeas',            # Portuguese
              'tr': u'T\xfcrk\xe7e',            # Turkish
              'sk': u'slovensk\xfd',            # Slovak
              'nl': u'nederlands',              # Dutch
              'ro': u'rom\xe2n\u0103',          # Romanian
              'es': u'espa\xf1ol',      # Spanish
              'pl': u'polski',          # Polish
              'it': u'italiano',        # Italian
              'de': u'Deutsch',         # German
              'da': u'Dansk',           # Danish
              'sv': u'svenska',         # Swedish
              'fi': u'Suomi',           # Finnish
              'no': u'norsk',           # Norsk
              }

VALID_OS_TYPES = ['windows', 'linux', 'mac']
VALID_LANG_TYPES = list(LANG_TABLE.keys())

universalLineEnd = ''
storeExtend = 'extend'
uLongPathPrefix= u"\\\\?\\"

if sys.version_info[0] < 3:
    storeExtend = 'store'
    universalLineEnd = 'U'


DEFAULT_FALLBACK_LANG = 'en'

# Save manifest data for these os and lang combinations
sysOS = platform.system() 
sysOS = sysOS.lower()    
if sysOS == 'darwin':
    sysOS = 'mac'
if sysOS == "java":
    print("Jython is not currently supported. Let me know if you want Jython support.")
    sys.exit(1)
if not (sysOS in VALID_OS_TYPES):
    sysOS = 'linux'
DEFAULT_OS_LIST = [sysOS]
sysLang,_ = locale.getlocale()
if (sysLang is not None):
    sysLang = sysLang[:2]
    sysLang = sysLang.lower()
if not (sysLang in VALID_LANG_TYPES):
    sysLang = 'en'
DEFAULT_LANG_LIST = [sysLang]

#if DEFAULT_FALLBACK_LANG not in DEFAULT_LANG_LIST:
#    DEFAULT_LANG_LIST.push(DEFAULT_FALLBACK_LANG)

# These file types don't have md5 data from GOG
SKIP_MD5_FILE_EXT = ['.txt', '.zip',''] #Removed tar.gz as it can have md5s and is actually parsed as .gz so wasn't working
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
RESUME_SAVE_THRESHOLD = 50

MANIFEST_SYNTAX_VERSION = 1
RESUME_MANIFEST_SYNTAX_VERSION = 1 

token_lock = threading.RLock()

WINDOWS_PREALLOCATION_FS = ["NTFS","exFAT","FAT32"]
POSIX_PREALLOCATION_FS = ["exfat","vfat","ntfs","btrfs", "ext4", "ocfs2", "xfs"] #May need to exempt NTFS because of reported hangs on remote drives, but should check if that's because of NFS or similar first
#request wrapper 
def request(session,url,args=None,byte_range=None,retries=HTTP_RETRY_COUNT,delay=None,stream=False,data=None):
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
            if e.response.status_code in HTTP_PERM_ERRORCODES:  # do not retry these HTTP codes
                warn('request failed: %s.  will not retry.', e)
                raise
        if retries > 0:
            _retry = True
        else:
            raise

        if _retry:
            warn('request failed: %s (%d retries left) -- will retry in %ds...' % (e, retries, HTTP_RETRY_DELAY))
            return request(session=session,url=url, args=args, byte_range=byte_range, retries=retries-1, delay=HTTP_RETRY_DELAY,stream=stream,data=data)
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
                    token_response = session.get(GOG_TOKEN_URL,params={'client_id':GOG_CLIENT_ID ,'client_secret':GOG_SECRET, 'grant_type': 'refresh_token','refresh_token': session.token['refresh_token']})   
                    token_response.raise_for_status()    
                except Exception as e:
                        if retries > 0:
                            _retry = True
                        else:
                            error(e)
                            error('Could not renew token, Please login again.')
                            sys.exit(1)
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
        tmp = self._buffer
        if tmp:
            pos = tmp.tell()
            tmp.seek(0)

            file_changed = not os.path.exists(self._filename)
            if not file_changed:
                with codecs.open(self._filename, 'r', 'utf-8') as orig:
                    for (new_chunk, old_chunk) in zip_longest(tmp, orig):
                        if new_chunk != old_chunk:
                            file_changed = True
                            break

            if file_changed:
                with codecs.open(self._filename, 'w', 'utf-8') as overwrite:
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
    if (sys.version_info[0] >= 3): #Modification
        value = str(value)
    else:  #Modification
        value=unicode(value)  #Modification
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
    path_without_extensions = os.path.join(os.path.dirname(path),os.path.basename(path).rsplit(os.extsep,1)[0]) #Need to improve this to handle eg tar.gz
    extension = os.extsep + os.path.basename(path).rsplit(os.extsep,1)[1]
    return [path_without_extensions,extension]

def move_with_increment_on_clash(src,dst,count=0):
    if (count == 0):
        potDst = dst
    else:
        if os.path.isdir(dst):
            potDst =  dst + "(" +str(count) + ")" 
        else:
            root,ext = path_preserving_split_ext(dst)
            if (ext != ".bin"):
                potDst = root + "("+str(count) + ")" + ext
            else:
                #bin file, adjust name to account for gogs weird extension method
                setDelimiter = root.rfind("-")
                try:
                    setPart = int(root[setDelimiter+1:])
                except ValueError:
                    #This indicators a false positive. The "-" found was part of the file name not a set delimiter. 
                    setDelimiter = -1 
                if (setDelimiter == -1):
                    #not part of a bin file set , some other binary file , treat it like a non .bin file
                    potDst = root + "("+str(count) + ")" + ext
                else:    
                    potDst = root[:setDelimiter] + "("+str(count) + ")" + root[setDelimiter:] + ext
        warn('Unresolved destination clash for "{}" detected. Trying "{}"'.format(dst,potDst))
    if (not os.path.exists(potDst)) or (os.path.isdir(potDst)):
        shutil.move(src,potDst)
    else:
        move_with_increment_on_clash(src,dst,count+1)
    
def load_manifest(filepath=MANIFEST_FILENAME):
    info('loading local manifest...')
    try:
        with codecs.open(filepath, 'r' + universalLineEnd, 'utf-8') as r:
#            ad = r.read().replace('{', 'AttrDict(**{').replace('}', '})')
            ad = r.read()
            compiledregexopen =  re.compile(r"'changelog':.*?'downloads':|({)",re.DOTALL)
            compiledregexclose = re.compile(r"'changelog':.*?'downloads':|(})",re.DOTALL)
            compiledregexmungeopen = re.compile(r"[AttrDict(**]+{")
            compiledregexmungeclose = re.compile(r"}\)+")
            
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
            
            mungeDetected = compiledregexmungeopen.search(ad) 
            if mungeDetected:
                warn("detected AttrDict error in manifest")
                ad = compiledregexmungeopen.sub("{",ad)
                ad = compiledregexmungeclose.sub("}",ad)
                warn("fixed AttrDict in manifest")                

            ad =  compiledregexopen.sub(myreplacementopen,ad)
            ad =  compiledregexclose.sub(myreplacementclose,ad)

            if (sys.version_info[0] >= 3):
                ad = re.sub(r"'size': ([0-9]+)L,",r"'size': \1,",ad)
            db = eval(ad)
            if (mungeDetected):
                save_manifest(db)
        return eval(ad)
    except IOError:
        return []

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
                        for cur_dir_file in os.listdir(cur_fulldir):
                            if os.path.isdir(os.path.join(MD5_DIR_NAME, cur_dir, cur_dir_file)):
                                if cur_dir_file not in expected_dirnames:
                                    info("Removing incorrect subdirectory " + os.path.join(MD5_DIR_NAME, cur_dir, cur_dir_file))
                                    shutil.rmtree(os.path.join(MD5_DIR_NAME, cur_dir, cur_dir_file)) 
                                else:
                                    cur_fulldir2 = os.path.join(MD5_DIR_NAME, cur_dir,cur_dir_file)
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
                                                                if ( game_item.name is not None ):
                                                                    expected_filenames.append(game_item.name + ".xml")                                                                
                                                            for cur_dir_file in os.listdir(cur_fulldir4):
                                                                
                                                                for cur_dir_file in os.listdir(cur_fulldir4):
                                                                    if os.path.isdir(os.path.join(cur_fulldir4, cur_dir_file)):
                                                                        info("Removing subdirectory(?!) " + os.path.join(downloadingdir, cur_dir, cur_dir_file))                    
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
            #all_md5s = glob.glob()   Can't recursive glob before 3.5 so have to do this the hardway     
                    
    save_manifest_core(items,filepath)

def save_manifest_core_worker(items,filepath,hasManifestPropsItem=False):
    tmp_path = filepath+TEMP_EXT
    bak_path = filepath+BACKUP_EXT
    if os.path.exists(filepath):
        shutil.copy(filepath,tmp_path)
    len_adjustment = 0
    if (hasManifestPropsItem):
        len_adjustment = -1
    with codecs.open(tmp_path, 'w', 'utf-8') as w:
        print('# {} games'.format(len(items)+len_adjustment), file=w)
        pprint.pprint(items, width=123, stream=w)
    if os.path.exists(bak_path):
        os.remove(bak_path)
    if os.path.exists(filepath):
        shutil.move(filepath,bak_path)
    shutil.move(tmp_path,filepath)    


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
        with codecs.open(filepath, 'r' + universalLineEnd, 'utf-8') as r:
            ad = r.read().replace('{', 'AttrDict(**{').replace('}', '})')
            if (sys.version_info[0] >= 3):
                ad = re.sub(r"'size': ([0-9]+)L,",r"'size': \1,",ad)
        return eval(ad)
    except IOError:
        return []
        
def save_config_file(items):
    info('saving config...')
    try:
        with codecs.open(CONFIG_FILENAME, 'w', 'utf-8') as w:
            print('# {} games'.format(len(items)-1), file=w)
            pprint.pprint(items, width=123, stream=w)
        info('saved config')                        
    except KeyboardInterrupt:
        with codecs.open(CONFIG_FILENAME, 'w', 'utf-8') as w:
            print('# {} games'.format(len(items)-1), file=w)
            pprint.pprint(items, width=123, stream=w)
        info('saved resume manifest')            
        raise

def load_config_file(filepath=CONFIG_FILENAME):
    info('loading config...')
    try:
        with codecs.open(filepath, 'r' + universalLineEnd, 'utf-8') as r:
            ad = r.read().replace('{', 'AttrDict(**{').replace('}', '})')
            #if (sys.version_info[0] >= 3):
            #    ad = re.sub(r"'size': ([0-9]+)L,",r"'size': \1,",ad)
        return eval(ad)
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
    afile = open(afile, 'rb')
    hasher = hashlib.md5()
    buf = afile.read(blocksize)
    while len(buf) > 0:
        hasher.update(buf)
        buf = afile.read(blocksize)
    return hasher.hexdigest()


def test_zipfile(filename):
    """Opens filename and tests the file for ZIP integrity.  Returns True if
    zipfile passes the integrity test, False otherwise.
    """
    try:
        with zipfile.ZipFile(filename, 'r') as f:
            if f.testzip() is None:
                return True
    except (zipfile.BadZipfile,zlib.error):
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

    if olditem.changelog != newitem.changelog and newitem.changelog not in [None, '']:
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
            if sys.version_info[0] < 3: #requires external module
                if newDownload.old_updated is not None:
                    oldUpdateTime = dateutil.parser.isoparse(newDownload.old_updated) #requires external module
                if newDownload.updated is not None:
                    updateTime = dateutil.parser.isoparse(newDownload.updated) 
            else: #Standardize #Only valid after 3.7 (this will always be in a datetime isoformat so the changes between 3.7 and 3.11 aren't relevant here)
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
                if oldExtra.md5 == oldExtra.md5 and oldExtra.size == newExtra.size:
                    if oldExtra.name == newExtra.name:
                        candidate = oldExtra #Match already exists
                        break #Can't be overriden so end it now
                    if oldExtra.name != newExtra.name and (candidate == None or candidate.md5 == None):
                        candidate = oldExtra
            else:    
                if oldExtra.name == newExtra.name and oldExtra.size == newExtra.size and candidate == None:
                    candidate = AttrDict(**oldExtra.copy())
                    if strict:
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
            if sys.version_info[0] < 3: #requires external module
                if newExtra.old_updated is not None:
                    oldUpdateTime = dateutil.parser.isoparse(newExtra.old_updated) #requires external module
                if newExtra.updated is not None:
                    updateTime = dateutil.parser.isoparse(newExtra.updated) 
            else: #Standardize #Only valid after 3.7 (this will always be in a datetime isoformat so the changes between 3.7 and 3.11 aren't relevant here)
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


def fetch_chunk_tree(response, session):
    file_ext = os.path.splitext(urlparse(response.url).path)[1].lower()
    if file_ext not in SKIP_MD5_FILE_EXT:
        try:
            chunk_url = append_xml_extension_to_url_path(response.url)
            chunk_response = request(session,chunk_url)
            shelf_etree = xml.etree.ElementTree.fromstring(chunk_response.content)
            return  shelf_etree
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                warn("no md5 data found for {}".format(chunk_url))
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

def fetch_file_info(d, fetch_md5,save_md5_xml,updateSession):
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
        if file_ext not in SKIP_MD5_FILE_EXT:
            try:
                tmp_md5_url = append_xml_extension_to_url_path(response.url)
                md5_response = request(updateSession,tmp_md5_url)
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
                if sys.version_info[0] < 3 :
                    d.updated = dateutil.parser.isoparse(d.raw_updated).replace(tzinfo=pytz.utc).isoformat() #requires external modules
                else:
                    d.updated = datetime.datetime.fromisoformat(d.raw_updated).replace(tzinfo=datetime.timezone.utc).isoformat() #Standardize #Only valid after 3.7 or maybe 3.11 ? #Assumes that timezone is UTC (might actually be GMT +2 (Poland) but even if so UTC is a far more consistent approximation than local time for most of the world)
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    warn("no md5 data found for {}".format(d.name))
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
        if (sys.version_info[0] < 3):
            d.updated = datetime.datetime.fromtimestamp( email.utils.mktime_tz(email.utils.parsedate_tz( d.raw_updated )), pytz.utc ).isoformat() #Standardize
        else:
            d.updated = email.utils.parsedate_to_datetime(d.raw_updated).isoformat() #Standardize

def filter_downloads(out_list, downloads_list, lang_list, os_list,save_md5_xml,updateSession):
    """filters any downloads information against matching lang and os, translates
    them, and extends them into out_list
    """
    filtered_downloads = []
    downloads_dict = dict(downloads_list)

    # hold list of valid languages languages as known by gogapi json stuff
    valid_langs = []
    for lang in lang_list:
        valid_langs.append(LANG_TABLE[lang])

    # check if lang/os combo passes the specified filter
    for lang in downloads_dict:
        if lang in valid_langs:
            for os_type in downloads_dict[lang]:
                if os_type in os_list:
                    for download in downloads_dict[lang][os_type]:
                        tempd = download['manualUrl']
                        if tempd[:10] == "/downloads":
                            tempd = "/downlink" +tempd[10:]
                        hrefs = [GOG_HOME_URL + download['manualUrl'],GOG_HOME_URL + tempd]
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
                                        #with codecs.open('head_test_headers.txt', 'w', 'utf-8') as w:
                                        #    w.write(str(head_response.headers))
                                        #shelf_head.etree = xml.etree.ElementTree.fromstring(head_response.content)
                                        fetch_file_info(d, True,save_md5_xml,updateSession)
                                        file_info_success = True
                                    except requests.HTTPError:
                                        warn("failed to fetch %s" % (d.href))
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
                                        warn("Successfully fetched file info from %s but no md5 data was available" % href_d[0].href)
                            if not any_file_info_success:
                                #None worked so go with the canonical link
                                error("Could not fetch file info so using canonical link: %s" % href_ds[0][0].href)
                                filtered_downloads.append(href_ds[0][0])
    out_list.extend(filtered_downloads)


def filter_extras(out_list, extras_list,save_md5_xml,updateSession):
    """filters and translates extras information and adds them into out_list
    """
    filtered_extras = []

    for extra in extras_list:
        tempd = extra['manualUrl']
        if tempd[:10] == "/downloads":
            tempd = "/downlink" +tempd[10:]
        hrefs = [GOG_HOME_URL + extra['manualUrl'],GOG_HOME_URL + tempd]
        href_ds = []
        file_info_success = False
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
                             name=None,
                             size=None,
                             prev_verified=False,
                             old_name = None,
                             unreleased = False,
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
                        #with codecs.open('head_test_headers.txt', 'w', 'utf-8') as w:
                        #    w.write(str(head_response.headers))
                        fetch_file_info(d, False,save_md5_xml,updateSession)
                        file_info_success = True
                    except requests.HTTPError:
                        warn("failed to fetch %s" % d.href)
                    except Exception:
                        warn("failed to fetch %s because of non-HTTP Error" % d.href)
                        warn("The handled exception was:")
                        log_exception('')
                        warn("End exception report.")
                href_ds.append([d,file_info_success])
        if unreleased:
            debug("File Not Available For Manual Download Storing Canonical Link: %s" % d.href)
            filtered_extras.append(d)
        elif file_info_success: #Will be the current d because no more are created once we're successful
            debug("Successfully fetched file info from %s" % d.href)
            filtered_extras.append(d)
        else:
            #None worked so go with the canonical link
            error("Could not fetch file info so using canonical link: %s" % href_ds[0][0].href)
            filtered_extras.append(href_ds[0][0])
    out_list.extend(filtered_extras)


def filter_dlcs(item, dlc_list, lang_list, os_list,save_md5_xml,updateSession):
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
            if sys.version_info[0] >= 3:
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
            else:
                if not (all(c in string.printable for c in  item.serial)):
                    pserial = item.serials[potential_title]
                    if (len(pserial) % 2): #0dd
                        pserial=pserial+"\x00" 
                    pserial = bytearray(pserial,"UTF-8")
                    pserial = pserial.decode("UTF-16")
                    if all(c in string.printable for c in  item.serial):
                        pserial = pserial.encode("UTF-8")
                        item.serials[potential_title] = pserial
                    else:
                        warn('DLC serial code is unprintable for %s, storing raw',potential_title)
        filter_downloads(item.downloads, dlc_dict['downloads'], lang_list, os_list,save_md5_xml,updateSession)
        filter_downloads(item.galaxyDownloads, dlc_dict['galaxyDownloads'], lang_list, os_list,save_md5_xml,updateSession)
        filter_extras(item.extras, dlc_dict['extras'],save_md5_xml,updateSession)
        filter_dlcs(item, dlc_dict['dlcs'], lang_list, os_list,save_md5_xml,updateSession)  # recursive
        
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

def makeDeDuplicateName(name,prevItemsCount):
    root,ext = name.rsplit(os.extsep,1) #expand this to cover eg tar.zip
    ext = os.extsep + ext
    if (ext != ".bin"):
        name = root + "("+str(prevItemsCount) + ")" + ext
    else:
        #bin file, adjust name to account for gogs weird extension method
        setDelimiter = root.rfind("-")
        try:
            setPart = int(root[setDelimiter+1:])
        except ValueError:
            #This indicators a false positive. The "-" found was part of the file name not a set delimiter. 
            setDelimiter = -1 
        if (setDelimiter == -1):
            #not part of a bin file set , some other binary file , treat it like a non .bin file
           name = root + "("+str(prevItemsCount) + ")" + ext
        else:    
            name = root[:setDelimiter] + "("+str(prevItemsCount) + ")" + root[setDelimiter:] + ext
    return name


def check_skip_file(fname, skipfiles):
    # return pattern that matched, or None
    for skipf in skipfiles:
        if fnmatch(fname, skipf):
            return skipf
    return None

def process_path(path):
    fpath = path
    if sys.version_info[0] < 3:
        if isinstance(fpath, str):
            fpath = fpath.decode('utf-8')
    fpath = os.path.abspath(fpath)
    raw_fpath = u'\\\\?\\%s' % fpath 
    return raw_fpath   

def is_numeric_id(s):
    try:
        int(s)
        return True
    except ValueError:
        return False    

def append_xml_extension_to_url_path(url):
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path = parsed.path + ".xml")).replace('%28','(').replace('%29',')') #Thanks to pasbeg

def process_argv(argv):
    p1 = argparse.ArgumentParser(description='%s (%s)' % (__appname__, __url__), add_help=False)
    sp1 = p1.add_subparsers(help='command', dest='command', title='commands')
    sp1.required = True

    g1 = sp1.add_parser('login', help='Login to GOG ( using a GOG or Galaxy Account only ) and save a local copy of your authenticated token')
    g1.add_argument('username', action='store', help='GOG username/email', nargs='?', default=None)
    g1.add_argument('password', action='store', help='GOG password', nargs='?', default=None)
    g1.add_argument('-nolog', action='store_true', help = 'doesn\'t writes log file gogrepo.log')
    g1.add_argument('-debug', action='store_true', help = "Includes debug messages")
    

    g1 = sp1.add_parser('update', help='Update locally saved game manifest from GOG server')
    g1.add_argument('-resumemode',action="store",choices=['noresume','resume','onlyresume'],default='resume',help="how to handle resuming if necessary")
    g1.add_argument('-strictverify',action="store_true",help="clear previously verified unless md5 match")
    g1.add_argument('-strictdupe',action="store_true",help="missing MD5s do not default to checking only file size (missing MD5s only match other missing MD5s rather than any value)")
    g1.add_argument('-lenientdownloadsupdate',action="store_false",help="Does not mark installers for updating, even if size and name match,  if the last updated time has changed and MD5s are not available or do not match")
    g1.add_argument('-strictextrasupdate',action="store_true",help="Marks extras for updating, even if size and name match,  if the last updated time has changed and MD5s are not available or do not match  ")
    g1.add_argument('-md5xmls',action="store_true",help="Downloads the MD5 XML files for each item (where available) and outputs them to " + MD5_DIR_NAME)
    g1.add_argument('-nochangelogs',action="store_true",help="Skips saving the changelogs for games")
    g2 = g1.add_mutually_exclusive_group()
    g2.add_argument('-os', action=storeExtend, help='operating system(s)', nargs='*', default=[])
    g2.add_argument('-skipos', action='store', help='skip operating system(s)', nargs='*', default=[])  
    g3 = g1.add_mutually_exclusive_group()
    g3.add_argument('-lang', action=storeExtend, help='game language(s)', nargs='*', default=[])
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
    g1.add_argument('-wait', action='store', type=float,
                    help='wait this long in hours before starting', default=0.0)  # sleep in hr
    g1.add_argument('-nolog', action='store_true', help = 'doesn\'t writes log file gogrepo.log')
    g1.add_argument('-debug', action='store_true', help = "Includes debug messages")
                    

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
    g4.add_argument('-os', action=storeExtend, help='download game files only for operating system(s)', nargs='*', default=[]) 
    g5 = g1.add_mutually_exclusive_group()  # below are mutually exclusive    
    g5.add_argument('-lang', action=storeExtend, help='download game files only for language(s)', nargs='*', default=[])    
    g5.add_argument('-skiplang', action=storeExtend, help='skip downloading game files for language(s)', nargs='*', default=[])  
    g1.add_argument('-skippreallocation',action='store_true',help='do not preallocate space for files')
    g1.add_argument('-nolog', action='store_true', help = 'doesn\'t writes log file gogrepo.log')
    g1.add_argument('-debug', action='store_true', help = "Includes debug messages")

                    
                    
    g1 = sp1.add_parser('import', help='Import files with any matching MD5 checksums found in manifest')
    g1.add_argument('src_dir', action='store', help='source directory to import games from')
    g1.add_argument('dest_dir', action='store', help='directory to copy and name imported files to')
    g2 = g1.add_mutually_exclusive_group()  # below are mutually exclusive        
    g2.add_argument('-skipos', action='store', help='skip importing game files for operating system(s)', nargs='*', default=[])  
    g2.add_argument('-os', action='store', help='import game files only for operating system(s)', nargs='*', default=[])  
    g3 = g1.add_mutually_exclusive_group()  # below are mutually exclusive    
    g3.add_argument('-skiplang', action='store', help='skip importing game files for language(s)', nargs='*', default=[])        
    g3.add_argument('-lang', action='store', help='import game files only for language(s)', nargs='*', default=[])       
    #Code path available but commented out and hardcoded as false due to lack of MD5s on extras. 
    #g4 = g1.add_mutually_exclusive_group()
    #g4.add_argument('-skipextras', action='store_true', help='skip downloading of any GOG extra files')
    #g4.add_argument('-skipgames', action='store_true', help='skip downloading of any GOG game files (deprecated, use -skipgalaxy -skipstandalone -skipshared instead)')
    g1.add_argument('-nolog', action='store_true', help = 'doesn\'t writes log file gogrepo.log')
    g1.add_argument('-debug', action='store_true', help = "Includes debug messages")
    g1.add_argument('-skipgalaxy', action='store_true', help='skip downloading Galaxy installers')
    g1.add_argument('-skipstandalone', action='store_true', help='skip downloading standlone installers')
    g1.add_argument('-skipshared', action = 'store_true', help ='skip downloading installers shared between Galaxy and standalone')
    g5 = g1.add_mutually_exclusive_group()  # below are mutually exclusive    
    g5.add_argument('-ids', action='store', help='id(s) or title(s) of the game in the manifest to import', nargs='*', default=[])
    g5.add_argument('-skipids', action='store', help='id(s) or title(s) of the game(s) in the manifest to NOT import', nargs='*', default=[])
    

    g1 = sp1.add_parser('backup', help='Perform an incremental backup to specified directory')
    g1.add_argument('src_dir', action='store', help='source directory containing gog items')
    g1.add_argument('dest_dir', action='store', help='destination directory to backup files to')
    g5 = g1.add_mutually_exclusive_group()  # below are mutually exclusive    
    g5.add_argument('-ids', action='store', help='id(s) or title(s) of the game in the manifest to backup', nargs='*', default=[])
    g5.add_argument('-skipids', action='store', help='id(s) or title(s) of the game(s) in the manifest to NOT backup', nargs='*', default=[])    
    g2 = g1.add_mutually_exclusive_group()  # below are mutually exclusive        
    g2.add_argument('-skipos', action='store', help='skip backup of game files for operating system(s)', nargs='*', default=[])  
    g2.add_argument('-os', action='store', help='backup game files only for operating system(s)', nargs='*', default=[])  
    g3 = g1.add_mutually_exclusive_group()  # below are mutually exclusive    
    g3.add_argument('-skiplang', action='store', help='skip backup of game files for language(s)', nargs='*', default=[])        
    g3.add_argument('-lang', action='store', help='backup game files only for language(s)', nargs='*', default=[] )        
    g4 = g1.add_mutually_exclusive_group()
    g4.add_argument('-skipextras', action='store_true', help='skip backup of any GOG extra files')
    g4.add_argument('-skipgames', action='store_true', help='skip backup of any GOG game files')
    g1.add_argument('-skipgalaxy',action='store_true', help='skip backup of any GOG Galaxy installer files')
    g1.add_argument('-skipstandalone',action='store_true', help='skip backup of any GOG standalone installer files')
    g1.add_argument('-skipshared',action='store_true',help ='skip backup of any installers included in both the GOG Galalaxy and Standalone sets')
    g1.add_argument('-nolog', action='store_true', help = 'doesn\'t writes log file gogrepo.log')
    g1.add_argument('-debug', action='store_true', help = "Includes debug messages")


    g1 = sp1.add_parser('verify', help='Scan your downloaded GOG files and verify their size, MD5, and zip integrity')
    g1.add_argument('gamedir', action='store', help='directory containing games to verify', nargs='?', default=GAME_STORAGE_DIR)
    g1.add_argument('-permissivechangeclear', action='store_true', help='clear change marking for files that pass this test (default is to only clear on MD5 match) ')    
    g1.add_argument('-forceverify', action='store_true', help='also verify files that are unchanged (by gogrepo) since they were last successfully verified')    
    g1.add_argument('-skipmd5', action='store_true', help='do not perform MD5 check')
    g1.add_argument('-skipsize', action='store_true', help='do not perform size check')
    g1.add_argument('-skipzip', action='store_true', help='do not perform zip integrity check')
    g2 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g2.add_argument('-delete', action='store_true', help='delete any files which fail integrity test')
    g2.add_argument('-noclean', action='store_true', help='leave any files which fail integrity test in place')
    g2.add_argument('-clean', action='store_true', help='(deprecated) This is now the default behaviour and this option is provided only to maintain backwards compatibility with existings scripts')
    g3 = g1.add_mutually_exclusive_group()  # below are mutually exclusive
    g3.add_argument('-ids', action='store', help='id(s) or title(s) of the game in the manifest to verify', nargs='*', default=[])
    g3.add_argument('-skipids', action='store', help='id(s) or title(s) of the game[s] in the manifest to NOT verify', nargs='*', default=[])
    g3.add_argument('-id', action='store', help='(deprecated) id or title of the game in the manifest to verify')    
    g1.add_argument('-skipfiles', action='store', help='file name (or glob patterns) to NOT verify', nargs='*', default=[])
    g4 = g1.add_mutually_exclusive_group()  # below are mutually exclusive        
    g4.add_argument('-skipos', action='store', help='skip verification of game files for operating system(s)', nargs='*', default=[])  
    g4.add_argument('-os', action='store', help='verify game files only for operating system(s)', nargs='*', default=[])  
    g5 = g1.add_mutually_exclusive_group()  # below are mutually exclusive    
    g5.add_argument('-skiplang', action='store', help='skip verification of game files for language(s)', nargs='*', default=[])        
    g5.add_argument('-lang', action='store', help='verify game files only for language(s)', nargs='*', default=[])        
    g6 = g1.add_mutually_exclusive_group()
    g6.add_argument('-skipextras', action='store_true', help='skip verification of any GOG extra files')
    g6.add_argument('-skipgames', action='store_true', help='skip verification of any GOG game files')
    g1.add_argument('-skipgalaxy',action='store_true', help='skip verification of any GOG Galaxy installer files')
    g1.add_argument('-skipstandalone',action='store_true', help='skip verification of any GOG standalone installer files')
    g1.add_argument('-skipshared',action='store_true',help ='skip verification of any installers included in both the GOG Galalaxy and Standalone sets')
    g1.add_argument('-nolog', action='store_true', help = 'doesn\'t writes log file gogrepo.log')
    g1.add_argument('-debug', action='store_true', help = "Includes debug messages")


    g1 = sp1.add_parser('clean', help='Clean your games directory of files not known by manifest')
    g1.add_argument('cleandir', action='store', help='root directory containing gog games to be cleaned')
    g1.add_argument('-dryrun', action='store_true', help='do not move files, only display what would be cleaned')
    g1.add_argument('-nolog', action='store_true', help = 'doesn\'t writes log file gogrepo.log')
    g1.add_argument('-debug', action='store_true', help = "Includes debug messages")

    g1 = sp1.add_parser('clear_partial_downloads', help='Permanently remove all partially downloaded files from your game directory')
    g1.add_argument('gamedir', action='store', help='root directory containing gog games')
    g1.add_argument('-dryrun', action='store_true', help='do not move files, only display what would be cleaned')
    g1.add_argument('-nolog', action='store_true', help = 'doesn\'t writes log file gogrepo.log')
    g1.add_argument('-debug', action='store_true', help = "Includes debug messages")

    g1 = sp1.add_parser("gui", help="Launch the tool using the GUI")

    g1 = sp1.add_parser(
        "compress",
        help="Compress a directory, typically your recently downloaded games",
    )

    g1.add_argument(
            "-compressdir",
            action="store",
            help="The source directory to compress",
        )
    
    g1 = sp1.add_parser('trash', help='Permanently remove orphaned files in your game directory (removes all files unless specific parameters are set)')
    g1.add_argument('gamedir', action='store', help='root directory containing gog games')
    g1.add_argument('-dryrun', action='store_true', help='do not move files, only display what would be trashed')
    g1.add_argument('-installersonly', action='store_true', help='(Deprecated) Currently an alias for -installers')
    g1.add_argument('-installers', action='store_true', help='delete file types used as installers')
    g1.add_argument('-images', action='store_true', help='delete !images subfolders')
    g1.add_argument('-nolog', action='store_true', help = 'doesn\'t writes log file gogrepo.log')
    g1.add_argument('-debug', action='store_true', help = "Includes debug messages")
    
    g1 = p1.add_argument_group('other')
    g1.add_argument('-h', '--help', action='help', help='show help message and exit')
    g1.add_argument('-v', '--version', action='version', help='show version number and exit',
                    version="%s (version %s)" % (__appname__, __version__))

    # parse the given argv.  raises SystemExit on error
    args = p1.parse_args(argv[1:])
    
    if getattr(args, 'nolog', None) is None or not args.nolog:
        rootLogger.addHandler(loggingHandler)
        
    if getattr(args, 'debug', None) is None or not args.debug:     
        rootLogger.setLevel(logging.INFO)

    if args.command == 'update' or args.command == 'download' or args.command == 'backup' or args.command == 'import' or args.command == 'verify':
        for lang in args.lang+args.skiplang:  # validate the language
            if lang not in VALID_LANG_TYPES:
                error('error: specified language "%s" is not one of the valid languages %s' % (lang, VALID_LANG_TYPES))
                raise SystemExit(1)

        for os_type in args.os+args.skipos:  # validate the os type
            if os_type not in VALID_OS_TYPES:
                error('error: specified os "%s" is not one of the valid os types %s' % (os_type, VALID_OS_TYPES))
                raise SystemExit(1)
                
    return args

# --------
# Commands
# --------
def cmd_login(user, passwd):
    """Attempts to log into GOG Galaxy API and saves the resulting Token to disk.
    """
    
    login_data = {'user': user,
                  'passwd': passwd,
                  'auth_url': None,
                  'login_token': None,
                  'two_step_url': None,
                  'two_step_token': None,
                  'two_step_security_code': None,
                  'login_success': None
                  }
    

    # prompt for login/password if needed
    if ( login_data['user'] is None ) or ( login_data['passwd'] ) is None:
        print("You must use a GOG or GOG Galaxy account, Google/Discord sign-ins are not currently supported.")
    if login_data['user'] is None:
        login_data['user'] = input("Username: ")
    if login_data['passwd'] is None:
        login_data['passwd'] = getpass.getpass()
        
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
    
    # fetch the auth url
    info("attempting Galaxy login as '{}' ...".format(token_data['user']))
    
    page_response = request(loginSession,GOG_AUTH_URL,args={'client_id':GOG_CLIENT_ID ,'redirect_uri': GOG_GALAXY_REDIRECT_URL + '?origin=client','response_type': 'code','layout':'client2'})
    # fetch the login token
    etree = html5lib.parse(page_response.text, namespaceHTMLElements=False)
    # Bail if we find a request for a reCAPTCHA *in the login form*
    loginForm = etree.find('.//form[@name="login"]')
    if (loginForm is None) or len(loginForm.findall('.//div[@class="g-recaptcha form__recaptcha"]')) > 0:
        if loginForm is None:
            error("Could not locate login form on login page to test for reCAPTCHA, please contact the maintainer. In the meantime use a browser (Firefox recommended) to sign in at the below url and then copy & paste the full URL")
        else:
            error("gog is asking for a reCAPTCHA :(  Please use a browser (Firefox recommended) to sign in at the below url and then copy & paste the full URL")
        error(page_response.url)
        inputUrl  = input("Signed In URL: ")
        try:
            parsed = urlparse(inputUrl)    
            query_parsed = parse_qs(parsed.query)
            token_data['login_code'] = query_parsed['code']
        except Exception:
            error("Could not parse entered URL. Try again later or report to the maintainer")
            return 
    for elm in etree.findall('.//input'):
        if elm.attrib['id'] == 'login__token':
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
                        
    if token_data['login_code']:
        token_start = time.time()
        token_response = request(loginSession,GOG_TOKEN_URL,args={'client_id':GOG_CLIENT_ID ,'client_secret':GOG_SECRET, 'grant_type': 'authorization_code','code': token_data['login_code'],'redirect_uri': GOG_GALAXY_REDIRECT_URL + '?origin=client'})    
        token_json = token_response.json()
        token_json['expiry'] = token_start + token_json['expires_in']
        save_token(token_json)           
    else:
        error('Galaxy login failed, verify your username/password and try again.')

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

def save_token(token):
    info('saving token...')
    try:
        with codecs.open(TOKEN_FILENAME, 'w', 'utf-8') as w:
            pprint.pprint(token, width=123, stream=w)
        info('saved token')
    except KeyboardInterrupt:
        with codecs.open(TOKEN_FILENAME, 'w', 'utf-8') as w:
            pprint.pprint(token, width=123, stream=w)
        info('saved token')            
        raise

def load_token(filepath=TOKEN_FILENAME):
    info('loading token...')
    try:
        with codecs.open(filepath, 'r' + universalLineEnd, 'utf-8') as r:
            ad = r.read().replace('{', 'AttrDict(**{').replace('}', '})')
        return eval(ad)
    except IOError:
        return {}
        
def input_timeout(*ignore):
    raise TimeoutError

        

def cmd_update(os_list, lang_list, skipknown, updateonly, partial, ids, skipids,skipHidden,installers,resumemode,strict,strictDupe,strictDownloadsUpdate,strictExtrasUpdate,md5xmls,noChangeLogs):
    media_type = GOG_MEDIA_TYPE_GAME
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
        save_installers = installers
        installers = resumeprops['installers']
        save_strict = strict
        strict = resumeprops['strict']
        save_strictDupe = strictDupe
        save_strictDownloadsUpdate = strictDownloadsUpdate
        save_strictExtrasUpdate = strictExtrasUpdate
        save_md5xmls = md5xmls
        save_noChangeLogs = noChangeLogs
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
                                
                                
                        if (not partial) or (updateonly and item.has_updates) or (skipknown and item.id not in known_ids):  
                             items.append(item)
                    else:        
                        info('skipping "{}" found in product data!'.format(item.title))
                    
                
            if i >= json_data['totalPages']:
                done = True
                    
     

        if not idsOriginal and not updateonly and not skipknown:
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
        if not idsOriginal and not updateonly and not skipknown:
            info('found %d games !!%s' % (items_count, '!'*int(items_count/100)))  # teehee
            if skipids: 
                formattedSkipIds =  ', '.join(map(str, skipids))        
                info('not including game id(s) from {%s}' % formattedSkipIds)
            
            
    # fetch item details
    i = 0
    resumedb = sorted(items, key=lambda item: item.title)
    resumeprop = {'resume_manifest_syntax_version':RESUME_MANIFEST_SYNTAX_VERSION,'os_list':os_list,'lang_list':lang_list,'installers':installers,'strict':strict,'complete':False,'skipknown':skipknown,'partial':partial,'updateonly':updateonly,'strictDupe':strictDupe,'strictDownloadsUpdate':strictDownloadsUpdate,'strictExtrasUpdate':strictExtrasUpdate,'md5xmls':md5xmls,'noChangeLogs':noChangeLogs}
    resumedb.append(resumeprop)
    save_resume_manifest(resumedb)                    
    
    resumedbInitLength = len(resumedb)
    for item in sorted(items, key=lambda item: item.title):
        api_url  = GOG_ACCOUNT_URL
        api_url += "/gameDetails/{}.json".format(item.id)
        
        

        i += 1
        info("(%*d / %d) fetching game details for %s..." % (print_padding, i, items_count, item.title))

        try:
            response = request(updateSession,api_url)
            
            item_json_data = response.json()

            item.bg_url = item_json_data['backgroundImage']
            item.bg_urls = AttrDict()
            if urlparse(item.bg_url).path != "":
                item.bg_urls[item.long_title] = item.bg_url
            item.serial = item_json_data['cdKey']
            if (sys.version_info[0] >= 3):
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
            else:
                if (not all(c in string.printable for c in  item.serial)):
                    pserial = item.serial
                    if (len(pserial) % 2): #0dd
                        pserial=pserial+"\x00" 
                    pserial = bytearray(pserial,"UTF-8")
                    pserial = pserial.decode("UTF-16")
                    if all(c in string.printable for c in pserial):
                        pserial = pserial.encode("UTF-8")
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
            filter_downloads(item.downloads, item_json_data['downloads'], lang_list, os_list,md5xmls,updateSession)
            filter_downloads(item.galaxyDownloads, item_json_data['galaxyDownloads'], lang_list, os_list,md5xmls,updateSession)                
            filter_extras(item.extras, item_json_data['extras'],md5xmls,updateSession)
            filter_dlcs(item, item_json_data['dlcs'], lang_list, os_list,md5xmls,updateSession)
            
            
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
            else:
                gamesdb.append(item)
        except Exception:
            warn("The handled exception was:")
            log_exception('error')
            warn("End exception report.")        
        resumedb.remove(item)    
        if (updateonly or skipknown or (resumedbInitLength - len(resumedb)) % RESUME_SAVE_THRESHOLD == 0):
            save_manifest(gamesdb)                
            save_resume_manifest(resumedb)                

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
    resumeprop['complete'] = True    
    save_resume_manifest(resumedb) 
    if (needresume):
        info('resume completed')
        if (resumemode != 'onlyresume'):
            info('returning to specified download request...')
            cmd_update(save_os_list, save_lang_list, save_skipknown, save_updateonly, save_partial, ids, skipids,skipHidden,save_installers,resumemode,save_strict,save_strictDupe,save_strictDownloadsUpdate,save_strictExtrasUpdate,save_md5xmls,save_noChangeLogs)


def cmd_import(src_dir, dest_dir,os_list,lang_list,skipextras,skipids,ids,skipgalaxy,skipstandalone,skipshared,destructive):
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
                        
            
        if ids and not (game.title in ids) and not (str(game.id) in ids):
            continue
        if game.title in skipids or str(game.id) in skipids:
            continue
        for game_item in downloads+galaxyDownloads+sharedDownloads:
            if game_item.md5 is not None:
                if game_item.lang in valid_langs:
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
        valid_langs_extras = valid_langs + [u'']
        valid_os_extras = os_list + [u'extra']
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
                            continue
                    info("%s to %s..." % (stringOperationP, dest_file))
                    if not os.path.isdir(game_dest_dir):
                        os.makedirs(game_dest_dir)
                    if destructive:
                        shutil.move(f, dest_file)
                    else:
                        shutil.copy(f, dest_file)
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
                        setattr(entry,"old_updated",updated)
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

def cmd_download(savedir, skipextras,skipids, dryrun, ids,os_list, lang_list,skipgalaxy,skipstandalone,skipshared, skipfiles,covers,backgrounds,skippreallocation,clean_old_images,downloadLimit = None):
    sizes, rates, errors = {}, {}, {}
    work = Queue()  # build a list of work items
    work_provisional = Queue()  # build a list of work items for provisional

    if not dryrun:
        downloadSession = makeGOGSession()    

    items = load_manifest()
    all_items = items
    work_dict = dict()
    provisional_dict = dict()

    # util
    def megs(b):
        return '%.1fMB' % (b / float(1024**2))
    def gigs(b):
        return '%.2fGB' % (b / float(1024**3))

    if ids:
        formattedIds =  ', '.join(map(str, ids))
        info("downloading games with id(s): {%s}" % formattedIds)
        downloadItems = [item for item in items if item.title in ids or str(item.id) in ids]
        items = downloadItems
        

    if skipids:
        formattedSkipIds =  ', '.join(map(str, skipids))
        info("skipping games with id(s): {%s}" % formattedSkipIds)
        downloadItems = [item for item in items if item.title not in skipids and str(item.id) not in skipids]
        items = downloadItems

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

    handle_game_renames(savedir,items,dryrun)

    #writable_items = load_manifest() #Load unchanged item list, so we don't save the filtering stuff.
    all_items_by_id = {}
    for item in all_items:
        all_items_by_id[item.id] = item
        
 
    
    all_items_by_title = {}    

    # make convenient dict with title/dirname as key
    for item in all_items:
        try:
            _ = item.folder_name 
        except AttributeError:
            item.folder_name = item.title
        all_items_by_title[item.folder_name] = item
        

    downloadingdir = os.path.join(savedir, DOWNLOADING_DIR_NAME)    
    provisionaldir = os.path.join(downloadingdir,PROVISIONAL_DIR_NAME )
    orphandir =  os.path.join(savedir, ORPHAN_DIR_NAME)  
    
    if os.path.isdir(downloadingdir):
        info ("Cleaning up " + downloadingdir)
        for cur_dir in sorted(os.listdir(downloadingdir)):
            cur_fulldir = os.path.join(downloadingdir, cur_dir)
            if os.path.isdir(cur_fulldir):
                if cur_dir != PROVISIONAL_DIR_NAME: #Leave the provisional directory alone
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
                            if os.path.isdir(os.path.join(downloadingdir, cur_dir, cur_dir_file)):
                                info("Removing subdirectory(?!) " + os.path.join(downloadingdir, cur_dir, cur_dir_file))                    
                                if not dryrun:
                                    shutil.rmtree(os.path.join(downloadingdir, cur_dir, cur_dir_file)) #There shouldn't be subdirectories here ?? Nuke to keep clean.
                            else: 
                                if cur_dir_file not in expected_filenames:
                                    info("Removing outdated file " + os.path.join(downloadingdir, cur_dir, cur_dir_file))    
                                    if not dryrun:
                                        os.remove(os.path.join(downloadingdir, cur_dir, cur_dir_file))

    if os.path.isdir(provisionaldir):
        info ("Cleaning up " +  provisionaldir)
        for cur_dir in sorted(os.listdir(provisionaldir)):
            cur_fulldir = os.path.join(provisionaldir, cur_dir)
            if os.path.isdir(cur_fulldir):
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
                        if os.path.isdir(os.path.join(provisionaldir, cur_dir, cur_dir_file)):
                            info("Removing subdirectory(?!) " + os.path.join(provisionaldir, cur_dir, cur_dir_file))                    
                            if not dryrun:
                                shutil.rmtree(os.path.join(provisionaldir, cur_dir, cur_dir_file)) #There shouldn't be subdirectories here ?? Nuke to keep clean.
                        else: 
                            if cur_dir_file not in expected_filenames:
                                info("Removing outdated file " + os.path.join(provisionaldir, cur_dir, cur_dir_file))    
                                if not dryrun:
                                    os.remove(os.path.join(provisionaldir, cur_dir, cur_dir_file))

                                        
                                        
        
    for item in items:
        try:
            _ = item.folder_name 
        except AttributeError:
            item.folder_name = item.title
            

    # Find all items to be downloaded and push into work queue
    for item in sorted(items, key=lambda g: g.folder_name):
        info("{%s}" % item.folder_name)
        item_homedir = os.path.join(savedir, item.folder_name)
        item_downloaddir = os.path.join(downloadingdir, item.folder_name)
        item_provisionaldir =os.path.join(provisionaldir, item.folder_name)
        item_orphandir = os.path.join(orphandir,item.folder_name)
        if not dryrun:
            if not os.path.isdir(item_homedir):
                os.makedirs(item_homedir)
                
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
        #print(item.downloads)
        
        downloadsOS = [game_item for game_item in filtered_galaxyDownloads if game_item.os_type in os_list]
        filtered_galaxyDownloads = downloadsOS

        downloadsOS = [game_item for game_item in  filtered_sharedDownloads if game_item.os_type in os_list]
        filtered_sharedDownloads = downloadsOS
        

        # hold list of valid languages languages as known by gogapi json stuff
        valid_langs = []
        for lang in lang_list:
            valid_langs.append(LANG_TABLE[lang])

        
        downloadslangs = [game_item for game_item in filtered_downloads if game_item.lang in valid_langs]
        filtered_downloads = downloadslangs
        #print(item.downloads)

        downloadslangs = [game_item for game_item in filtered_galaxyDownloads if game_item.lang in valid_langs]
        filtered_galaxyDownloads = downloadslangs

        downloadslangs = [game_item for game_item in filtered_sharedDownloads if game_item.lang in valid_langs]
        filtered_sharedDownloads = downloadslangs


        # Generate and save a game info text file
        if not dryrun:
            with ConditionalWriter(os.path.join(item_homedir, INFO_FILENAME)) as fd_info:
                fd_info.write(u'{0}-- {1} --{0}{0}'.format(os.linesep, item.long_title))
                fd_info.write(u'title.......... {}{}'.format(item.title, os.linesep))
                if item.genre:
                    fd_info.write(u'genre.......... {}{}'.format(item.genre, os.linesep))
                fd_info.write(u'game id........ {}{}'.format(item.id, os.linesep))
                fd_info.write(u'url............ {}{}'.format(GOG_HOME_URL + item.store_url, os.linesep))
                if item.rating > 0:
                    fd_info.write(u'user rating.... {}%{}'.format(item.rating * 2, os.linesep))
                if item.release_timestamp > 0:
                    rel_date = datetime.datetime.fromtimestamp(item.release_timestamp).strftime('%B %d, %Y')
                    fd_info.write(u'release date... {}{}'.format(rel_date, os.linesep))
                if hasattr(item, 'gog_messages') and item.gog_messages:
                    fd_info.write(u'{0}gog messages...:{0}'.format(os.linesep))
                    for gog_msg in item.gog_messages:
                        fd_info.write(u'{0}{1}{0}'.format(os.linesep, html2text(gog_msg).strip().replace("\n",os.linesep)))
                fd_info.write(u'{0}game items.....:{0}{0}'.format(os.linesep))
                if len(filtered_downloads) > 0:
                    fd_info.write(u'{0}    standalone...:{0}{0}'.format(os.linesep))                
                for game_item in filtered_downloads:
                    fd_info.write(u'        [{}] -- {}{}'.format(game_item.name, game_item.desc, os.linesep))
                    if game_item.version:
                        fd_info.write(u'            version: {}{}'.format(game_item.version, os.linesep))
                if len(filtered_galaxyDownloads) > 0:
                    fd_info.write(u'{0}    galaxy.......:{0}{0}'.format(os.linesep))                                        
                for game_item in filtered_galaxyDownloads:
                    fd_info.write(u'        [{}] -- {}{}'.format(game_item.name, game_item.desc, os.linesep))
                    if game_item.version:
                        fd_info.write(u'            version: {}{}'.format(game_item.version, os.linesep))
                if len(filtered_sharedDownloads) > 0:                        
                    fd_info.write(u'{0}    shared.......:{0}{0}'.format(os.linesep))                                        
                for game_item in filtered_sharedDownloads:
                    fd_info.write(u'        [{}] -- {}{}'.format(game_item.name, game_item.desc, os.linesep))
                    if game_item.version:
                        fd_info.write(u'            version: {}{}'.format(game_item.version, os.linesep))                        
                if len(filtered_extras) > 0:
                    fd_info.write(u'{0}extras.........:{0}{0}'.format(os.linesep))
                    for game_item in filtered_extras:
                        fd_info.write(u'    [{}] -- {}{}'.format(game_item.name, game_item.desc, os.linesep))
                if item.changelog:
                    fd_info.write(u'{0}changelog......:{0}{0}'.format(os.linesep))
                    fd_info.write(html2text(item.changelog).strip().replace("\n",os.linesep))
                    fd_info.write(os.linesep)
        # Generate and save a game serial text file
        if not dryrun:
            try:
                if len(item.serials) != 0:
                    with ConditionalWriter(os.path.join(item_homedir, SERIAL_FILENAME)) as fd_serial:
                        for key in item.serials.keys():
                            serial = item.serials[key]
                            fd_serial.write(key + ":\n\n" )
                            serial = serial.replace(u'<span>', '')
                            serial = serial.replace(u'</span>', os.linesep)
                            serial = serial.rstrip('\n')
                            fd_serial.write(serial)
                            fd_serial.write("\n\n")
            except AttributeError:
                    if item.serial != '':
                        with ConditionalWriter(os.path.join(item_homedir, SERIAL_FILENAME)) as fd_serial:
                            item.serial = item.serial.replace(u'<span>', '')
                            item.serial = item.serial.replace(u'</span>', os.linesep)
                            fd_serial.write(item.serial)

        
        def download_image_from_item_key(item,key,images_dir_name,image_orphandir,clean_existing): 
            images_key_dir_name = os.path.join(images_dir_name,key)
            key_local_path = item[key].lstrip("/") + ".jpg"
            key_url = 'https://' + key_local_path
            (dir,file) = os.path.split(key_local_path)
            key_local_path_dir = os.path.join(images_key_dir_name,dir) 
            key_local_path_file = os.path.join(key_local_path_dir,file) 
            modified_images_key_dir_name = images_key_dir_name
            if (platform.system() == "Windows" and sys.version_info[0] < 3):
                key_local_path_file = uLongPathPrefix + os.path.abspath(key_local_path_file)
                key_local_path_dir = uLongPathPrefix + os.path.abspath(key_local_path_dir)
                image_orphandir = uLongPathPrefix + os.path.abspath(image_orphandir)
                modified_images_key_dir_name = uLongPathPrefix + os.path.abspath( modified_images_key_dir_name)
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
                response = request(downloadSession,key_url)
                os.makedirs(key_local_path_dir)
                with open(key_local_path_file,"wb") as out:
                    out.write(response.content)

        def download_image_from_item_keys(item,keys,images_dir_name,image_orphandir,clean_existing):
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
                if (platform.system() == "Windows" and sys.version_info[0] < 3):
                    longpath_safe_leading_partial_key_local_path_dir = uLongPathPrefix + os.path.abspath(longpath_safe_leading_partial_key_local_path_dir)
                if not os.path.exists(longpath_safe_leading_partial_key_local_path_dir):
                    os.makedirs(longpath_safe_leading_partial_key_local_path_dir)
                full_key_local_path_dir = os.path.join(leading_partial_key_local_path_dir,trailing_partial_key_local_path_dir)
                full_key_local_path_file = os.path.join(full_key_local_path_dir,trailing_partial_key_local_path_file)
                key_url = 'https://' + partial_key_local_path
                if (platform.system() == "Windows" and sys.version_info[0] < 3):
                    full_key_local_path_file = uLongPathPrefix + os.path.abspath(full_key_local_path_file)
                    full_key_local_path_dir = uLongPathPrefix + os.path.abspath(full_key_local_path_dir)
                if not os.path.exists(full_key_local_path_file):
                    if os.path.exists(full_key_local_path_dir):
                        images_full_key_local_path_orphandir = os.path.join(images_key_orphandir_name,leading_partial_key_local_path)
                        if (platform.system() == "Windows" and sys.version_info[0] < 3):
                             images_full_key_local_path_orphandir = uLongPathPrefix + os.path.abspath( images_full_key_local_path_orphandir)
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
                        response = request(downloadSession,key_url)
                        os.makedirs(full_key_local_path_dir)
                        with open(full_key_local_path_file,"wb") as out:
                            out.write(response.content)
                    except requests.HTTPError:
                        error('Could not download background image ' + full_key_local_path_file)
            for potential_old_folder in sorted(os.listdir(images_key_dir_name)):
                if potential_old_folder not in validPaths:
                    potential_old_folder_path = os.path.join(images_key_dir_name,potential_old_folder)
                    try:
                        if (platform.system() == "Windows" and sys.version_info[0] < 3): #Work around for rmtree not handling long path names on 2.7 + Windows , can just rm.shutil the full_key_local_path_dir for pure 3+
                            potential_old_folder_path = uLongPathPrefix + os.path.abspath(potential_old_folder_path)
                            images_key_orphandir_name = uLongPathPrefix + os.path.abspath(images_key_orphandir_name)
                        if (clean_existing):
                            if not os.path.exists(images_key_orphandir_name):
                                os.makedirs(images_key_orphandir_name)
                            move_with_increment_on_clash(potential_old_folder_path, images_key_orphandir_name)
                        else:
                            shutil.rmtree(potential_old_folder_path)
                    except Exception as e:
                        error("Could not remove potential old image files, aborting update attempt. Please make sure folder and files are writeable and that nothing is accessing the !image folder")
                        raise

        #Download images
        if not dryrun:
            images_dir_name = os.path.join(item_homedir, IMAGES_DIR_NAME)
            image_orphandir = os.path.join(item_orphandir,IMAGES_DIR_NAME)

            if not os.path.exists(images_dir_name):
                os.makedirs(images_dir_name)
            try:
                if len(item.bg_urls) != 0 and backgrounds:
                    images_old_bg_url_dir_name = os.path.join(images_dir_name,"bg_url")
                    modified_image_orphandir =  image_orphandir  
                    if (platform.system() == "Windows" and sys.version_info[0] < 3): #Work around for rmtree not handling long path names on 2.7 + Windows
                        images_old_bg_url_dir_name =  uLongPathPrefix + os.path.abspath(images_old_bg_url_dir_name)
                        modified_image_orphandir =  uLongPathPrefix + os.path.abspath(modified_image_orphandir )
                    if os.path.exists(images_old_bg_url_dir_name):
                        try:
                            if (clean_existing):
                                if not os.path.exists( modified_image_orphandir):
                                    os.makedirs( imodified_image_orphandir)
                                move_with_increment_on_clash(images_old_bg_url_dir_name , modified_image_orphandir)
                            else:
                                shutil.rmtree(images_old_bg_url_dir_name )
                        except Exception as e:
                            error("Could not delete potential old bg_url files, aborting update attempt. Please make sure folder and files are writeable and that nothing is accessing the !image folder")
                            raise
                    try:
                        download_image_from_item_keys(item,"bg_urls",images_dir_name,image_orphandir,clean_old_images)
                    except KeyboardInterrupt:
                        warn("Interrupted during download of background image(s)")
                        raise
                    except Exception:
                        warn("Could not download background image")
                    
            except AttributeError:
                if item.bg_url != '' and backgrounds:
                    try:
                        download_image_from_item_key(item,"bg_url",images_dir_name,image_orphandir,clean_old_images)
                    except KeyboardInterrupt:
                        warn("Interrupted during download of background image")
                        raise
                    except Exception:
                        warn("Could not download background image")
                
            if item.image_url != '' and covers:
                try:
                    download_image_from_item_key(item,"image_url",images_dir_name,image_orphandir,clean_old_images)
                except KeyboardInterrupt:
                    warn("Interrupted during download of cover image")
                    raise
                except Exception:
                    warn("Could not download cover image")

        #updatable_item = all_items_by_id[item.id]
        #potential_game_items = updatable_item.downloads + updatable_item.galaxyDownloads + updatable_item.sharedDownloads + updatable_item.extras
 

        # Populate queue with all files to be downloaded
        for game_item in filtered_downloads + filtered_galaxyDownloads + filtered_sharedDownloads + filtered_extras:
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
                continue

            dest_file = os.path.join(item_homedir, game_item.name)
            downloading_file = os.path.join(item_downloaddir, game_item.name)
            provisional_file = os.path.join(item_provisionaldir,game_item.name)

            if game_item.size is None:
                warn('     unknown    %s has no size info.  skipping' % game_item.name)
                continue

            if os.path.isfile(provisional_file):
                if os.path.isfile(dest_file):
                    #I don't know how you got it here, but if you did , clean up your mess! This is not my problem. But more politely. 
                    warn('     error      %s has both provisional and destination file. Please remove one.' % game_item.name)
                    continue
                else:
                    info('     working    %s' % game_item.name)
                    provisional_dict[dest_file] = (dest_file,provisional_file,game_item,all_items)
                    continue
                    
                
            if os.path.isfile(dest_file):
                if game_item.size != os.path.getsize(dest_file):
                    warn('     fail       %s has incorrect size.' % game_item.name)
                elif game_item.force_change == True:
                    warn('     fail       %s has been marked for change.' % game_item.name)
                else:
                    info('     pass       %s' % game_item.name)
                    continue  # move on to next game item
            
            if downloadLimit is not None and ((sum(sizes.values()) + game_item.size) > downloadLimit):
                info('     skip       %s (size %s would exceed download limit (%s/%s) )' % (game_item.name, megs(game_item.size),megs(sum(sizes.values())),megs(downloadLimit)))
                continue

            
            info('     download   %s' % game_item.name)
            sizes[dest_file] = game_item.size
            
        
            work_dict[dest_file] = (game_item.href, game_item.size, 0, game_item.size-1, dest_file,downloading_file,provisional_file,game_item,all_items)
    
    for work_item in work_dict:
        work.put(work_dict[work_item])
    
    for provisional_item in provisional_dict:
        work_provisional.put(provisional_dict[provisional_item])

    if dryrun:
        info("{} left to download".format(gigs(sum(sizes.values()))))
        return  # bail, as below just kicks off the actual downloading
        
    if work.empty():
        info("nothing to download")
        return
    
    downloading_root_dir = os.path.join(savedir, DOWNLOADING_DIR_NAME)
    if not os.path.isdir(downloading_root_dir):
        os.makedirs(downloading_root_dir)

    provisional_root_dir = os.path.join(savedir, DOWNLOADING_DIR_NAME,PROVISIONAL_DIR_NAME)
    if not os.path.isdir(provisional_root_dir):
        os.makedirs(provisional_root_dir)        

    info('-'*60)
    
    def killresponse(response):
        response.close()

    # work item I/O loop
    def ioloop(tid, path, response, out):
        #info("Entering I/O Loop - " + path)
        sz, t0 = True, time.time()
        dlsz = 0
        responseTimer = threading.Timer(HTTP_TIMEOUT,killresponse,[response])
        responseTimer.start()
        try:
            for chunk in response.iter_content(chunk_size=4*1024):
                responseTimer.cancel()
                if (chunk):
                    t = time.time()
                    out.write(chunk)
                    sz, dt, t0 = len(chunk), t - t0, t
                    dlsz = dlsz + sz
                    with lock:
                        sizes[path] -= sz
                        rates.setdefault(path, []).append((tid, (sz, dt)))
                responseTimer = threading.Timer(HTTP_TIMEOUT,killresponse,[response])
                responseTimer.start()
        except (requests.exceptions.ConnectionError,requests.packages.urllib3.exceptions.ProtocolError) as e:
            error("server response issue while downloading content for %s" % (path))
        except (requests.exceptions.SSLError) as e:
            error("SSL issue while downloading content for %s" % (path))
        responseTimer.cancel()
        #info("Exiting I/O Loop - " + path)
        return dlsz            

    # downloader worker thread main loop
    def worker():
        tid = threading.current_thread().ident
        while not work.empty():
            (href, sz, start, end, path,downloading_path,provisional_path,writable_game_item,work_writable_items) = work.get()
            try:
                dest_dir = os.path.dirname(path)
                downloading_dir = os.path.dirname(downloading_path)
                provisional_dir = os.path.dirname(provisional_path)
                compat_downloading_path = process_path(downloading_path)
                with lock:
                    if not os.path.isdir(dest_dir):
                        os.makedirs(dest_dir)
                    if not os.path.isdir(downloading_dir):    
                        os.makedirs(downloading_dir)                    
                    if not os.path.isdir(provisional_dir):    
                        os.makedirs(provisional_dir) 
                    if (os.path.exists(path)):    
                        info("moving existing file '%s' to '%s' for downloading " % (path,downloading_path))
                        shutil.move(path,downloading_path)
                        file_sz = os.path.getsize(downloading_path)    
                        if file_sz > sz:  # if needed, truncate file if ours is larger than expected size
                            with open_notrunc(downloading_path) as f:
                                f.truncate(sz)
                        if file_sz < sz: #preallocate extra space
                            if not skippreallocation:
                                if platform.system() == "Darwin":
                                    #MacOS doesn't support posix.fallocate
                                    pass
                                elif platform.system() == "Windows":
                                    fs = get_fs_type(compat_downloading_path,True)
                                    if fs in WINDOWS_PREALLOCATION_FS:
                                        try:
                                            info("increasing preallocation to '%d' bytes for '%s' " % (sz,downloading_path))
                                            preH = ctypes.windll.kernel32.CreateFileW(compat_downloading_path, GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None)
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
                                                info('failed - closing outstanding handle')
                                                ctypes.windll.kernel32.CloseHandle(preH)                             
                                else:
                                    fs = get_fs_type(downloading_path)
                                    if fs.lower() in POSIX_PREALLOCATION_FS:
                                        if sys.version_info[0] >= 3:
                                            info("increasing preallocation to '%d' bytes for '%s' using posix_fallocate " % (sz,downloading_path))
                                            with open(downloading_path, "r+b") as f:
                                                try:
                                                    os.posix_fallocate(f.fileno(),0,sz)
                                                except Exception:    
                                                    warn("posix preallocation failed")
                    else:
                        if (os.path.exists(downloading_path)):
                            file_sz = os.path.getsize(downloading_path)    
                            if file_sz > sz:  # if needed, truncate file if ours is larger than expected size
                                with open_notrunc(downloading_path) as f:
                                    f.truncate(sz)
                            if file_sz < sz: #preallocate extra space       
                                if not skippreallocation:
                                    if platform.system() == "Darwin":
                                        #MacOS doesn't support posix.fallocate
                                        pass
                                    elif platform.system() == "Windows":
                                        fs = get_fs_type(downloading_path,True)
                                        if fs in WINDOWS_PREALLOCATION_FS:
                                            try:
                                                preH = -1 
                                                info("increasing preallocation to '%d' bytes for '%s' " % (sz,downloading_path))
                                                preH = ctypes.windll.kernel32.CreateFileW(compat_downloading_path, GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_EXISTING, 0, None)
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
                                                    info('failed - closing outstanding handle')
                                                    ctypes.windll.kernel32.CloseHandle(preH) 
                                    else:
                                        fs = get_fs_type(downloading_path)
                                        if fs.lower() in POSIX_PREALLOCATION_FS:
                                            if sys.version_info[0] >= 3:
                                                info("increasing preallocation to '%d' bytes for '%s' using posix_fallocate " % (sz,downloading_path))
                                                with open(downloading_path, "r+b") as f:
                                                    try:
                                                        os.posix_fallocate(f.fileno(),0,sz)
                                                    except Exception:    
                                                        warn("posix preallocation failed")
                        else:
                            if not skippreallocation:
                                if platform.system() == "Darwin":
                                    #MacOS doesn't support posix.fallocate
                                    pass
                                elif platform.system() == "Windows":
                                    fs = get_fs_type(downloading_path,True)
                                    if fs in WINDOWS_PREALLOCATION_FS:
                                        try:
                                            preH = -1 
                                            info("preallocating '%d' bytes for '%s' " % (sz,downloading_path))
                                            preH = ctypes.windll.kernel32.CreateFileW(compat_downloading_path, GENERIC_READ | GENERIC_WRITE, 0, None, CREATE_NEW, 0, None)
                                            if preH==-1:
                                                warn("could not get filehandle")
                                                raise OSError()
                                            c_sz = ctypes.wintypes.LARGE_INTEGER(sz)
                                            ctypes.windll.kernel32.SetFilePointerEx(preH,c_sz,None,FILE_BEGIN)  
                                            ctypes.windll.kernel32.SetEndOfFile(preH)   
                                            ctypes.windll.kernel32.CloseHandle(preH) 
                                            #DEVNULL = open(os.devnull, 'wb')
                                            #subprocess.call(["fsutil","file","createnew",path,str(sz)],stdout=DEVNULL,stderr=DEVNULL)
                                        except Exception:
                                            warn("preallocation failed")
                                            warn("The handled exception was:")
                                            log_exception('')
                                            warn("End exception report.")
                                            if preH != -1:
                                                info('failed - closing outstanding handle')
                                                ctypes.windll.kernel32.CloseHandle(preH) 
                                else:
                                    fs = get_fs_type(downloading_path)
                                    if fs.lower() in POSIX_PREALLOCATION_FS:
                                        if sys.version_info[0] >= 3:
                                            info("attempting preallocating '%d' bytes for '%s' using posix_fallocate " % (sz,downloading_path))
                                            with open(downloading_path, "wb") as f:
                                                try:
                                                    os.posix_fallocate(f.fileno(),0,sz)
                                                except Exception:    
                                                    warn("posix preallocation failed")
                succeed = False                       
                response = request_head(downloadSession,href)
                chunk_tree = fetch_chunk_tree(response,downloadSession)
                if (chunk_tree is not None):
                    name = chunk_tree.attrib['name']
                    expected_size = int(chunk_tree.attrib['total_size'])
                    if (expected_size != sz):
                        with lock:
                            error("XML verification data size does not match manifest size for %s. manifest %d, received %d, skipping. "
                                  % (name, sz, expected_size))
                    else:
                        expected_no_of_chunks = int(chunk_tree.attrib['chunks'])
                        actual_no_of_chunks = len(list(chunk_tree))
                        if (expected_no_of_chunks != actual_no_of_chunks):
                            with lock:
                                error("XML verification chunk data for %s is not sane skipping." % name)
                        else: 
                            succeed = True
                            for elem in list(chunk_tree):
                                method = elem.attrib["method"]
                                if (method != "md5"):
                                    error("XML chunk verification method for %s is not md5. skipping. " %name)
                                    succeed = succeed and False
                                else:
                                    start = int(elem.attrib["from"])
                                    end =   int(elem.attrib["to"])
                                    se = start,end
                                    md5 = elem.text
                                    with open_notruncwrrd(downloading_path) as out:
                                        valid = hashstream(out,start,end) == md5
                                        if (valid):
                                            with lock:
                                                sizes[path] -= (end - start)+1
                                        else:
                                            retries = HTTP_RETRY_COUNT
                                            downloadSegmentSuccess = False
                                            while (not downloadSegmentSuccess and retries >= 0):
                                                try:
                                                    response = request(downloadSession,href, byte_range=(start,end),stream=True)
                                                    hdr = response.headers['Content-Range'].split()[-1]
                                                    if hdr != '%d-%d/%d' % (start, end, sz):
                                                        with lock:
                                                            error("chunk request has unexpected Content-Range. "
                                                                  "expected '%d-%d/%d' received '%s'. skipping."
                                                                  % (start, end, sz, hdr))
                                                            succeed = succeed and False
                                                            retries = -1
                                                    else:
                                                        out.seek(start)
                                                        assert out.tell() == start
                                                        dlsz = ioloop(tid, path, response, out)
                                                        if (dlsz == (end - start)+1 and out.tell() == end + 1):
                                                            downloadSegmentSuccess= True;
                                                            succeed = succeed and True
                                                        else:
                                                            with lock:
                                                                sizes[path] += dlsz
                                                            if (retries > 0):
                                                                warn("failed to download %s, byte_range=%s (%d retries left) -- will retry in %ds..." % (os.path.basename(path), str(se),retries,HTTP_RETRY_DELAY))
                                                            else:
                                                                error("failed to download %s, byte_range=%s" % (os.path.basename(path), str(se)))
                                                                succeed = succeed and False;
                                                        retries = retries -1 
                                                except requests.HTTPError as e:
                                                    with lock:
                                                        error("failed to download %s, byte_range=%s" % (os.path.basename(path), str(se)))
                                                        succeed = succeed and False
                                                        retries = -1
                                                except Exception as e:
                                                     with lock:
                                                        warn("The unhandled exception was:")
                                                        log_exception('')
                                                        warn("End exception report.")
                                                        raise
                else:
                    with open_notrunc(downloading_path) as out:
                        se = start, end
                        retries = HTTP_RETRY_COUNT
                        downloadSuccess = False
                        while ((not downloadSuccess) and retries >= 0):
                            try:
                                response = request(downloadSession,href, byte_range=(start,end),stream=True)
                                hdr = response.headers['Content-Range'].split()[-1]
                                if hdr != '%d-%d/%d' % (start, end, sz):
                                    with lock:
                                        error("chunk request has unexpected Content-Range. "
                                              "expected '%d-%d/%d' received '%s'. skipping."
                                              % (start, end, sz, hdr))
                                        succeed = False
                                        retries = -1
                                else:
                                    out.seek(start)
                                    assert out.tell() == start
                                    dlsz = ioloop(tid, path, response, out)
                                    if (dlsz == (end - start)+1 and out.tell() == end + 1):
                                        downloadSuccess= True;
                                        succeed = True
                                    else:
                                        with lock:
                                            sizes[path] += dlsz
                                            if (retries > 0):
                                                warn("failed to download %s, byte_range=%s (%d retries left) -- will retry in %ds..." % (os.path.basename(path), str(se),retries,HTTP_RETRY_DELAY))
                                                time.sleep(HTTP_RETRY_DELAY)
                                            else:
                                                error("failed to download %s, byte_range=%s" % (os.path.basename(path), str(se)))
                                                succeed = False;
                                            retries = retries -1 
                            except requests.HTTPError as e:
                                error("failed to download %s, byte_range=%s" % (os.path.basename(path), str(se)))
                                succeed = False
                                retries = -1
                            except Exception as e:
                                 with lock:
                                    warn("The unhandled exception was:")
                                    log_exception('')
                                    warn("End exception report.")
                                    raise
                if succeed and sizes[path]==0:
                    with lock:
                        info("moving provisionally completed download '%s' to '%s'  " % (downloading_path,provisional_path))
                        shutil.move(downloading_path,provisional_path)
                        #if writable_game_item != None:
                        #    try:
                        #        _ = writable_game_item.force_change
                        #    except AttributeError:
                        #        writable_game_item.force_change = False
                        #    try:
                        #        _ = writable_game_item.updated
                        #    except AttributeError:
                        #        writable_game_item.updated = None
                        #    try:
                        #        _ = writable_game_item.old_updated
                        #    except AttributeError:
                        #        writable_game_item.old_updated = None
                        #    try:
                        #        _ = writable_game_item.prev_verified
                        #    except AttributeError:
                        #        writable_game_item.prev_verified = False

                        #    wChanged = False;
                        #    if writable_game_item.force_change:
                        #        writable_game_item.force_change = False
                        #        writable_game_item.old_updated = writable_game_item.updated
                        #        wChanged = True
                        #    if writable_game_item.prev_verified:
                        #        writable_game_item.prev_verified = False
                        #        wChanged = True
                        #    if wChanged:  
                        #        save_manifest(work_writable_items)
                    #This should be thread safe so should be fine outside the lock, doing it after the lock so we don't add this if something went wrong.
                    work_provisional.put((path,provisional_path,writable_game_item,work_writable_items)) 
                else:
                    with lock:
                        info("not moving uncompleted download '%s', success: %s remaining bytes: %d / %d " % (downloading_path,str(succeed),sizes[path],sz))
            except IOError as e:
                with lock:
                    warn("The handled exception was:")
                    log_exception('')
                    warn("End exception report.")
                    print('!', path, file=sys.stderr)
                    errors.setdefault(path, []).append(e)
            except Exception as e:
                 with lock:
                    warn("The unhandled exception was:")
                    log_exception('')
                    warn("End exception report.")
                    raise
            #debug 
            #info("thread completed")
            work.task_done()

    # detailed progress report
    def progress():
        with lock:
            left = sum(sizes.values())
            for path, flowrates in sorted(rates.items()):
                flows = {}
                for tid, (sz, t) in flowrates:
                    szs, ts = flows.get(tid, (0, 0))
                    flows[tid] = sz + szs, t + ts
                bps = sum(szs/ts for szs, ts in list(flows.values()) if ts > 0)
                info('%10s %8.1fMB/s %2dx  %s' % \
                    (megs(sizes[path]), bps / 1024.0**2, len(flows), "%s/%s" % (os.path.basename(os.path.split(path)[0]), os.path.split(path)[1])))
            if len(rates) != 0:  # only update if there's change
                info('%s remaining' % gigs(left))
            rates.clear()

    # process work items with a thread pool
    lock = threading.Lock()
    pool = []
    for i in range(HTTP_GAME_DOWNLOADER_THREADS):
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()
        pool.append(t)
    try:
        while any(t.is_alive() for t in pool):
            progress()
            time.sleep(1)
    except KeyboardInterrupt:
        raise
    except Exception:
        with lock:
            warn("The unhandled exception was:")
            log_exception('')
            warn("End exception report.")
        raise

    wChanged = False;
    
    #Everything here would be done inside a lock so may as well process it in the main thread.
    while not work_provisional.empty():
        (path,provisional_path,writable_game_item,work_writable_items) = work_provisional.get()
        info("moving provisionally completed download '%s' to '%s'  " % (provisional_path,path))
        shutil.move(provisional_path,path)
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
    if wChanged:  
        save_manifest(work_writable_items)

    
    for dir in os.listdir(downloading_root_dir):
        if dir != PROVISIONAL_DIR_NAME:
            testdir= os.path.join(downloading_root_dir,dir)
            if os.path.isdir(testdir):
                if not os.listdir(testdir):
                    try:
                        os.rmdir(testdir)
                    except Exception:
                        pass

    for dir in os.listdir(provisional_root_dir):
        testdir= os.path.join(provisional_root_dir,dir)
        if os.path.isdir(testdir):
            if not os.listdir(testdir):
                try:
                    os.rmdir(testdir)
                except Exception:
                    pass
                    
def cmd_backup(src_dir, dest_dir,skipextras,os_list,lang_list,ids,skipids,skipgalaxy,skipstandalone,skipshared):
    gamesdb = load_manifest()
    
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
            
        if ids and not (game.title in ids) and not (str(game.id) in ids):
            continue
        if game.title in skipids or str(game.id) in skipids:
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

        downloadslangs = [game_item for game_item in game.downloads if game_item.lang in valid_langs]
        game.downloads = downloadslangs
        
        downloadslangs = [game_item for game_item in game.galaxyDownloads if game_item.lang in valid_langs]
        game.galaxyDownloads = downloadslangs

        downloadslangs = [game_item for game_item in game.sharedDownloads if game_item.lang in valid_langs]
        game.sharedDownloads = downloadslangs
        
        
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
                    continue
                if not os.path.isdir(dest_game_dir):
                    os.makedirs(dest_game_dir)
                if not os.path.exists(dest_file) or itm.size != os.path.getsize(dest_file):
                    info('copying to %s...' % dest_file)
                    shutil.copy(src_file, dest_file)
                    touched = True

        # backup the info and serial files too
        if touched and os.path.isdir(dest_game_dir):
            for extra_file in [INFO_FILENAME, SERIAL_FILENAME]:
                if os.path.exists(os.path.join(src_game_dir, extra_file)):
                    shutil.copy(os.path.join(src_game_dir, extra_file), dest_game_dir)


def cmd_verify(gamedir, skipextras, skipids,  check_md5, check_filesize, check_zips, delete_on_fail, clean_on_fail, ids, os_list, lang_list, skipgalaxy,skipstandalone,skipshared, skipfiles, force_verify, permissive_change_clear):
    """Verifies all game files match manifest with any available md5 & file size info
    """
    item_count = 0
    missing_cnt = 0
    bad_md5_cnt = 0
    bad_size_cnt = 0
    bad_zip_cnt = 0
    del_file_cnt = 0
    clean_file_cnt = 0
    prev_verified_cnt = 0
    skip_cnt = 0

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
        games_to_check = [game for game in games_to_check_base if (game.title not in skipids and str(game.id) not in skipids)]
        games_to_skip = [game for game in games_to_check_base if (game.title  in skipids or str(game.id) in skipids)]
        games_to_skip_titles = [game.title for game in games_to_skip]
        games_to_skip_ids = [str(game.id) for game in games_to_skip]        
        not_skipped = [id for id in skipids if id not in games_to_skip_titles and id not in games_to_skip_ids]
        if not_skipped:
            formattedNotSkipped =  ', '.join(map(str, not_skipped))                
            warn('The following id(s)/title(s) could not be found to skip {%s}' % formattedNotSkipped)
    elif ids:
        games_to_check = [game for game in games_to_check_base if (game.title in ids or str(game.id) in ids)]
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

        downloadslangs = [game_item for game_item in verify_downloads if game_item.lang in valid_langs]
        verify_downloads = downloadslangs
        
        downloadslangs = [game_item for game_item in verify_galaxyDownloads if game_item.lang in valid_langs]
        verify_galaxyDownloads = downloadslangs

        downloadslangs = [game_item for game_item in verify_sharedDownloads if game_item.lang in valid_langs]
        verify_sharedDownloads = downloadslangs
    
    
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
                        info('mismatched file size for %s' % itm_dirpath)
                        bad_size_cnt += 1
                        fail = True
                if not fail and check_md5 and itm.md5 is not None: #MD5 is not reliable if size doesn't match
                    if itm.md5 != hashfile(itm_file):
                        info('mismatched md5 for %s' % itm_dirpath)
                        bad_md5_cnt += 1
                        fail = True
                if not fail and check_zips and itm.name.lower().endswith('.zip'): #Doesn't matter if it's a valid zip if size / MD5 are wrong, it's not the right zip
                    try:
                        if not test_zipfile(itm_file):
                            info('zip test failed for ' % itm_dirpath)
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
                    if check_md5 and itm.md5 is not None:
                        itm.force_change = False #Verified as correct by MD5 match
                        itm.old_updated = itm.updated
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
                info('missing file %s' % itm_dirpath)
                missing_cnt += 1
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
    info('have items.......... %d' % (item_count - missing_cnt - del_file_cnt - clean_file_cnt))
    info('skipped items....... %d' % skip_cnt)
    info('missing items....... %d' % (missing_cnt + del_file_cnt + clean_file_cnt))
    if check_md5:
        info('md5 mismatches...... %d' % bad_md5_cnt)
    if check_filesize:
        info('size mismatches..... %d' % bad_size_cnt)
    if check_zips:
        info('zipfile failures.... %d' % bad_zip_cnt)
    if delete_on_fail:
        info('deleted items....... %d' % del_file_cnt)
    if clean_on_fail:
        info('cleaned items....... %d' % clean_file_cnt)
        
def cmd_trash(cleandir,installers,images,dryrun):
    downloading_root_dir = os.path.join(cleandir, ORPHAN_DIR_NAME)
    for dir in os.listdir(downloading_root_dir):
        testdir= os.path.join(downloading_root_dir,dir)
        if os.path.isdir(testdir):
            if installers:
                contents = os.listdir(testdir)
                deletecontents = [x for x in contents if (len(x.rsplit(os.extsep,1)) > 1 and (os.extsep + x.rsplit(os.extsep,1)[1]) in INSTALLERS_EXT)]
                for content in deletecontents:
                    contentpath = os.path.join(testdir,content)
                    if (not dryrun):
                        os.remove(contentpath)
                    info("Deleting " + contentpath )
            if images:
                images_folder = os.path.join(testdir,IMAGES_DIR_NAME)
                if os.path.isdir(images_folder):
                    if (not dryrun):
                        shutil.rmtree(images_folder)
                    info("Deleting " + images_folder )
            if not ( installers or images):
                try:
                    if (not dryrun):
                        shutil.rmtree(testdir)
                    info("Deleting " + testdir)
                except Exception:
                    error("Failed to delete directory: " + testdir)
            else:
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
                    info("Deleting " + testdir)
                except Exception:
                    error("Failed to delete directory: " + testdir)

    provisional_root_dir = os.path.join(cleandir, DOWNLOADING_DIR_NAME,PROVISIONAL_DIR_NAME)
    for dir in os.listdir(provisional_root_dir):
        testdir= os.path.join(downloading_root_dir,dir)
        if os.path.isdir(testdir):
            try:
                if (not dryrun):
                    shutil.rmtree(testdir)
                info("Deleting " + testdir)
            except Exception:
                error("Failed to delete directory: " + testdir)


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
                            except Exception as e:
                                error(str(e))
                                error("could not move to destination '{}'".format(os.path.join(dest_dir,cur_dir_file)))
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
                                changed_item =  changed_game_items[cur_dir_file]
                                #changed_item.old_updated = changed_item.updated
                                #changed_item.force_change = False
                                #changed_item.prev_verified = False
                            except Exception as e:
                                error(str(e))
                                error("could not move to destination '{}'".format(os.path.join(dest_dir,cur_dir_file)))
                      
    if have_cleaned:
        info('')
        info('total size of newly orphaned files: {}'.format(pretty_size(total_size)))
        if not dryrun:
            info('orphaned items moved to: {}'.format(orphan_root_dir))
            save_manifest(items)
    else:
        info('nothing to clean. nice and tidy!')
        


def get_theme():
    """
    Get the theme to use for the program
    Value is in this program's user settings. If none set, then use PySimpleGUI's global default theme
    :return: The theme
    :rtype: str
    """
    # First get the current global theme for PySimpleGUI to use if none has been set for this program
    try:
        global_theme = sg.theme_global()
    except:
        global_theme = sg.theme()
    # Get theme from user settings for this program.  Use global theme if no entry found
    user_theme = sg.user_settings_get_entry("-theme-", "")
    if user_theme == "":
        user_theme = global_theme
    return user_theme


def get_game_list():
    """
    Generate a list of all games available in the manifest
    TODO: sort by date obtained so it's easier to see newly added games
    """
    print("getting list")
    all_games = load_manifest()
    game_list = []
    for game in all_games:
        game_list.append(game.title)

    return sorted(game_list)


def download_games_gui(selected_games, args, download_path):
    if len(selected_games) == 0:
        sg.popup_error(
            "You did not select any games. You must select at least one game to download"
        )
    else:
        # kick off the download
        sg.popup_non_blocking(
            "Downloading the selected games. Watch the console window for progress...",
            no_titlebar=True,
        )

        if getattr(args, "skipids", None) is None:
            args.skipids = []
        if not getattr(args,"dryrun", False):
            args.dryrun = False
        if getattr(args, "skippreallocation", None) is None:
            args.skippreallocation = False
        if getattr(args, "clean_old_images", None) is None:
            args.clean_old_images = False

        cmd_download(
            download_path,
            args.skipextras,
            args.skipids,
            args.dryrun,
            selected_games,
            args.os,
            args.lang,
            args.skipgalaxy,
            args.skipstandalone,
            args.skipshared,
            args.skipfiles,
            args.covers,
            args.backgrounds,
            args.skippreallocation,
            args.clean_old_images,
            args.downloadlimit,
        )


def cmd_gui(args):
    theme = get_theme()
    if not theme:
        theme = sg.OFFICIAL_PYSIMPLEGUI_THEME
    sg.theme(theme)

    left_col = sg.Col(
        [
            [
                sg.Listbox(
                    values=get_game_list(),
                    select_mode=sg.LISTBOX_SELECT_MODE_MULTIPLE,
                    size=(50, 20),
                    key="-LEFT-",
                )
            ],
            [
                sg.Button(
                    "Update List",
                    enable_events=True,
                    k="Update List",
                    tooltip="Populate Game List",
                )
            ],
        ],
        element_justification="l",
    )

    right_col = [
        [
            sg.Listbox(
                values=[],
                size=(50, 20),
                key="-RIGHT-",
                select_mode=sg.LISTBOX_SELECT_MODE_MULTIPLE,
            )
        ],
        [sg.Button("Download Selected Games", k="-DOWNLOADBUTTON-"), sg.Button("Exit")],
    ]

    choose_folder_at_top = [
        [
            sg.Text("Folder"),
            sg.In(size=(25, 1), enable_events=True, key="-FOLDER-"),
            sg.FolderBrowse(),
        ]
    ]
    # ----- Full layout -----

    layout = [
        [sg.Text("GOG Game Downloader", font="Any 20")],
        [choose_folder_at_top],
        sg.vtop(
            [
                sg.Column([[left_col]], element_justification="l"),
                sg.Column(
                    [[sg.Button(">>", key="-MOVE-")], [sg.Button("<<", key="-REMOVE-")]]
                ),
                sg.Col(right_col, element_justification="c"),
            ]
        ),
    ]

    # --------------------------------- Create Window ---------------------------------

    # All the stuff inside your window.
    try:
        makeGOGSession()

    except (KeyError, AttributeError):
        layout = [
            [sg.Text("You do not have a valid GOG Session. Please Log in")],
            [
                [sg.Text("Enter GOG Email"), sg.InputText()],
                [sg.Text("Enter GOG Password"), sg.InputText()],
                [sg.Button("Login"), sg.Button("Cancel")],
            ],
        ]

    # Create the Window
    window = sg.Window("GOG Downloader", layout, finalize=True, metadata=0)

    # Event Loop to process "events" and get the "values" of the inputs
    while True:
        event, values = window.read()
        print(event)

        # if user closes window or clicks cancel
        if event == sg.WIN_CLOSED or event == "Cancel" or event == "Exit":
            break
        elif event == "Ok":
            print("ok")

        elif event == "Login":
            if len(values[0]) == 0 or len(values[1]) == 0:
                sg.popup_no_titlebar("You must enter both an email & password")
                break
            try:
                cmd_login(values[0], values[1])
                if (
                    sg.popup_ok("Login successful. Please restart the application")
                    == "OK"
                ):
                    exit()
            except Exception as e:
                sg.Print(f"Login failed. Please close and try again: {e}")
        elif event == "Update List":
            sg.popup_non_blocking(
                "Updating the game list. Please watch the console for updates."
            )

            if getattr(args, "skipknown", None) is None:
                args.skipknown = True
            if getattr(args, "updateonly", None) is None:
                args.updateonly = False
            if getattr(args, "full", None) is None:
                args.full = True
            if getattr(args, "ids", None) is None:
                args.ids = []
            if getattr(args, "skipids", None) is None:
                args.skipids = []   
            if getattr(args, "skiphidden", None) is None:
                args.skiphidden = False
            if getattr(args, "installers", None) is None:
                args.installers = "standalone"
            if getattr(args, "resumemode", None) is None:
                args.resumemode = "noresume"
            if getattr(args, "strictverify", None) is None:
                args.strictverify = False
            if getattr(args, "strictdupe", None) is None:
                args.strictdupe = False
            if getattr(args, "lenientdownloadsupdate", None) is None:
                args.lenientdownloadsupdate = True
            if getattr(args, "strictextrasupdate", None) is None:
                args.strictextrasupdate = False
            if getattr(args, "md5xmls", None) is None:
                args.md5xmls = False
            if getattr(args, "nochangelogs", None) is None:
                args.nochangelogs = True

            cmd_update(
                args.os,
                args.lang,
                args.skipknown,
                args.updateonly,
                not args.full,
                args.ids,
                args.skipids,
                args.skiphidden,
                args.installers,
                args.resumemode,
                args.strictverify,
                args.strictdupe,
                args.lenientdownloadsupdate,
                args.strictextrasupdate,
                args.md5xmls,
                args.nochangelogs,
            )
            if (
                sg.popup_ok(
                    "Game list Updated. You will have to restart the app for it to update on the GUI"
                )
                == "OK"
            ):
                exit()

        elif event == "-DOWNLOADBUTTON-":
            if len(values["-FOLDER-"]) == 0:
                print("Save path not specified. Saving to desktop...")
                if platform.system() == "Windows":
                    download_folder = os.path.join(os.environ["USERPROFILE"], "Desktop")
                else:
                    download_folder = os.path.join(os.path.expanduser("~"), "Desktop")
            else:
                download_folder = Path(values["-FOLDER-"])

            print(f"I will download games to {download_folder}")
            print(f"I will download these games: {window['-RIGHT-'].get_list_values()}")
            download_games_gui(
                window["-RIGHT-"].get_list_values(), args, download_folder
            )

        # Move items to the right list
        elif event == "-MOVE-" and values["-LEFT-"]:
            selected_items = values["-LEFT-"]
            right_items = window["-RIGHT-"].get_list_values()
            # Add selected items to the right listbox
            window["-RIGHT-"].update(values=right_items + list(selected_items))
            # Remove selected items from the left listbox
            left_items = [
                item for item in get_game_list() if item not in selected_items
            ]
            window["-LEFT-"].update(values=left_items)

        # Remove items from the right list
        elif event == "-REMOVE-" and values["-RIGHT-"]:
            selected_items = values["-RIGHT-"]
            right_items = [
                item
                for item in window["-RIGHT-"].get_list_values()
                if item not in selected_items
            ]
            window["-RIGHT-"].update(values=right_items)
            # Add the removed items back to the left listbox
            window["-LEFT-"].update(
                values=window["-LEFT-"].get_list_values() + list(selected_items)
            )

    window.close()


def compress_folders(source_directory):
    """
    Compresses all folders in the given source directory into 7z archives compatible with GameVault.
    Folders starting with '!' are skipped.
    Deletes the folder after successful compression.
    Is designed to compress as much as possible, results in high CPU usage.
    """
    # Change to the source directory
    os.chdir(source_directory)

    # Loop over each item in the directory
    for folder in os.listdir(source_directory):
        folder_path = os.path.join(source_directory, folder)

        # if folder starts with !, then we skip it
        # presumed !orphan or !downloading folders
        if folder.startswith("!"):
            print(f"Skipping folder: {folder}")
            continue

        # Check if it's a directory
        if os.path.isdir(folder_path):
            # Define the output archive name
            archive_name = f"{folder}.7z"

            # Command to compress the folder using 7zip with the given flags
            command = [
                "7z",
                "a",
                "-mx=9",
                "-mfb=64",
                "-md=32m",
                "-ms=on",
                archive_name,
                folder_path,
            ]

            try:
                # Run the command
                subprocess.run(command, check=True)
                print(f"Compressed {folder} into {archive_name}")

                # Delete the folder after successful compression
                shutil.rmtree(folder_path)
                print(f"Deleted folder: {folder}")
            except subprocess.CalledProcessError as e:
                print(f"Failed to compress {folder}: {e}")
            except Exception as e:
                print(f"Failed to delete folder {folder}: {e}")


def cmd_compress(args):
    compress_dir = args.compressdir
    if not os.path.isdir(compress_dir):
        error(f"Error: '{compress_dir}' is not a valid directory.")
        return

    compress_folders(compress_dir)


def update_self():
    #To-Do: add auto-update to main using Last-Modified (repo for rolling, latest release for standard)
    #Add a dev mode which skips auto-updates and a manual update command which can specify rolling/standard
    # Since 302 is not an error can use the standard session handling for this. Rewrite appropriately 
    gitSession = makeGitHubSession()
    #if mode = Standard
    response = gitSession.get(REPO_HOME_URL+NEW_RELEASE_URL,stream="False",timeout=HTTP_TIMEOUT,headers={'If-Modified-Since':'Mon, 16 Jul 2018 08:51:22 GMT'})       
    response.raise_for_status()    
    if response.status_code == 304:
        print("Not Modified")
        sys.exit()
    print(response.headers)    
    jsonResponse = response.json()
    print(response.headers)
    print(jsonResponse)
    with codecs.open('updatetest.test', 'w', 'utf-8') as w:
        print(response.headers)
        print(jsonResponse, file=w)    
    response = gitSession.get(jsonResponse['tarball_url'],stream="False",timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    rawResponse = response.content
    print(response.headers)
    with codecs.open('tarballupdatetest.test', 'w', 'utf-8') as w:
        print(response.headers,file=w)
    with open_notrunc('update.tar.gz') as w:    
        w.write(rawResponse)
    
    #if mode = Rolling
    response = gitSession.get(REPO_HOME_URL,stream="False",timeout=HTTP_TIMEOUT)        
    response.raise_for_status()    
    jsonResponse = response.json()
    print(response.headers)
    print(jsonResponse)
    with codecs.open('rollingupdatetest.test', 'w', 'utf-8') as w:
        print(response.headers,file=w)
        print(jsonResponse, file=w)    
    response = gitSession.get(REPO_HOME_URL+"/tarball/master",stream="False",timeout=HTTP_TIMEOUT)        
    response.raise_for_status()    
    rawResponse = response.content
    print(response.headers)
    with codecs.open('tarballrollingupdatetest.test', 'w', 'utf-8') as w:
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
    stime = datetime.datetime.now()

    if args.command == 'login':
        cmd_login(args.username, args.password)
        return  # no need to see time stats
    elif args.command == 'update':
        if not args.os:    
            if args.skipos:
                args.os = [x for x in VALID_OS_TYPES if x not in args.skipos]
            else:
                args.os = DEFAULT_OS_LIST
        if not args.lang:    
            if args.skiplang:
                args.lang = [x for x in VALID_LANG_TYPES if x not in args.skiplang]
            else:
                args.lang = DEFAULT_LANG_LIST
        if (not args.skipknown) and (not args.updateonly) and (not args.standard):         
            if (args.ids):
                args.full = True
        if args.wait > 0.0:
            info('sleeping for %.2fhr...' % args.wait)
            time.sleep(args.wait * 60 * 60)                
        if not args.installers:
            args.installers = "standalone"
        cmd_update(args.os, args.lang, args.skipknown, args.updateonly, not args.full, args.ids, args.skipids,args.skiphidden,args.installers,args.resumemode,args.strictverify,args.strictdupe,args.lenientdownloadsupdate,args.strictextrasupdate,args.md5xmls,args.nochangelogs)
    elif args.command == 'download':
        if (args.id):
            args.ids = [args.id]
        if not args.os:    
            if args.skipos:
                args.os = [x for x in VALID_OS_TYPES if x not in args.skipos]
            else:
                args.os = [x for x in VALID_OS_TYPES]
        if not args.lang:    
            if args.skiplang:
                args.lang = [x for x in VALID_LANG_TYPES if x not in args.skiplang]
            else:
                args.lang = [x for x in VALID_LANG_TYPES]
        if args.skipgames:
            args.skipstandalone = True
            args.skipgalaxy = True
            args.skipshared = True
        if args.wait > 0.0:
            info('sleeping for %.2fhr...' % args.wait)
            time.sleep(args.wait * 60 * 60)
        if args.downloadlimit is not None:
            args.downloadlimit = args.downloadlimit*1024.0*1024.0 #Convert to Bytes
        cmd_download(args.savedir, args.skipextras, args.skipids, args.dryrun, args.ids,args.os,args.lang,args.skipgalaxy,args.skipstandalone,args.skipshared, args.skipfiles,args.covers,args.backgrounds,args.skippreallocation,not args.nocleanimages,args.downloadlimit)
    elif args.command == 'import':
        args.skipgames = False
        args.skipextras = False
        if not args.os:  
            if args.skipos:
                args.os = [x for x in VALID_OS_TYPES if x not in args.skipos]
            else:
                args.os = VALID_OS_TYPES
        if not args.lang:    
            if args.skiplang:
                args.lang = [x for x in VALID_LANG_TYPES if x not in args.skiplang]
            else:
                args.lang = VALID_LANG_TYPES  
        if args.skipgames:
            args.skipstandalone = True
            args.skipgalaxy = True
            args.skipshared = True
        cmd_import(args.src_dir, args.dest_dir,args.os,args.lang,args.skipextras,args.skipids,args.ids,args.skipgalaxy,args.skipstandalone,args.skipshared,False)
    elif args.command == 'verify':
        #Hardcode these as false since extras currently do not have MD5s as such skipgames would give nothing and skipextras would change nothing. The logic path and arguments are present in case this changes, though commented out in the case of arguments)
        if args.clean:
            warn("The -clean option is deprecated, as the default behaviour has been changed to clean files that fail the verification checks. -noclean now exists for leaving files in place. Please update your scripts accordingly. ")
        if (args.id):
            args.ids = [args.id]    
        if not args.os:    
            if args.skipos:
                args.os = [x for x in VALID_OS_TYPES if x not in args.skipos]
            else:
                args.os = VALID_OS_TYPES
        if not args.lang:    
            if args.skiplang:
                args.lang = [x for x in VALID_LANG_TYPES if x not in args.skiplang]
            else:
                args.lang = VALID_LANG_TYPES
        if args.skipgames:
            args.skipstandalone = True
            args.skipgalaxy = True
            args.skipshared = True                
        check_md5 = not args.skipmd5
        check_filesize = not args.skipsize
        check_zips = not args.skipzip
        cmd_verify(args.gamedir, args.skipextras,args.skipids,check_md5, check_filesize, check_zips, args.delete,not args.noclean,args.ids,  args.os, args.lang,args.skipgalaxy,args.skipstandalone,args.skipshared, args.skipfiles, args.forceverify,args.permissivechangeclear)
    elif args.command == 'backup':
        if not args.os:    
            if args.skipos:
                args.os = [x for x in VALID_OS_TYPES if x not in args.skipos]
            else:
                args.os = VALID_OS_TYPES
        if not args.lang:    
            if args.skiplang:
                args.lang = [x for x in VALID_LANG_TYPES if x not in args.skiplang]
            else:
                args.lang = VALID_LANG_TYPES
        if args.skipgames:
            args.skipstandalone = True
            args.skipgalaxy = True
            args.skipshared = True
        cmd_backup(args.src_dir, args.dest_dir,args.skipextras,args.os,args.lang,args.ids,args.skipids,args.skipgalaxy,args.skipstandalone,args.skipshared)
    elif args.command == 'clear_partial_downloads':
        cmd_clear_partial_downloads(args.gamedir,args.dryrun)
    elif args.command == 'clean':
        cmd_clean(args.cleandir, args.dryrun)
    elif args.command == "trash":
        if (args.installersonly):
            args.installers = True
        cmd_trash(args.gamedir,args.installers,args.images,args.dryrun)
    elif args.command == "gui":
        # handle None values 
        if getattr(args, "os", None) is None:
            if getattr(args, "skipos", None) is not None:
                args.os = [x for x in VALID_OS_TYPES if x not in args.skipos]
            else:
                args.os = VALID_OS_TYPES
        if getattr(args, "lang", None) is None:
            if getattr(args, "skiplang", None) is not None:
                args.lang = [x for x in VALID_LANG_TYPES if x not in args.skiplang]
            else:
                args.lang = VALID_LANG_TYPES
        if getattr(args, "skipgames", None) is None:
            args.skipstandalone = False
            args.skipgalaxy = True
            args.skipshared = True
            args.skipextras = True
            args.skipfiles = []
            args.covers = False
            args.backgrounds = False
            args.downloadlimit = None

        cmd_gui(args)
        return
    elif args.command == "compress":
        if getattr(args, "compressdir", None) is None:
            # you must specify a directory to compress
            error("You must specify a directory to compress")
        cmd_compress(args)

    etime = datetime.datetime.now()
    info('--')
    info('total time: %s' % (etime - stime))

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
    try:
        wakelock = Wakelock()
        wakelock.take_wakelock()
        main(process_argv(sys.argv))
        info('exiting...')
    except KeyboardInterrupt:
        info('exiting...')
        sys.exit(1)
    except SystemExit:
        raise
    except Exception:
        log_exception('fatal...')
        sys.exit(1)
    finally:
        wakelock.release_wakelock()

