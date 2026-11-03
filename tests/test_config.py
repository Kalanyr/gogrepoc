"""The config file gogrepo_delta.cfg: [settings], defaults for command-line flags, and creating the file.

The script finds its config file through the environment variable GOGREPO_DELTA_CONFIG (the test bootstrap points it
at an empty temporary folder, so a real config file next to the script never changes a test). Every test here writes its
own file and points the variable at it."""
import configparser
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g

ENV = g.USER_CONFIG_ENV_VAR
MINIMAL = {'login': [], 'update': [], 'download': [], 'import': ['src', 'dst'], 'backup': ['src', 'dst'], 'verify': [],
           'export': [], 'clean': ['dir'], 'clear_partial_downloads': ['dir'], 'trash': ['dir'], 'diagnostics': [], 'list': []}

RUNNER = ("import runpy, sys, types\n"
          "for name in ('html5lib', 'psutil'):\n"
          "    try:\n        __import__(name)\n    except ImportError:\n        sys.modules[name] = types.ModuleType(name)\n"
          "script = sys.argv[1]; sys.argv = [script] + sys.argv[2:]\n"
          "runpy.run_path(script, run_name='__main__')\n")
IMPORTER = ("import sys, types\n"
            "for name in ('html5lib', 'psutil'):\n"
            "    try:\n        __import__(name)\n    except ImportError:\n        sys.modules[name] = types.ModuleType(name)\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import gogrepo_delta as g, inspect\n")
SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(SCRIPT_DIR, 'gogrepo_delta.py')


class ConfigTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='cfgtest_')
        self.addCleanup(__import__('shutil').rmtree, self.dir, True)
        self.path = os.path.join(self.dir, 'gogrepo_delta.cfg')
        patcher = mock.patch.dict(os.environ, {ENV: self.path})
        patcher.start()
        self.addCleanup(patcher.stop)

    def write(self, text, encoding='utf-8'):
        with open(self.path, 'w', encoding=encoding, newline='') as w:
            w.write(text)

    def read(self, path=None):
        with open(path or self.path, encoding='utf-8') as reader:
            return reader.read()

    def parse(self, *argv):
        return g.process_argv(['gogrepo_delta.py'] + list(argv) + ['-nolog'])

    def parse_logged(self, *argv):
        with self.assertLogs('gogrepoc', level='DEBUG') as logs:
            args = self.parse(*argv)
            g.info('end of test')
        return args, '\n'.join(logs.output)

    def fails(self, *argv):
        """Parse and expect the program to stop; returns what it logged and printed."""
        err = io.StringIO()
        with self.assertLogs('gogrepoc', level='ERROR') as logs, contextlib.redirect_stderr(err), \
                self.assertRaises(SystemExit) as stop:
            self.parse(*argv)
        self.assertNotEqual(stop.exception.code, 0)
        return '\n'.join(logs.output) + err.getvalue()


# --- identity ------------------------------------------------------------------------------------------------------

CHANGELOG = os.path.join(SCRIPT_DIR, 'CHANGELOG.md')


def changelog_headings():
    """The headings of the entries in CHANGELOG.md, in the order in which they appear: (number, text of the heading)."""
    import re
    with open(CHANGELOG, encoding='utf-8') as reader:
        text = reader.read()
    return [(int(a or b), line) for line in text.splitlines()
            for a, b in re.findall(r'^## (?:0\.5\.(\d+)|Entry (\d+)) - ', line)]


