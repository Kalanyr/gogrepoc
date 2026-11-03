"""Import gogrepo_delta.py (the single-file script next to this folder) as the module 'gogrepo_delta'.

The script needs requests, html5lib and psutil at import time. If html5lib/psutil are not installed
(for example in a bare CI container) harmless empty stand-ins are used so the pure-logic tests can
still run; none of the code under test touches them."""
import atexit, importlib.util, os, shutil, sys, tempfile, types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The script keeps its data (gog-manifest.dat, gogrepo.log, the config file, ...) in the folder it is started from, and a command that
# saves the manifest writes there. A test must never do that in the folder the tests were started from: that may be the folder of a
# real library, and its manifest would be overwritten. So the whole test run happens in a scratch folder that is removed at the end.
# This is done before the script is imported (it opens gogrepo.log in the current folder when it is loaded).
LAUNCH_DIR = os.getcwd()
SCRATCH_DIR = os.path.realpath(tempfile.mkdtemp(prefix='gogrepo_delta_cwd_'))
os.chdir(SCRATCH_DIR)
atexit.register(shutil.rmtree, SCRATCH_DIR, True)
for _name in ('html5lib', 'psutil'):
    try:
        __import__(_name)
    except ImportError:
        sys.modules[_name] = types.ModuleType(_name)

# The tests must not be influenced by (or write into) a real gogrepo_delta.cfg in the folder they are started from.
# The script looks for its config file at the path in this variable; scripts started by the tests inherit it.
_CONFIG_DIR = tempfile.mkdtemp(prefix='gogrepo_delta_tests_')
os.environ['GOGREPO_DELTA_CONFIG'] = os.path.join(_CONFIG_DIR, 'gogrepo_delta.cfg')

if 'gogrepo_delta' not in sys.modules:
    _spec = importlib.util.spec_from_file_location('gogrepo_delta', os.path.join(ROOT, 'gogrepo_delta.py'))
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules['gogrepo_delta'] = _mod
    _spec.loader.exec_module(_mod)

# The script logs to the console while it runs; that is only noise between test results. Tests that check log
# output (assertLogs, the download rig) attach their own handlers and are not affected.
gogrepoc = sys.modules['gogrepo_delta']   # the name gogrepoc is kept in the tests as a short alias
gogrepoc.rootLogger.removeHandler(gogrepoc.consoleHandler)
gogrepoc.rootLogger.addHandler(__import__('logging').NullHandler())   # no handler would make Python print warnings to stderr

# No test may ever wait for someone to type an answer: the recovery questions are only asked on a terminal, and the tests
# that exercise them pretend to be on one (and to type the answers) explicitly.
gogrepoc._real_stdin_is_interactive = gogrepoc._stdin_is_interactive    # for the tests of the check itself (test_interactive)
gogrepoc._stdin_is_interactive = lambda: False

# Nor may any test ever prompt for a password on the console (token encryption asks for one). Tests that care about the
# prompt patch getpass themselves; every other test silently gets this fixed throw-away password.
gogrepoc.getpass.getpass = lambda prompt='Password: ', stream=None: 'test-password'
