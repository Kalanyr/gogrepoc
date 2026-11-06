"""0.5.41: a long list of failures is conflated (one line per reason, games with counts), and verify reports a game whose files are
mostly missing in one line instead of one warning per file."""
import hashlib
import logging
import os
import shutil
import tempfile
import unittest
import _bootstrap  # noqa: F401
import gogrepo_delta as g


class Capture(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def errors(self):
        return [r.getMessage() for r in self.records if r.levelname == 'ERROR']

    def warnings(self):
        return [r.getMessage() for r in self.records if r.levelname == 'WARNING']


def captured():
    handler = Capture()
    g.rootLogger.addHandler(handler)
    return handler


class GroupedSummaryTests(unittest.TestCase):
    def setUp(self):
        self.report = g.RunReport()
        self.handler = captured()
        self.addCleanup(g.rootLogger.removeHandler, self.handler)

    def test_many_missing_files_are_grouped_by_game(self):
        for game in range(30):
            for n in range(4):
                self.report.fail('game%02d/file%d.zip' % (game, n), 'missing')        # 120 failures, 30 games
        self.report.log()
        errors = self.handler.errors()
        self.assertIn('   FAILED: 120', errors)
        self.assertIn('      missing: 120 files in 30 games', errors)
        self.assertFalse(any(e.startswith('      game00/file0') for e in errors), 'no per-file lines in the grouped summary')
        self.assertTrue(any('game00 (4)' in e for e in errors))
        self.assertTrue(len(errors) < 15, errors)

    def test_the_games_listed_are_capped(self):
        for game in range(g.RunReport.MAX_LISTED_FAILURES + 5):
            self.report.fail('game%02d/a.zip' % game, 'missing')
            self.report.fail('game%02d/b.zip' % game, 'missing')
        self.report.log()
        self.assertTrue(any('and 5 more games' in e for e in self.handler.errors()))

    def test_different_reasons_get_their_own_line(self):
        for game in range(30):
            self.report.fail('g%d/a.zip' % game, 'missing')
        for game in range(30, 45):
            self.report.fail('g%d/a.zip' % game, 'wrong checksum (md5)')
        self.report.log()
        errors = self.handler.errors()
        self.assertIn('      missing: 30 files in 30 games', errors)
        self.assertIn('      wrong checksum (md5): 15 files in 15 games', errors)

    def test_windows_separators_are_grouped_too(self):
        for n in range(50):
            self.report.fail('game\\file%d.zip' % n, 'missing')
        self.report.log()
        self.assertIn('      missing: 50 files in 1 game', self.handler.errors())

    def test_a_short_list_still_names_every_file(self):
        self.report.fail('game/a.exe', 'wrong checksum')
        self.report.fail('game/b.exe', 'missing')
        self.report.log()
        errors = self.handler.errors()
        self.assertIn('      game/a.exe: wrong checksum', errors)
        self.assertIn('      game/b.exe: missing', errors)

    def test_failures_without_a_folder_keep_the_old_cut_off(self):
        for i in range(45):
            self.report.fail('file%d' % i, 'x')
        self.report.log()
        errors = self.handler.errors()
        self.assertEqual(g.RunReport.MAX_LISTED_FAILURES, len([e for e in errors if e.startswith('      file')]))
        self.assertTrue(any('and 5 more' in e for e in errors))


class VerifyMissingFilesTests(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        g.run_report.reset()
        self.handler = captured()
        self.addCleanup(g.rootLogger.removeHandler, self.handler)

    def library(self, files_per_game):
        games = []
        for gid, count in enumerate(files_per_game, 1):
            entries = []
            for n in range(count):
                name = 'f%d.zip' % n
                data = b'x' * 10
                entries.append(g.AttrDict(name=name, desc=name, lang='English', os_type='windows', size=len(data), md5=hashlib.md5(data).hexdigest(),
                                          href='http://x/' + name, version='1', updated='2020', old_updated='2020', prev_verified=False,
                                          force_change=False, unreleased=False, md5_exempt=False, old_name=None, gog_data=g.AttrDict()))
            games.append(g.AttrDict(id=gid, title='game%d' % gid, folder_name='game%d' % gid, long_title='game%d' % gid, genre='', store_url='/g',
                                    rating=0, release_timestamp=0, changelog='', has_updates=False, serial='', bg_url='', image_url='',
                                    downloads=entries, galaxyDownloads=[], sharedDownloads=[], extras=[]))
        g.save_manifest(games)

    def verify(self):
        g.cmd_verify(self.dir, False, [], True, True, False, False, False, [], ['windows'], ['en'], False, False, False, [], False, False, False, 0,
                     use_blake3=False)

    def test_a_game_with_many_missing_files_gets_one_line(self):
        self.library([6])
        self.verify()
        warnings = [w for w in self.handler.warnings() if 'missing' in w]
        self.assertEqual(['game1: 6 of 6 files missing'], warnings)
        self.assertEqual(6, len(g.run_report.failures))                      # every file still counts as a failure

    def test_a_few_missing_files_are_still_named(self):
        self.library([2])
        self.verify()
        expected = ['missing file ' + os.path.join('game1', name) for name in ('f0.zip', 'f1.zip')]       # the path uses the separator of the system
        self.assertEqual(expected, [w for w in self.handler.warnings() if 'missing' in w])

    def test_the_names_are_kept_at_debug_level(self):
        self.addCleanup(g.rootLogger.setLevel, g.rootLogger.level)       # main() sets INFO unless -debug; other tests may have run it
        g.rootLogger.setLevel(logging.DEBUG)
        self.library([5])
        self.verify()
        debug_lines = [r.getMessage() for r in self.handler.records if r.levelname == 'DEBUG' and r.getMessage().startswith('missing file')]
        self.assertEqual(5, len(debug_lines))


if __name__ == '__main__':
    unittest.main()