class IdentityTests(unittest.TestCase):
    def test_name_and_version(self):
        self.assertEqual(g.__appname__, 'gogrepo_delta.py')
        self.assertEqual(g.USER_AGENT, 'GOGRepoDelta/' + g.__version__)

    def test_the_patch_number_of_the_version_is_the_number_of_the_newest_changelog_entry(self):
        # the rule: every new entry in CHANGELOG.md raises the version, so that 0.5.N matches entry N
        numbers = [n for n, heading in changelog_headings()]
        self.assertEqual(numbers, list(range(len(numbers), 0, -1)), 'the entries must be numbered without gaps, newest first')
        self.assertEqual(g.__version__, '0.5.%d' % numbers[0])

    def test_entries_from_24_on_are_headed_with_their_version_the_older_ones_are_not(self):
        import re
        for number, heading in changelog_headings():
            if number >= 24:
                self.assertTrue(heading.startswith('## 0.5.%d - ' % number), heading)
            else:
                self.assertTrue(heading.startswith('## Entry %d - ' % number), heading)
            if number >= 25:                                        # from 25 on every entry is dated dd.mm.yyyy
                self.assertRegex(heading, r'^## 0\.5\.%d - \d\d\.\d\d\.\d{4} - \S' % number)

    def test_the_known_issues_and_the_version_rule_are_in_the_changelog(self):
        with open(CHANGELOG, encoding='utf-8') as reader:
            text = reader.read()
        self.assertIn('## Known issues (not fixed yet)', text)
        self.assertIn('## How the version works', text)
        self.assertLess(text.index('## Known issues'), text.index('## 0.5.%d' % int(g.__version__.split('.')[-1])))   # before the entries

    def test_the_notes_are_no_longer_in_the_script_which_points_to_the_changelog(self):
        import re
        with open(SCRIPT, encoding='utf-8') as reader:
            text = reader.read()
        header = text.split('\nimport ')[0]
        self.assertIn('CHANGELOG.md', header)
        self.assertEqual(re.findall(r'^# \d+\. ', header, flags=re.M), [])
        self.assertNotIn('REFACTORING NOTES', header)
        self.assertLess(header.count('\n'), 40)                     # a short header, not a book

    def test_version_option_shows_them(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            g.process_argv(['gogrepo_delta.py', '--version'])
        self.assertIn('gogrepo_delta.py (version %s)' % g.__version__, out.getvalue())

    def test_data_files_and_log_keep_their_names(self):
        self.assertEqual((g.MANIFEST_FILENAME, g.TOKEN_FILENAME, g.RESUME_MANIFEST_FILENAME, g.CONFIG_FILENAME),
                         ('gog-manifest.dat', 'gog-token.dat', 'gog-resume-manifest.dat', 'gog-config.dat'))
        self.assertEqual(os.path.basename(g.loggingHandler.baseFilename), 'gogrepo.log')


# --- [settings] ----------------------------------------------------------------------------------------------------

class SettingParsingTests(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(g.parse_setting('http_retry_count', ' 7 '), 7)
        self.assertEqual(g.parse_setting('http_timeout', '30'), 30)
        self.assertEqual(g.parse_setting('http_timeout', '2.5'), 2.5)
        self.assertEqual(g.parse_setting('file_replace_delay', '0'), 0)

    def test_whole_number_settings_refuse_decimals_and_words(self):
        for text in ('2.5', 'four', '1e3', '0x10'):
            with self.assertRaises(ValueError, msg=text):
                g.parse_setting('download_threads', text)

    def test_limits(self):
        for key, bad in (('download_threads', '0'), ('log_max_mb', '0'), ('http_timeout', '0'), ('http_retry_count', '-1'),
                         ('download_chunk_size', '0'), ('progress_interval', '0'), ('log_backups', '-1')):
            with self.assertRaises(ValueError, msg=key):
                g.parse_setting(key, bad)
        self.assertEqual(g.parse_setting('log_backups', '0'), 0)

    def test_numbers_that_are_not_numbers(self):
        for text in ('nan', 'inf', '-inf', ''):
            with self.assertRaises(ValueError, msg=text):
                g.parse_setting('http_timeout', text)

    def test_http_codes(self):
        self.assertEqual(g.parse_setting('http_no_retry_codes', '404, 403,410'), (404, 403, 410))
        self.assertEqual(g.parse_setting('http_no_retry_codes', '404\n410'), (404, 410))
        for bad in ('abc', '99', '600', '404, x'):
            with self.assertRaises(ValueError, msg=bad):
                g.parse_setting('http_no_retry_codes', bad)

    def test_every_setting_default_passes_its_own_checks(self):
        for key, kind, default, minimum in g.SETTINGS:
            self.assertEqual(g.parse_setting(key, g.format_setting(kind, default)), default, key)


class SettingLoadingTests(ConfigTestCase):
    def test_no_file_gives_the_built_in_defaults(self):
        values, problems = g.load_settings(g.read_user_config())
        self.assertEqual(values, dict((s[0], s[2]) for s in g.SETTINGS))
        self.assertEqual(problems, [])

    def test_the_old_hardcoded_values_are_the_defaults(self):
        # what the script used before the config file existed
        d = dict((s[0], s[2]) for s in g.SETTINGS)
        self.assertEqual((d['log_max_mb'], d['log_backups'], d['http_retry_count'], d['http_retry_delay'], d['http_timeout']),
                         (180, 9, 4, 5, 60))
        self.assertEqual((d['download_chunk_size'], d['download_threads'], d['resume_save_threshold']), (65536, 4, 50))
        self.assertEqual((d['summary_max_items'], d['max_listed_failures'], d['http_no_retry_codes']), (15, 40, (404, 403)))
        self.assertEqual((d['file_replace_attempts'], d['file_replace_delay'], d['progress_interval']), (5, 0.2, 1))

    def test_file_values_replace_defaults_and_others_stay(self):
        self.write('[settings]\nhttp_timeout = 20\ndownload_threads = 2\n')
        values, problems = g.load_settings(g.read_user_config())
        self.assertEqual(values['http_timeout'], 20)
        self.assertEqual(values['download_threads'], 2)
        self.assertEqual(values['http_retry_count'], 4)
        self.assertEqual(problems, [])

    def test_empty_value_means_default(self):
        self.write('[settings]\nhttp_timeout =\n')
        self.assertEqual(g.load_settings(g.read_user_config())[0]['http_timeout'], 60)

    def test_unknown_setting_is_reported_not_fatal(self):
        self.write('[settings]\nhttp_timeuot = 20\n')
        values, problems = g.load_settings(g.read_user_config())
        self.assertEqual(values['http_timeout'], 60)
        self.assertEqual(len(problems), 1)
        self.assertIn('http_timeuot', problems[0])

    def test_bad_value_names_file_section_key_and_reason(self):
        self.write('[settings]\ndownload_threads = lots\n')
        with self.assertRaises(g.ConfigError) as caught:
            g.load_settings(g.read_user_config())
        message = str(caught.exception)
        for part in (self.path, '[settings]', 'download_threads', 'lots', 'whole number'):
            self.assertIn(part, message)

    def test_unreadable_file_content_is_a_config_error(self):
        for text in ('this is not an ini file', '[settings]\nno equals sign here\n', '[settings]\na = 1\n[settings]\n'):
            self.write(text)
            with self.assertRaises(g.ConfigError, msg=text):
                g.read_user_config()
        self.write('[settings]\nhttp_timeout = \xff\xfe'.encode('latin-1').decode('latin-1'), encoding='latin-1')
        with self.assertRaises(g.ConfigError):
            g.read_user_config()

    def test_file_with_a_byte_order_mark_is_read(self):
        self.write('\ufeff[settings]\nhttp_timeout = 33\n')
        self.assertEqual(g.load_settings(g.read_user_config())[0]['http_timeout'], 33)

    def test_keys_are_not_case_sensitive(self):
        self.write('[settings]\nHTTP_Timeout = 33\n')
        self.assertEqual(g.load_settings(g.read_user_config())[0]['http_timeout'], 33)


class SettingsReachTheProgramTests(ConfigTestCase):
    """The settings are read when the module is loaded, so these start a fresh python."""

    def run_python(self, code, config_text=None):
        if config_text is not None:
            self.write(config_text)
        return subprocess.run([sys.executable, '-c', IMPORTER + code, SCRIPT_DIR], capture_output=True, text=True, timeout=60,
                              env=dict(os.environ, **{ENV: self.path}), cwd=self.dir, stdin=subprocess.DEVNULL)

    def test_every_setting_is_used_by_its_constant(self):
        cfg = ('[settings]\nlog_max_mb = 7\nlog_backups = 2\nhttp_retry_count = 1\nhttp_retry_delay = 3\nhttp_timeout = 11\n'
               'http_no_retry_codes = 404, 410\ndownload_chunk_size = 2048\ndownload_threads = 3\nprogress_interval = 0.5\n'
               'resume_save_threshold = 9\nsummary_max_items = 4\nmax_listed_failures = 6\nfile_replace_attempts = 2\n'
               'file_replace_delay = 0.01\n')
        code = ("print([g.LOG_MAX_MB, g.LOG_BACKUPS, g.loggingHandler.maxBytes, g.loggingHandler.backupCount, g.HTTP_RETRY_COUNT,"
                " g.HTTP_RETRY_DELAY, g.HTTP_TIMEOUT, g.HTTP_PERM_ERRORCODES, g.DOWNLOAD_CHUNK_SIZE, g.HTTP_GAME_DOWNLOADER_THREADS,"
                " g.DOWNLOAD_PROGRESS_INTERVAL, g.RESUME_SAVE_THRESHOLD, g.SUMMARY_MAX_ITEMS, g.run_report.MAX_LISTED_FAILURES,"
                " inspect.signature(g.request).parameters['retries'].default,"
                " inspect.signature(g.request_head).parameters['retries'].default,"
                " inspect.signature(g.renew_token).parameters['retries'].default,"
                " inspect.signature(g._replace_file).parameters['attempts'].default,"
                " inspect.signature(g._replace_file).parameters['delay'].default])")
        result = self.run_python(code, cfg)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(),
                         str([7, 2, 7 * 1024 * 1024, 2, 1, 3, 11, (404, 410), 2048, 3, 0.5, 9, 4, 6, 1, 1, 1, 2, 0.01]))

    def test_without_a_file_the_constants_are_the_old_ones(self):
        code = ("print([g.LOG_MAX_MB, g.LOG_BACKUPS, g.HTTP_RETRY_COUNT, g.HTTP_RETRY_DELAY, g.HTTP_TIMEOUT,"
                " g.HTTP_PERM_ERRORCODES, g.DOWNLOAD_CHUNK_SIZE, g.HTTP_GAME_DOWNLOADER_THREADS, g.RESUME_SAVE_THRESHOLD,"
                " g.SUMMARY_MAX_ITEMS, g.run_report.MAX_LISTED_FAILURES])")
        result = self.run_python(code)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str([180, 9, 4, 5, 60, (404, 403), 65536, 4, 50, 15, 40]))
        self.assertFalse(os.path.exists(self.path), 'importing must not create the file; only running the script does')

    def test_a_bad_setting_stops_the_program_with_a_clear_message(self):
        result = self.run_python('print("started")', '[settings]\nhttp_timeout = soon\n')
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('started', result.stdout)
        self.assertIn('http_timeout = soon', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_an_unknown_setting_is_a_warning_in_the_output(self):
        result = self.run_python('print("started")', '[settings]\nhttp_timeuot = 5\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("no setting 'http_timeuot'", result.stdout)

    def test_the_progress_loop_uses_the_interval(self):
        with open(SCRIPT, encoding='utf-8') as reader:
            self.assertIn('time.sleep(DOWNLOAD_PROGRESS_INTERVAL)', reader.read())


# --- flag defaults -------------------------------------------------------------------------------------------------

class NoFileTests(ConfigTestCase):
    def test_without_a_config_file_nothing_changes(self):
        self.assertFalse(os.path.exists(self.path))
        args = self.parse('update')
        self.assertEqual((args.os, args.lang, args.wait, args.resumemode, args.nolog, args.debug), ([], [], 0.0, 'resume', True, False))
        self.assertFalse(os.path.exists(self.path), 'process_argv only reads; the file is made when the script is started')

    def test_a_file_with_only_comments_or_settings_changes_no_flag(self):
        base = vars(self.parse('update'))
        for text in ('', '; nothing here\n', '[settings]\nhttp_timeout = 30\n'):
            self.write(text)
            self.assertEqual(vars(self.parse('update')), base, repr(text))


class FlagDefaultTests(ConfigTestCase):
    def test_switch_is_set_by_true_and_yes_and_on_and_1(self):
        for word in ('true', 'True', 'yes', 'on', '1'):
            self.write('[download]\ndryrun = %s\n' % word)
            self.assertTrue(self.parse('download').dryrun, word)

    def test_switch_set_to_false_or_empty_does_nothing(self):
        for word in ('false', 'no', 'off', '0', ''):
            self.write('[download]\ndryrun = %s\n' % word)
            self.assertFalse(self.parse('download').dryrun, word)

    def test_a_switch_with_a_wrong_word_stops_with_a_message(self):
        self.write('[download]\ndryrun = maybe\n')
        message = self.fails('download')
        for part in (self.path, '[download]', 'dryrun', 'maybe'):
            self.assertIn(part, message)

    def test_switch_that_turns_a_default_off_means_the_same_as_typing_it(self):
        # -lenientdownloadsupdate normally gives False; the config entry "true" is the same as typing the flag
        self.assertTrue(self.parse('update').lenientdownloadsupdate)
        self.write('[update]\nlenientdownloadsupdate = true\n')
        self.assertFalse(self.parse('update').lenientdownloadsupdate)
        self.assertFalse(self.parse('update', '-lenientdownloadsupdate').lenientdownloadsupdate)

    def test_lists_split_on_commas_and_keep_spaces_inside_entries(self):
        self.write('[update]\nos = linux, windows\nids = The Witcher 2, 1207658924\n')
        args = self.parse('update')
        self.assertEqual(args.os, ['linux', 'windows'])
        self.assertEqual(args.ids, ['The Witcher 2', '1207658924'])

    def test_lists_can_be_written_one_per_line(self):
        self.write('[download]\nskipfiles =\n    *.zip\n    readme*\n')
        self.assertEqual(self.parse('download').skipfiles, ['*.zip', 'readme*'])

    def test_percent_and_hash_in_values_are_kept_as_typed(self):
        self.write('[update]\nids = 100% Orange Juice, Game #1\n')
        self.assertEqual(self.parse('update').ids, ['100% Orange Juice', 'Game #1'])

    def test_choices_numbers_and_text(self):
        self.write('[update]\nresumemode = noresume\nwait = 1.5\ninstallers = both\n[export]\noutput = lib.csv\ndelimiter = ;\n')
        args = self.parse('update')
        self.assertEqual((args.resumemode, args.wait, args.installers), ('noresume', 1.5, 'both'))
        args = self.parse('export')
        self.assertEqual((args.output, args.delimiter), ('lib.csv', ';'))

    def test_wrong_choice_and_wrong_number_stop_with_a_message(self):
        self.write('[update]\nresumemode = sometimes\n')
        self.assertIn('not one of: noresume, resume, onlyresume', self.fails('update'))
        self.write('[update]\nwait = soon\n')
        self.assertIn('wait = soon', self.fails('update'))

    def test_command_line_beats_the_config_file(self):
        self.write('[update]\nresumemode = noresume\nwait = 1.5\n[download]\ndryrun = true\n')
        args = self.parse('update', '-resumemode', 'onlyresume', '-wait', '0')
        self.assertEqual((args.resumemode, args.wait), ('onlyresume', 0.0))

    def test_command_line_list_replaces_the_config_list_it_is_not_added_to_it(self):
        self.write('[update]\nos = linux\nlang = de\n')
        args = self.parse('update', '-os', 'windows', '-lang', 'en')
        self.assertEqual((args.os, args.lang), (['windows'], ['en']))

    def test_a_flag_typed_switches_off_the_config_entry_of_the_flag_it_excludes(self):
        self.write('[update]\nos = linux\nlang = de\n')
        args = self.parse('update', '-skipos', 'windows')
        self.assertEqual((args.os, args.skipos, args.lang), ([], ['windows'], ['de']))
        args = self.parse('update', '-skiplang', 'fr')
        self.assertEqual((args.lang, args.skiplang, args.os), ([], ['fr'], ['linux']))

    def test_the_same_works_when_the_flag_is_typed_abbreviated_or_with_two_dashes(self):
        self.write('[update]\nos = linux\n')
        for spelling in ('-skipo', '--skipos'):
            args = self.parse('update', spelling, 'windows')
            self.assertEqual((args.os, args.skipos), ([], ['windows']), spelling)

    def test_two_entries_that_exclude_each_other_stop_with_a_message(self):
        self.write('[update]\nos = linux\nskipos = windows\n')
        message = self.fails('update')
        self.assertIn('cannot be used together', message)
        self.assertIn('os and skipos', message)

    def test_exclusive_entry_is_fine_when_the_command_line_decides(self):
        self.write('[update]\nos = linux\nskipos = windows\n')
        self.assertEqual(self.parse('update', '-os', 'mac').os, ['mac'])

    def test_each_command_reads_only_its_own_section(self):
        self.write('[download]\ndryrun = true\nwait = 2\n[verify]\nskipmd5 = true\n')
        self.assertFalse(hasattr(self.parse('verify'), 'dryrun'))
        self.assertTrue(self.parse('verify').skipmd5)
        self.assertEqual(self.parse('download').wait, 2.0)
        self.assertEqual(self.parse('update').wait, 0.0)

    def test_deprecated_and_odd_flags_work_too(self):
        self.write('[download]\nid = Some Game\n[update]\nwait = 0.25\n')
        self.assertEqual(self.parse('download').id, 'Some Game')


class CommonSectionTests(ConfigTestCase):
    def test_common_applies_to_every_command(self):
        self.write('[common]\ndebug = true\nmanifestformat = legacy\n')
        for command, extra in MINIMAL.items():
            args = g.process_argv(['gogrepo_delta.py', command] + extra + ['-nolog'])
            self.assertTrue(args.debug, command)
            self.assertEqual(args.manifestformat, 'legacy', command)

    def test_nolog_can_be_set_in_the_file(self):
        self.write('[common]\nnolog = true\n')
        added = []
        with mock.patch.object(g.rootLogger, 'addHandler', added.append):
            args = g.process_argv(['gogrepo_delta.py', 'update'])
        self.assertTrue(args.nolog)
        self.assertNotIn(g.loggingHandler, added)

    def test_command_section_beats_common(self):
        self.write('[common]\nmanifestformat = legacy\n[verify]\nmanifestformat = json\n')
        self.assertEqual(self.parse('verify').manifestformat, 'json')
        self.assertEqual(self.parse('update').manifestformat, 'legacy')

    def test_empty_command_entry_does_not_hide_common(self):
        self.write('[common]\nmanifestformat = legacy\n[verify]\nmanifestformat =\n')
        self.assertEqual(self.parse('verify').manifestformat, 'legacy')

    def test_command_line_beats_common(self):
        self.write('[common]\nmanifestformat = legacy\n')
        self.assertEqual(self.parse('update', '-manifestformat', 'json').manifestformat, 'json')

    def test_common_holds_any_option_and_applies_where_the_command_has_it(self):
        self.write('[common]\ndryrun = true\nwait = 2\n')
        args, log = self.parse_logged('download')
        self.assertTrue(args.dryrun)
        self.assertEqual(args.wait, 2.0)
        for command, extra, has in (('clean', ['dir'], ['dryrun']), ('trash', ['dir'], ['dryrun']), ('update', [], ['wait'])):
            args = g.process_argv(['gogrepo_delta.py', command] + extra + ['-nolog'])
            for name in has:
                self.assertEqual(getattr(args, name), {'dryrun': True, 'wait': 2.0}[name], (command, name))

    def test_commands_that_do_not_have_a_common_option_ignore_it_without_a_warning(self):
        self.write('[common]\ndryrun = true\nwait = 2\nos = linux\n')
        args, log = self.parse_logged('export')
        self.assertFalse(hasattr(args, 'dryrun'))
        self.assertNotIn('has no option', log)
        self.assertNotIn('ignored', log)

    def test_an_option_that_no_command_has_is_reported_in_common(self):
        self.write('[common]\ndryrnu = true\n')
        args, log = self.parse_logged('download')
        self.assertIn("[common] has no option 'dryrnu' (no command has it)", log)


class FolderArgumentTests(ConfigTestCase):
    def test_folder_arguments_can_come_from_the_file(self):
        self.write('[backup]\nsrc_dir = /from\ndest_dir = /to\n[download]\nsavedir = /games\n[verify]\ngamedir = /games\n')
        args = self.parse('backup')
        self.assertEqual((args.src_dir, args.dest_dir), ('/from', '/to'))
        self.assertEqual(self.parse('download').savedir, '/games')
        self.assertEqual(self.parse('verify').gamedir, '/games')

    def test_typed_folders_are_used_left_to_right_and_the_rest_come_from_the_file(self):
        self.write('[backup]\nsrc_dir = /from\ndest_dir = /to\n')
        args = self.parse('backup', '/other')
        self.assertEqual((args.src_dir, args.dest_dir), ('/other', '/to'))
        args = self.parse('backup', '/a', '/b')
        self.assertEqual((args.src_dir, args.dest_dir), ('/a', '/b'))

    def test_typed_folder_beats_the_file_for_optional_arguments(self):
        self.write('[download]\nsavedir = /games\n')
        self.assertEqual(self.parse('download', '/elsewhere').savedir, '/elsewhere')

    def test_required_folder_is_still_required_when_the_file_does_not_give_all_of_them(self):
        # typed folders fill the arguments left to right, so a command needs all of its folders from one place
        for text in ('', '[backup]\nsrc_dir =\n', '[backup]\nsrc_dir = /from\n'):
            self.write(text)
            for typed in ([], ['/x']) if text.endswith('/from\n') else ([],):
                err = io.StringIO()
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
                    self.parse('backup', *typed)
                self.assertIn('required', err.getvalue(), (text, typed))

    def test_login_user_name_and_password_are_never_read_from_the_file(self):
        self.write('[login]\nusername = someone\npassword = secret\nbrowser = true\n')
        args, log = self.parse_logged('login')
        self.assertIsNone(args.username)
        self.assertIsNone(args.password)
        self.assertTrue(args.browser)
        self.assertIn("no option 'password'", log)
        self.assertNotIn('secret', log)


class ProblemReportTests(ConfigTestCase):
    def test_unknown_option_and_unknown_section_are_warnings(self):
        self.write('[update]\nresumemod = noresume\ndryrun = true\n[updat]\nwait = 1\n')
        args, log = self.parse_logged('update')
        self.assertEqual(args.resumemode, 'resume')
        self.assertIn("[update] has no option 'resumemod' for the command update", log)
        self.assertIn("[update] has no option 'dryrun' for the command update", log)
        self.assertIn('[updat] is not a command', log)

    def test_what_the_file_changed_is_logged(self):
        self.write('[update]\nos = linux\nwait = 2\n')
        args, log = self.parse_logged('update')
        self.assertIn('defaults from the config file', log)
        self.assertIn('os=linux', log)
        self.assertIn('wait=2.0', log)

    def test_nothing_is_logged_when_the_file_changes_nothing(self):
        self.write('[update]\nos =\n')
        with self.assertLogs('gogrepoc', level='DEBUG') as logs:
            self.parse('update')
            g.info('end of test')
        self.assertNotIn('defaults from the config file', '\n'.join(logs.output))

    def test_a_broken_file_stops_with_a_message_not_a_traceback(self):
        self.write('[update\nnonsense\n')
        message = self.fails('update')
        self.assertIn('cannot be read', message)
        self.assertIn(self.path, message)

    def test_help_and_version_work_whatever_the_file_holds(self):
        self.write('[update\nbroken\n')
        for argv in (['--help'], ['update', '-h'], ['--version'], ['-v']):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as stop:
                g.process_argv(['gogrepo_delta.py'] + argv)
            self.assertEqual(stop.exception.code, 0, argv)

    def test_help_text_is_the_same_with_and_without_a_file(self):
        def help_of(command):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
                g.process_argv(['gogrepo_delta.py', command, '-h'])
            return out.getvalue()
        before = [help_of(c) for c in ('backup', 'download', 'update')]
        self.write('[backup]\nsrc_dir = /a\ndest_dir = /b\n[download]\nsavedir = /g\n[update]\nos = linux\n')
        self.assertEqual([help_of(c) for c in ('backup', 'download', 'update')], before)

    def test_command_line_errors_are_still_reported_with_a_file_present(self):
        self.write('[update]\nwait = 1\n')
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            self.parse('update', '-nonsense')
        self.assertIn('unrecognized arguments', err.getvalue())

    def test_an_unknown_os_from_the_file_is_refused_like_a_typed_one(self):
        self.write('[update]\nos = amiga\n')
        self.assertIn('amiga', self.fails('update'))


# --- the generated file --------------------------------------------------------------------------------------------

class GeneratedFileTests(ConfigTestCase):
    def text(self):
        return g.default_config_text(g.build_parser()[1])

    def test_it_is_valid_and_has_every_section(self):
        parser = configparser.ConfigParser(interpolation=None, delimiters=('=',))
        parser.read_string(self.text())
        commands = g.build_parser()[1]
        shared = g.shared_options(commands)
        own = [c for c, sub in commands.choices.items() if any(a.dest not in shared for a in g.config_options(sub, c))]
        self.assertEqual(parser.sections(), ['settings', 'common'] + own)
        self.assertNotIn('clear_partial_downloads', own)       # everything it has is in [common]

    def test_every_setting_is_in_it_with_its_default(self):
        parser = configparser.ConfigParser(interpolation=None, delimiters=('=',))
        parser.read_string(self.text())
        for key, kind, default, minimum in g.SETTINGS:
            self.assertEqual(parser.get('settings', key), g.format_setting(kind, default), key)
        self.assertEqual(set(parser.options('settings')), set(g.SETTING_KEYS))

    def test_every_option_of_every_command_is_in_it(self):
        parser = configparser.ConfigParser(interpolation=None, delimiters=('=',))
        parser.read_string(self.text())
        for command, sub in g.build_parser()[1].choices.items():
            wanted = set(a.dest for a in g.config_options(sub, command))
            present = (set(parser.options(command)) if parser.has_section(command) else set()) | set(parser.options('common'))
            self.assertEqual(wanted - present, set(), command)

    def test_password_and_user_name_are_not_in_it(self):
        parser = configparser.ConfigParser(interpolation=None, delimiters=('=',))
        parser.read_string(self.text())
        self.assertEqual(parser.options('login'), ['browser'])

    def test_the_text_has_the_explanations_and_stays_within_100_columns(self):
        text = self.text()
        self.assertIn('operating systems to include', text)
        self.assertIn('Order of precedence', text)
        for line in text.splitlines():
            self.assertLessEqual(len(line), 100, line)

    def test_the_generated_file_changes_nothing(self):
        # with the freshly generated file every command parses exactly as without any file
        plain = dict((c, vars(g.process_argv(['gogrepo_delta.py', c] + e + ['-nolog']))) for c, e in MINIMAL.items())
        self.write(self.text())
        for command, extra in MINIMAL.items():
            args, log = self.parse_logged(command, *extra)
            self.assertEqual(vars(args), plain[command], command)
            self.assertNotIn('defaults from the config file', log, command)
            self.assertNotIn('ignored', log, command)

    def test_the_generated_file_gives_the_old_settings(self):
        self.write(self.text())
        values, problems = g.load_settings(g.read_user_config())
        self.assertEqual(values, dict((s[0], s[2]) for s in g.SETTINGS))
        self.assertEqual(problems, [])


# --- the layout of the generated file: short, grouped, nothing explained twice -----------------------------------------

import re


def parse_layout(text):
    """[(section, [blocks])] where a block is (comment text, [keys]) for a comment with the keys under it, or (None, [keys])
    for keys without a comment of their own. Keys that follow a comment but are not named in it are a block of their own."""
    sections, blocks, comment, keys = [], None, [], []

    def close():
        text = ' '.join(comment) if comment else None
        named = re.findall(r'(?:^|; )([a-z_0-9]+): ', text) if text else []
        if text and sections[-1][0] != 'settings':
            blocks.append((text, keys[:len(named)]))       # the keys the comment names (it comes first, in this order)
            if keys[len(named):]:
                blocks.append((None, keys[len(named):]))   # the keys after them have no comment of their own
        elif keys or text:
            blocks.append((text, list(keys)))
        del keys[:]
        del comment[:]
    for line in text.splitlines():
        if line.startswith('['):
            if blocks is not None:
                close()
            blocks = []
            sections.append((line.strip('[]'), blocks))
        elif blocks is None or not line.strip():
            continue
        elif line.startswith(';'):
            if keys:
                close()
            comment.append(line[1:].strip())
        else:
            keys.append(line.split('=')[0].strip())
    close()
    return sections


class CompactLayoutTests(ConfigTestCase):
    def setUp(self):
        super().setUp()
        self.commands = g.build_parser()[1]
        self.text = g.default_config_text(self.commands)
        self.layout = parse_layout(self.text)

    def test_every_option_of_every_command_has_a_description(self):
        # a new flag must get a line in CONFIG_NOTES (without one the generated file falls back to the shortened help text)
        for command, sub in self.commands.choices.items():
            for action in g.config_options(sub, command):
                self.assertIsNotNone(g._note_for(command, action.dest), '%s: %s' % (command, action.dest))

    def test_no_description_is_left_over_for_an_option_that_does_not_exist(self):
        existing = {}
        for command, sub in self.commands.choices.items():
            for action in g.config_options(sub, command):
                existing.setdefault(action.dest, set()).add(command)
        for number, (commands, members) in enumerate(g.CONFIG_NOTES):
            dests = [d for d, t in members]
            self.assertEqual(len(dests), len(set(dests)), 'note %d names an option twice' % number)
            for dest in dests:
                self.assertIn(dest, existing, 'note %d: %s' % (number, dest))
                for command in commands or ():
                    self.assertIn(command, existing[dest], 'note %d: %s is not an option of %s' % (number, dest, command))
            for command in commands or ():
                self.assertIn(command, self.commands.choices)

    def test_every_setting_is_in_exactly_one_group(self):
        grouped = [key for keys, text in g.SETTING_GROUPS for key in keys]
        self.assertEqual(sorted(grouped), sorted(g.SETTING_KEYS))
        for keys, text in g.SETTING_GROUPS:
            self.assertTrue(text)

    def test_every_settings_group_has_its_comment_above_exactly_its_keys(self):
        settings = [blocks for section, blocks in self.layout if section == 'settings'][0]
        expected = [(' '.join(text.split()), list(keys)) for keys, text in g.SETTING_GROUPS]
        self.assertEqual([(' '.join(c.split()) if c else None, k) for c, k in settings], expected)

    def test_the_file_is_short(self):
        # the first version had 469 lines
        self.assertLessEqual(len(self.text.splitlines()), 260)

    def test_blank_lines_only_separate_sections(self):
        lines = self.text.splitlines()
        for number, line in enumerate(lines):
            if not line.strip():
                self.assertTrue(lines[number + 1].startswith('['), 'blank line before: %r' % lines[number + 1])

    def test_no_comment_is_written_twice(self):
        comments = [c for section, blocks in self.layout for c, keys in blocks if c]
        self.assertEqual(len(comments), len(set(comments)))

    def test_a_comment_names_the_options_that_follow_it(self):
        for section, blocks in self.layout:
            if section == 'settings':
                continue
            for comment, keys in blocks:
                if comment:
                    named = re.findall(r'(?:^|; )([a-z_0-9]+): ', comment)
                    self.assertEqual(named, keys, '[%s] %s' % (section, comment))

    def test_an_option_is_explained_where_it_first_appears_and_not_again(self):
        where = {}
        for section, blocks in self.layout:
            for comment, keys in blocks:
                for key in keys:
                    where.setdefault(key, []).append((section, comment is not None))
        # an option that several commands have is listed once, in [common], with its comment
        self.assertEqual(where['os'], [('common', True)])
        self.assertEqual(self.text.count('operating systems to include'), 1)
        for dest in g.shared_options(self.commands):
            self.assertEqual(len(where[dest]), 1, dest)
            self.assertEqual(where[dest][0][0], 'common', dest)
        # an option that means something else in other commands is listed in each of them, with its own comment
        self.assertEqual(sorted(where['installers']), [('trash', True), ('update', True)])

    def test_an_option_that_means_something_else_in_another_command_is_explained_again(self):
        def comment_of(section, key):
            for name, blocks in self.layout:
                if name == section:
                    for comment, keys in blocks:
                        if key in keys:
                            return comment
        self.assertNotEqual(comment_of('update', 'installers'), comment_of('trash', 'installers'))
        self.assertNotEqual(comment_of('import', 'src_dir'), comment_of('backup', 'src_dir'))
        for section, key in (('update', 'installers'), ('trash', 'installers'), ('import', 'dest_dir'), ('backup', 'dest_dir')):
            self.assertIsNotNone(comment_of(section, key), (section, key))

    def test_options_that_belong_together_are_listed_together_in_every_section(self):
        for section, blocks in self.layout:
            keys = [k for c, ks in blocks for k in ks]
            for group in (('os', 'skipos'), ('lang', 'skiplang'), ('ids', 'skipids'),
                          ('skipgalaxy', 'skipstandalone', 'skipshared', 'skipextras', 'skipgames'), ('skipmd5', 'skipsize', 'skipzip')):
                present = [k for k in group if k in keys]
                if len(present) > 1:
                    first = keys.index(present[0])
                    self.assertEqual(keys[first:first + len(present)], present, (section, group))

    def test_choices_are_shown_when_the_description_does_not_name_them(self):
        self.assertIn('[noresume|resume|onlyresume]', self.text)
        self.assertEqual(self.text.count('[json|legacy]'), 0)        # the description already says json and legacy

    def test_an_option_without_a_note_falls_back_to_its_help_text(self):
        commands = g.build_parser()[1]
        sub = commands.choices['update']
        action = [a for a in sub._actions if a.dest == 'wait'][0]
        with mock.patch.object(g, 'CONFIG_NOTES', []):
            lines = g._section_lines('update', [action], set())
        self.assertEqual(lines[1], 'wait = 0.0')
        self.assertIn('wait this long in hours before starting', lines[0])

    def test_the_old_comment_clutter_is_gone(self):
        for old in ('(default: 180)', '(default: 4)', 'Defaults for the command', 'Program settings.', 'Flags that every command has',
                    'the argument '):
            self.assertNotIn(old, self.text)


# --- options with the same name in several commands are set once, in [common] ---------------------------------------------

class MergedOptionTests(ConfigTestCase):
    COMMANDS_WITH_OS = ('update', 'download', 'import', 'backup', 'verify', 'list')

    def parse_command(self, command, *extra):
        return g.process_argv(['gogrepo_delta.py', command] + MINIMAL[command] + list(extra) + ['-nolog'])

    def test_one_entry_in_common_changes_the_option_for_every_command_that_has_it(self):
        self.write('[common]\nos = linux, windows\nlang = de\n')
        for command in self.COMMANDS_WITH_OS:
            args = self.parse_command(command)
            self.assertEqual(args.os, ['linux', 'windows'], command)
            self.assertEqual(args.lang, ['de'], command)
        self.write('[common]\nskipos = mac\nskiplang = fr\n')
        for command in self.COMMANDS_WITH_OS:
            args = self.parse_command(command)
            self.assertEqual((args.skipos, args.skiplang), (['mac'], ['fr']), command)

    def test_the_example_download_os_and_update_os(self):
        self.write('[common]\nos = linux\n')
        self.assertEqual(self.parse_command('download').os, ['linux'])
        self.assertEqual(self.parse_command('update').os, ['linux'])
        self.assertEqual(self.parse_command('download', '-os', 'mac').os, ['mac'])       # typed: beats the file, is not merged
        self.assertEqual(self.parse_command('update', '-os', 'windows').os, ['windows'])

    def test_a_command_section_overrides_common_for_that_command_only(self):
        self.write('[common]\nos = linux\n[verify]\nos = windows\n')
        self.assertEqual(self.parse_command('verify').os, ['windows'])
        self.assertEqual(self.parse_command('download').os, ['linux'])

    def test_a_section_of_a_command_that_has_everything_in_common_is_still_accepted(self):
        self.write('[common]\ndryrun = false\n[clear_partial_downloads]\ndryrun = true\n')
        args, log = self.parse_logged('clear_partial_downloads', 'dir')
        self.assertTrue(args.dryrun)
        self.assertNotIn('has no option', log)

    def test_an_entry_for_an_excluded_option_in_a_command_section_replaces_the_common_entry(self):
        self.write('[common]\nos = linux\n[verify]\nskipos = mac\n')
        args = self.parse_command('verify')
        self.assertEqual((args.os, args.skipos), ([], ['mac']))
        args = self.parse_command('update')
        self.assertEqual((args.os, args.skipos), (['linux'], []))

    def test_two_excluding_entries_in_common_are_an_error(self):
        self.write('[common]\nos = linux\nskipos = mac\n')
        self.assertIn('cannot be used together', self.fails('update'))

    def test_typing_the_excluding_option_still_switches_off_the_common_entry(self):
        self.write('[common]\nos = linux\n')
        args = self.parse_command('download', '-skipos', 'mac')
        self.assertEqual((args.os, args.skipos), ([], ['mac']))

    def test_a_value_that_does_not_fit_one_command_names_the_command(self):
        # installers is a choice in update and a yes/no switch in trash, which is why it is not in [common] by itself
        self.write('[common]\ninstallers = both\n')
        self.assertEqual(self.parse_command('update').installers, 'both')
        message = self.fails('trash', 'dir')
        for part in ('[common] installers = both', 'not yes or no', 'for the command trash'):
            self.assertIn(part, message)

    def test_shared_options_are_the_ones_with_the_same_name_kind_and_meaning(self):
        shared = g.shared_options(g.build_parser()[1])
        for dest in ('os', 'skipos', 'lang', 'skiplang', 'ids', 'skipids', 'dryrun', 'wait', 'gamedir', 'savedir', 'skipfiles',
                     'nolog', 'debug', 'manifestformat', 'skipextras'):
            self.assertIn(dest, shared, dest)
        self.assertEqual(sorted(shared['os']), sorted(self.COMMANDS_WITH_OS))
        for dest in ('installers', 'src_dir', 'dest_dir', 'browser', 'resumemode', 'output'):   # different meaning, or only one command
            self.assertNotIn(dest, shared, dest)

    def test_a_folder_in_common_serves_every_command_that_takes_it(self):
        self.write('[common]\ngamedir = /games\nsavedir = /library\n')
        self.assertEqual(g.process_argv(['gogrepo_delta.py', 'verify', '-nolog']).gamedir, '/games')
        self.assertEqual(g.process_argv(['gogrepo_delta.py', 'trash', '-nolog']).gamedir, '/games')
        self.assertEqual(g.process_argv(['gogrepo_delta.py', 'clear_partial_downloads', '-nolog']).gamedir, '/games')
        self.assertEqual(g.process_argv(['gogrepo_delta.py', 'download', '-nolog']).savedir, '/library')   # an argument there ...
        self.assertEqual(g.process_argv(['gogrepo_delta.py', 'export', '-nolog']).savedir, '/library')     # ... and an option here


class OptionKindTests(unittest.TestCase):
    """_option_kind decides which options may share one entry. Tested on made-up options, because the real ones
    already differ in other ways."""

    def action(self, *args, **kwargs):
        import argparse
        return argparse.ArgumentParser(prog='x').add_argument(*args, **kwargs)

    def test_options_that_differ_in_what_they_accept_are_different_kinds(self):
        base = self.action('-a', choices=['x', 'y'], default='x')
        self.assertEqual(g._option_kind(base), g._option_kind(self.action('-b', choices=['x', 'y'], default='x')))
        self.assertNotEqual(g._option_kind(base), g._option_kind(self.action('-b', choices=['x', 'z'], default='x')))
        self.assertNotEqual(g._option_kind(self.action('-a', type=float)), g._option_kind(self.action('-b', type=int)))
        self.assertNotEqual(g._option_kind(self.action('-a', default='1')), g._option_kind(self.action('-b', default='2')))

    def test_a_switch_a_list_and_a_value_are_different_kinds(self):
        kinds = [g._option_kind(self.action('-a', action='store_true')), g._option_kind(self.action('-b', action='store_false')),
                 g._option_kind(self.action('-c', nargs='*', default=[])), g._option_kind(self.action('-d'))]
        self.assertEqual(len(set(kinds)), 4)

    def test_how_argparse_stores_a_value_does_not_matter(self):
        self.assertEqual(g._option_kind(self.action('-a', nargs='*', default=[], action='extend')),
                         g._option_kind(self.action('-b', nargs='*', default=[])))

    def test_an_argument_and_an_option_with_the_same_meaning_are_the_same_kind(self):
        self.assertEqual(g._option_kind(self.action('folder', nargs='?', default='.')), g._option_kind(self.action('-folder')))

    def test_a_note_for_the_first_command_that_has_an_option_is_used_in_common(self):
        action = self.action('-x', action='store_true')
        action.dest = 'x'
        notes = [(('b',), (('x', 'text for b'),)), (('a',), (('x', 'text for a'),))]
        with mock.patch.object(g, 'CONFIG_NOTES', notes):
            lines = g._section_lines('common', [action], set(), {'x': 'b'})
            self.assertEqual(lines[0], '; x: text for b')
            lines = g._section_lines('common', [action], set(), {'x': 'a'})
            self.assertEqual(lines[0], '; x: text for a')


class WrittenRulesTests(ConfigTestCase):
    """The remarks at the top of the generated file are true: these tests check the behaviour they describe."""

    def text(self):
        return g.default_config_text(g.build_parser()[1])

    def test_the_header_gives_the_rules(self):
        header = self.text().split('[settings]')[0]
        flat = ' '.join(line.lstrip('; ') for line in header.splitlines())
        for part in ('separate the entries with commas (not with spaces or semicolons)', 'or write one per line',
                     'section names ([common], [update], ...)', 'values of os and lang (windows, linux, mac; en, de, ...) in lower case',
                     'option names may be written in any case'):
            self.assertIn(part, flat)

    def test_lists_are_separated_by_commas_and_by_nothing_else(self):
        self.write('[common]\nos = windows, linux\n')
        self.assertEqual(self.parse('download').os, ['windows', 'linux'])
        for separator in (' ', '; ', ' / '):
            self.write('[common]\nos = windows%slinux\n' % separator)
            self.assertIn('windows%slinux' % separator, self.fails('download'))
        self.write('[common]\nos =\n    windows\n    linux\n')
        self.assertEqual(self.parse('download').os, ['windows', 'linux'])             # one per line works too

    def test_the_values_of_os_and_lang_must_be_lower_case(self):
        for text in ('[common]\nos = Windows\n', '[common]\nos = windows, Linux\n', '[common]\nlang = DE\n', '[common]\nlang = De, en\n'):
            self.write(text)
            self.fails('download')
        self.write('[common]\nos = windows\nlang = de, en\n')
        args = self.parse('download')
        self.assertEqual((args.os, args.lang), (['windows'], ['de', 'en']))

    def test_section_names_must_be_lower_case(self):
        self.write('[COMMON]\nos = linux\n')
        args, log = self.parse_logged('download')
        self.assertEqual(args.os, [])                                                    # not used ...
        self.assertIn('[COMMON] is not a command, ignored', log)                         # ... and the log says so
        self.write('[Download]\ndryrun = true\n')
        args, log = self.parse_logged('download')
        self.assertFalse(args.dryrun)
        self.assertIn('[Download] is not a command, ignored', log)

    def test_option_names_may_be_written_in_any_case(self):
        self.write('[common]\nOS = linux\nDryRun = TRUE\nWAIT = 2\n')
        args = self.parse('download')
        self.assertEqual((args.os, args.dryrun, args.wait), (['linux'], True, 2.0))

    def test_ids_may_be_written_in_any_case_because_names_are_compared_ignoring_case(self):
        self.write('[common]\nids = Beneath A Steel Sky\n')
        self.assertEqual(self.parse('download').ids, ['Beneath A Steel Sky'])           # kept as written; matching ignores the case


class ProjectAddressTests(unittest.TestCase):
    def test_the_project_address_is_the_new_repository(self):
        self.assertEqual(g.__url__.split()[0], 'https://github.com/MarS301/gogrepo_delta')
        self.assertEqual(g.REPO_HOME_URL.strip(), 'https://api.github.com/repos/MarS301/gogrepo_delta')

    def test_the_two_addresses_name_the_same_repository(self):
        self.assertEqual(g.REPO_HOME_URL.strip().split('/repos/')[1], g.__url__.split('github.com/')[1])

    def test_the_help_shows_the_new_address_and_the_credit_stays(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            g.process_argv(['gogrepo_delta.py', '--help'])
        self.assertIn('https://github.com/MarS301/gogrepo_delta', out.getvalue())
        self.assertEqual(g.__author__.split(','), ['eddie3', 'kalanyr', 'MarS301', 'claude.ai'])    # the original authors, then this version's


class EnsureConfigFileTests(ConfigTestCase):
    def ensure(self):
        with self.assertLogs('gogrepoc', level='DEBUG') as logs:
            result = g.ensure_config_file()
            g.info('end of test')
        return result, '\n'.join(logs.output)

    def test_missing_file_is_created(self):
        created, log = self.ensure()
        self.assertTrue(created)
        self.assertTrue(os.path.exists(self.path))
        self.assertIn('created', log)
        self.assertEqual(self.read(), g.default_config_text(g.build_parser()[1]))
        self.assertEqual(os.listdir(self.dir), ['gogrepo_delta.cfg'])      # no temporary file left behind

    def test_existing_file_is_never_touched(self):
        self.write('[settings]\nhttp_timeout = 5\n')
        created, log = self.ensure()
        self.assertFalse(created)
        self.assertEqual(self.read(), '[settings]\nhttp_timeout = 5\n')

    def test_an_empty_existing_file_is_not_replaced_either(self):
        self.write('')
        self.assertFalse(self.ensure()[0])
        self.assertEqual(self.read(), '')

    def test_a_folder_that_cannot_be_written_gives_a_warning_not_a_crash(self):
        os.environ[ENV] = os.path.join(self.dir, 'no', 'such', 'folder', 'x.cfg')
        created, log = self.ensure()
        self.assertFalse(created)
        self.assertIn('could not be written', log)

    def test_created_file_can_be_read_back_as_it_is(self):
        self.ensure()
        self.assertEqual(g.load_settings(g.read_user_config())[1], [])
        self.assertEqual(vars(self.parse('update'))['resumemode'], 'resume')


class RealScriptTests(ConfigTestCase):
    """Start the script itself (so the part under  if __name__ == '__main__'  runs)."""

    def run_script(self, *args):
        return subprocess.run([sys.executable, '-c', RUNNER, SCRIPT] + list(args), capture_output=True, text=True, timeout=120,
                              env=dict(os.environ, PYTHONIOENCODING='utf-8', **{ENV: self.path}), cwd=self.dir, stdin=subprocess.DEVNULL)

    def test_first_run_creates_the_file_and_later_runs_leave_it(self):
        first = self.run_script('--version')
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertTrue(os.path.exists(self.path))
        self.assertIn('created', first.stderr)            # on stderr: stdout may be the list that a command writes and that is piped
        self.assertNotIn('created', first.stdout)
        content = self.read()
        self.assertIn('[settings]', content)
        second = self.run_script('--version')
        self.assertNotIn('created', second.stdout + second.stderr)
        self.assertEqual(self.read(), content)

    def test_edited_file_is_used_by_the_next_run(self):
        self.run_script('--version')
        text = self.read().replace('log_backups = 9', 'log_backups = 3')
        self.write(text)
        result = subprocess.run([sys.executable, '-c', IMPORTER + 'print(g.LOG_BACKUPS)', SCRIPT_DIR], capture_output=True,
                                text=True, env=dict(os.environ, **{ENV: self.path}), cwd=self.dir, stdin=subprocess.DEVNULL)
        self.assertEqual(result.stdout.strip(), '3')

    def test_a_flag_default_from_the_file_reaches_a_real_run(self):
        self.write('[verify]\nskipmd5 = true\nskipsize = true\nskipzip = true\n[common]\nnolog = true\n')
        os.makedirs(os.path.join(self.dir, 'games'))
        result = self.run_script('verify', os.path.join(self.dir, 'games'))
        # no manifest here: what matters is that the run got far enough to take the options from the file
        self.assertIn('defaults from the config file', result.stdout)
        self.assertIn('skipmd5=True', result.stdout)
        self.assertNotIn('Traceback', result.stderr)

    def test_a_bad_entry_exits_with_one_and_a_message(self):
        self.write('[update]\nwait = soon\n')
        result = self.run_script('update')
        self.assertEqual(result.returncode, 1)
        self.assertIn('wait = soon', result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
