"""The first line of every run in the log file says which version of the program wrote it (and on which Python and system)."""
import contextlib
import io
import logging
import os
import shutil
import tempfile
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g


class LogHeaderTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='loghead_')
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.logfile = os.path.join(self.dir, 'gogrepo.log')
        self.handler = logging.FileHandler(self.logfile, encoding='utf-8')
        self.handler.setFormatter(g.loggingHandler.formatter)                      # the same layout as the real log file
        self.console_stream = io.StringIO()
        self.console = logging.StreamHandler(self.console_stream)
        self.console.setFormatter(g.loggingHandler.formatter)
        patcher = mock.patch.object(g, 'loggingHandler', self.handler)
        patcher.start()
        self.addCleanup(patcher.stop)
        g.rootLogger.addHandler(self.console)
        self.addCleanup(g.rootLogger.removeHandler, self.console)
        self.addCleanup(g.rootLogger.removeHandler, self.handler)
        self.addCleanup(self.handler.close)
        self.config = os.path.join(self.dir, 'gogrepo_delta.cfg')
        patch_env = mock.patch.dict(os.environ, {g.USER_CONFIG_ENV_VAR: self.config})
        patch_env.start()
        self.addCleanup(patch_env.stop)

    def log_lines(self):
        self.handler.flush()
        with open(self.logfile, encoding='utf-8') as reader:
            return reader.read().splitlines()

    def run_argv(self, *argv):
        return g.process_argv(['gogrepo_delta.py'] + list(argv))

    def test_the_first_line_of_a_run_names_the_version(self):
        self.run_argv('update')
        first = self.log_lines()[0]
        self.assertIn('gogrepo_delta.py version %s' % g.__version__, first)
        self.assertIn('INFO', first)

    def test_it_names_the_python_and_the_system_too(self):
        import platform
        self.run_argv('update')
        first = self.log_lines()[0]
        self.assertIn('Python %s' % platform.python_version(), first)
        self.assertIn(platform.platform(), first)

    def test_it_is_the_text_of_version_line(self):
        self.run_argv('update')
        self.assertTrue(self.log_lines()[0].endswith(g.version_line()))

    def test_it_comes_before_everything_else_the_run_logs(self):
        with open(self.config, 'w', encoding='utf-8') as w:
            w.write('[update]\nwait = 2\nunknown_option = 1\n')
        self.run_argv('update')
        lines = self.log_lines()
        self.assertIn('version', lines[0])
        self.assertTrue(any('defaults from the config file' in l for l in lines[1:]))     # the config notes follow it
        self.assertTrue(any("no option 'unknown_option'" in l for l in lines[1:]))

    def test_every_run_writes_its_own_line(self):
        self.run_argv('update')
        self.run_argv('verify')
        self.assertEqual(sum(1 for l in self.log_lines() if 'gogrepo_delta.py version' in l), 2)

    def test_the_console_is_not_bothered_with_it(self):
        self.run_argv('update')
        self.assertNotIn('gogrepo_delta.py version', self.console_stream.getvalue())

    def test_a_list_keeps_its_output_clean(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.run_argv('list')
        self.assertNotIn('version', out.getvalue())

    def test_with_nolog_nothing_is_written(self):
        self.run_argv('update', '-nolog')
        self.assertEqual(self.log_lines(), [])

    def test_help_and_version_options_write_nothing_to_the_log(self):
        for argv in (['--version'], ['update', '-h']):
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                self.run_argv(*argv)
        self.assertEqual(self.log_lines(), [])

    def test_the_line_is_in_the_same_layout_as_the_other_lines(self):
        self.run_argv('update')
        g.info('another line')
        first, second = self.log_lines()[:2]
        self.assertRegex(first, r'^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d \| INFO +\| gogrepo_delta\.py version ')
        self.assertEqual(first.split(' | ')[:2][1], second.split(' | ')[1])               # the same level column


if __name__ == '__main__':
    unittest.main()
