"""End-of-run summary and exit status: 0 when everything worked, 1 when something failed."""
import functools
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest import mock
import _bootstrap  # noqa: F401
import gogrepo_delta as g

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'download_rig'))
import rig  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gogrepo_delta.py')


class RunReportTests(unittest.TestCase):
    def setUp(self):
        self.report = g.RunReport()

    def lines(self, **kw):
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            self.report.log(**kw)
        return logs.records

    def test_counts_add_up_and_sizes_are_summed(self):
        self.report.count('files', 1, 1000)
        self.report.count('files', 2, 24)
        self.report.count('games')
        self.assertEqual(self.report.counts, {'files': [3, 1024], 'games': [1, 0]})

    def test_exit_status_follows_failures(self):
        self.assertEqual(self.report.exit_status(), 0)
        self.report.count('files', 5)
        self.assertEqual(self.report.exit_status(), 0)
        self.report.fail('a.exe', 'broken')
        self.assertEqual(self.report.exit_status(), 1)

    def test_reset_starts_clean_and_names_the_command(self):
        self.report.count('files')
        self.report.fail('x')
        self.report.reset('verify')
        self.assertEqual((self.report.command, self.report.counts, self.report.failures), ('verify', {}, []))

    def test_summary_lists_counts_with_sizes_and_says_when_nothing_failed(self):
        self.report.reset('download')
        self.report.count('files downloaded', 3, 1024 * 1024)
        self.report.count('files already up to date', 40)
        records = self.lines()
        text = '\n'.join(r.getMessage() for r in records)
        self.assertIn('-- summary: download', text)
        self.assertIn('files downloaded:', text)
        self.assertIn('3 (1.00MB)', text)
        self.assertIn('files already up to date:', text)
        self.assertIn('no failures', text)
        self.assertTrue(all(r.levelname == 'INFO' for r in records))

    def test_labels_are_aligned(self):
        self.report.count('a', 1)
        self.report.count('a much longer label', 2)
        numbers = [m for m in (r.getMessage() for r in self.lines()) if m.startswith('   a')]
        self.assertEqual(len(set(m.index(str(c)) for m, c in zip(numbers, (1, 2)))), 1)

    def test_failures_are_listed_as_errors_with_their_reason(self):
        self.report.fail('game/a.exe', 'wrong checksum')
        self.report.fail('game/b.exe')
        records = self.lines()
        errors = [r.getMessage() for r in records if r.levelname == 'ERROR']
        self.assertIn('   FAILED: 2', errors)
        self.assertIn('      game/a.exe: wrong checksum', errors)
        self.assertIn('      game/b.exe', errors)                       # no reason, no colon
        self.assertNotIn('no failures', '\n'.join(r.getMessage() for r in records))

    def test_a_long_failure_list_is_cut_short_but_the_count_is_exact(self):
        for i in range(45):
            self.report.fail('file%d' % i, 'x')
        errors = [r.getMessage() for r in self.lines() if r.levelname == 'ERROR']
        self.assertIn('   FAILED: 45', errors)
        self.assertEqual(len([e for e in errors if e.startswith('      file')]), g.RunReport.MAX_LISTED_FAILURES)
        self.assertTrue(any('and 5 more' in e for e in errors))

    def test_nothing_is_logged_when_there_is_nothing_to_report(self):
        with self.assertNoLogs('gogrepoc', level='INFO'):
            self.report.log()

    def test_an_interrupted_run_is_marked_as_such(self):
        self.report.reset('download')
        self.report.count('files downloaded', 2)
        text = '\n'.join(r.getMessage() for r in self.lines(interrupted=True))
        self.assertIn('interrupted', text)
        self.assertIn('files downloaded:', text)
        self.assertNotIn('no failures', text)


class MainTests(unittest.TestCase):
    def args(self, *argv):
        return g.process_argv(['gogrepo_delta.py'] + list(argv) + ['-nolog'])

    def test_main_returns_one_when_something_failed_and_logs_the_summary_first(self):
        def failing_clean(*a, **k):
            g.run_report.count('files moved to the orphan folder', 1, 10)
            g.run_report.fail('game/junk.txt', 'could not be moved')
        with mock.patch.object(g, 'cmd_clean', failing_clean), self.assertLogs('gogrepoc', level='INFO') as logs:
            status = g.main(self.args('clean', 'somedir'))
        self.assertEqual(status, 1)
        messages = [r.getMessage() for r in logs.records]
        self.assertLess(messages.index('-- summary: clean'), messages.index('--'))     # the summary comes before the total time
        self.assertIn('      game/junk.txt: could not be moved', messages)

    def test_main_returns_zero_otherwise(self):
        with mock.patch.object(g, 'cmd_clean'):
            self.assertEqual(g.main(self.args('clean', 'somedir')), 0)

    def test_a_failure_in_one_run_does_not_leak_into_the_next(self):
        with mock.patch.object(g, 'cmd_clean', lambda *a, **k: g.run_report.fail('x')):
            self.assertEqual(g.main(self.args('clean', 'somedir')), 1)
        with mock.patch.object(g, 'cmd_clean'):
            self.assertEqual(g.main(self.args('clean', 'somedir')), 0)


class EntryPointTests(unittest.TestCase):
    """The `if __name__ == "__main__"` part: it turns main's result into the process exit status."""
    def run_entry(self, fake_main):
        with open(SCRIPT, encoding='utf-8') as f:
            source = f.read()
        block = source[source.index('if __name__ == "__main__":'):]
        namespace = dict(vars(g), __name__='__main__', main=fake_main, process_argv=lambda argv: SimpleNamespace(command='test'),
                         Wakelock=lambda: SimpleNamespace(take_wakelock=lambda: None, release_wakelock=lambda: None))
        try:
            exec(compile(block, SCRIPT, 'exec'), namespace)
        except SystemExit as e:
            return e.code
        return None

    def test_success_exits_normally(self):
        self.assertIsNone(self.run_entry(lambda args: 0))

    def test_failures_exit_with_status_one(self):
        self.assertEqual(self.run_entry(lambda args: 1), 1)

    def test_ctrl_c_prints_what_was_done_and_exits_with_one(self):
        def interrupted(args):
            g.run_report.reset('download')
            g.run_report.count('files downloaded', 2)
            raise KeyboardInterrupt()
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            code = self.run_entry(interrupted)
        self.assertEqual(code, 1)
        text = '\n'.join(r.getMessage() for r in logs.records)
        self.assertIn('interrupted', text)
        self.assertIn('files downloaded:', text)

    def test_unexpected_errors_exit_with_one(self):
        def broken(args):
            raise RuntimeError('boom')
        with self.assertLogs('gogrepoc', level='ERROR'):
            self.assertEqual(self.run_entry(broken), 1)

    def test_a_deliberate_exit_status_is_kept(self):
        def stops(args):
            raise SystemExit(3)
        self.assertEqual(self.run_entry(stops), 3)


@functools.lru_cache(maxsize=None)
def download_run(name):
    """The whole rig result of a scenario (its report, and file_bytes: what the fake server really sent)."""
    with mock.patch.object(threading, 'excepthook', lambda args: None):
        return rig.run(g, name)


class TransferSummaryTests(unittest.TestCase):
    """'files downloaded' must count what came over the network. A file that was marked for change but was already right on the disk,
    chunk by chunk, is only checked in place; before, it was counted as downloaded with its full size (208 GB 'downloaded' in four
    minutes, with one file really transferred)."""
    CHECKED = 'files verified in place (nothing downloaded)'

    def counts(self, name):
        return download_run(name)['report']['counts']

    def test_a_fresh_download_reports_exactly_the_bytes_that_were_sent(self):
        run = download_run('fresh_download')
        counts = run['report']['counts']
        self.assertEqual(counts['files downloaded'], [10, run['file_bytes']])
        self.assertNotIn(self.CHECKED, counts)

    def test_files_that_were_already_right_are_counted_as_checked_not_as_downloaded(self):
        run = download_run('force_change_flags')                # every file is marked for change, and every file is on the disk
        counts = run['report']['counts']
        self.assertEqual(counts[self.CHECKED][0], 5)             # the five with checksum data on the server are checked in place
        self.assertEqual(counts[self.CHECKED][1], 9000)          # ... and the summary says how much data that was
        self.assertEqual(counts['files downloaded'][0], 5)       # the other five cannot be checked and are fetched again
        self.assertEqual(counts['files downloaded'][0] + counts[self.CHECKED][0], 10)

    def test_the_downloaded_size_is_what_the_server_sent_not_the_size_of_the_files(self):
        run = download_run('force_change_flags')
        self.assertEqual(run['report']['counts']['files downloaded'][1], run['file_bytes'])
        total = sum(c[1] for c in run['report']['counts'].values() if c[1])
        self.assertGreater(total, run['file_bytes'])             # the checked files are not in the downloaded figure

    def test_a_file_repaired_chunk_by_chunk_counts_only_the_chunks_that_arrived(self):
        run = download_run('resume_chunk_repair')
        downloaded = run['report']['counts']['files downloaded']
        self.assertEqual(downloaded[1], run['file_bytes'])
        self.assertLess(downloaded[1], 16000)                    # the ten files together are bigger than what was fetched
        self.assertEqual(downloaded[0], 10)

    def test_recovered_files_keep_their_own_line_and_size(self):
        counts = self.counts('provisional_files')
        self.assertEqual(counts['files recovered from an earlier run'], [2, 1800])
        self.assertNotIn(self.CHECKED, counts)

    def test_nothing_to_do_is_neither(self):
        counts = self.counts('all_up_to_date')
        self.assertNotIn('files downloaded', counts)
        self.assertNotIn(self.CHECKED, counts)

    def test_both_lines_are_in_the_summary_text(self):
        report = g.RunReport()
        report.reset('download')
        report.count('files downloaded', 1, 100 * 1024 * 1024)
        report.count(self.CHECKED, 215, 208 * 1024 ** 3)
        with self.assertLogs('gogrepoc', level='INFO') as logs:
            report.log()
        text = '\n'.join(logs.output)
        self.assertRegex(text, r'files downloaded:\s+1 \(100\.00MB\)')
        self.assertRegex(text, r'files verified in place \(nothing downloaded\):\s+215 \(208\.00GB\)')


class FinishProvisionalClassificationTests(unittest.TestCase):
    """How _finish_provisional_downloads sorts a finished file into the summary."""

    def finish(self, path, in_provisional, transferred, size=5000):
        job = g._DownloadJob(None, False, None)
        if in_provisional:
            job.provisional_dict[path] = object()
        if transferred:
            job.transferred[path] = transferred
        item = g.AttrDict(size=size, force_change=True, prev_verified=False, updated='x', old_updated=None)
        job.work_provisional.put((path, path + '.part', item, [item]))
        g.run_report.reset('download')
        with mock.patch.object(g.shutil, 'move'), mock.patch.object(g, 'save_manifest'), self.assertLogs('gogrepoc', level='DEBUG'):
            g._finish_provisional_downloads(job)
            g.info('end of test')
        return g.run_report.counts

    def test_data_that_arrived_is_a_download_of_that_size(self):
        self.assertEqual(self.finish('a/f.exe', False, 1234), {'files downloaded': [1, 1234]})

    def test_no_data_is_a_file_checked_in_place_with_the_size_of_the_file(self):
        self.assertEqual(self.finish('a/f.exe', False, 0), {'files verified in place (nothing downloaded)': [1, 5000]})

    def test_a_file_from_an_earlier_run_is_recovered_whatever_else_is_known(self):
        self.assertEqual(self.finish('a/f.exe', True, 0), {'files recovered from an earlier run': [1, 5000]})
        self.assertEqual(self.finish('a/f.exe', True, 99), {'files recovered from an earlier run': [1, 5000]})


@functools.lru_cache(maxsize=None)
def download_report(name):
    with mock.patch.object(threading, 'excepthook', lambda args: None):      # a scenario crashes a thread on purpose
        return rig.run(g, name)['report']


class DownloadSummaryTests(unittest.TestCase):
    def count(self, name, label):
        return download_report(name)['counts'].get(label, [0, 0])[0]

    def failed(self, name):
        return set(what for what, why in download_report(name)['failures'])

    def test_a_clean_download_counts_the_files_and_reports_no_failures(self):
        report = download_report('fresh_download')
        self.assertEqual(report['counts']['files downloaded'][0], 10)
        self.assertGreater(report['counts']['files downloaded'][1], 0)
        self.assertEqual(report['failures'], [])

    def test_a_dry_run_says_what_would_be_downloaded(self):
        report = download_report('dryrun_fresh')
        self.assertEqual(report['counts']['files that would be downloaded'][0], 10)
        self.assertNotIn('files downloaded', report['counts'])
        self.assertEqual(report['failures'], [])

    def test_up_to_date_and_skipped_files_are_counted(self):
        self.assertEqual(self.count('all_up_to_date', 'files already up to date'), 10)
        self.assertEqual(self.count('skipfiles', 'files skipped'), 2)
        self.assertEqual(self.count('download_limit', 'files skipped (download limit)'), 7)

    def test_files_recovered_from_an_earlier_run_are_counted_separately(self):
        self.assertEqual(self.count('provisional_files', 'files recovered from an earlier run'), 2)
        self.assertEqual(self.count('provisional_files', 'files downloaded'), 8)

    def test_failed_files_are_named_with_a_reason_and_the_others_still_count(self):
        report = download_report('faults')
        self.assertEqual(self.failed('faults'), {'faulty/missing.exe', 'faulty/headfail.exe', 'faulty/badrange.exe', 'faulty/badrange_nochunk.bin',
                                                  'faulty/truncated.exe', 'faulty/truncated_nochunk.bin'})
        self.assertEqual(report['counts']['files downloaded'][0], 3)
        reasons = dict(report['failures'])
        self.assertIn('404', reasons['faulty/missing.exe'])
        self.assertIn('incomplete', reasons['faulty/truncated.exe'])

    def test_every_queued_file_is_either_downloaded_or_reported(self):
        report = download_report('faults')
        self.assertEqual(report['counts']['files downloaded'][0] + len(report['failures']), 9)

    def test_a_file_that_exists_twice_is_a_failure(self):
        self.assertEqual(self.failed('provisional_and_dest'), {'alpha/manual.pdf'})

    def test_a_crashing_download_thread_is_reported_for_its_file(self):
        self.assertEqual(self.failed('worker_unhandled_exception'), {'Beta Game/setup_beta.exe'})
        self.assertIn('unexpected error', dict(download_report('worker_unhandled_exception')['failures'])['Beta Game/setup_beta.exe'])

    def test_disk_or_network_errors_are_reported_per_file(self):
        self.assertEqual(self.failed('worker_ioerror'), {'Beta Game/setup_beta.exe', 'Beta Game/extra_beta.exe'})

    def test_files_that_nobody_worked_on_are_reported_too(self):
        with mock.patch.object(g, '_download_worker', lambda job: None):      # all threads stop at once
            report = rig.run(g, 'fresh_download')['report']
        self.assertEqual(len(report['failures']), 10)
        self.assertTrue(all('stopped unexpectedly' in why for _, why in report['failures']))
        self.assertNotIn('files downloaded', report['counts'])


def games_api(fail_on_id=None):
    products = [dict(id=1000 + i, slug='game_%d' % i, title='Game %d' % i, category='RPG', image='//images.test/%d' % i,
                     url='/game/game_%d' % i, rating=40, updates=0) for i in range(3)]

    class Response(object):
        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    def request(session, url, args=None, **kwargs):
        if '/gameDetails/' in url:
            game_id = int(url.rsplit('/', 1)[1].split('.')[0])
            if game_id == fail_on_id:
                raise ValueError('GOG sent something unexpected')
            return Response(dict(backgroundImage='', cdKey='', forumLink='', changelog='', releaseTimestamp=1500000000, messages=[],
                                 downloads=[], galaxyDownloads=[], extras=[], dlcs=[]))
        return Response(dict(products=products, totalPages=1))
    return request


class TempDirTests(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        g.run_report.reset()

    def library(self, files):
        """Manifest with one game 'alpha' whose files are given as {name: bytes}; returns the entries."""
        entries = []
        for name, data in files.items():
            entries.append(g.AttrDict(name=name, desc=name, lang='English', os_type='windows', size=len(data), md5=hashlib.md5(data).hexdigest(), href='http://x/' + name,
                                      version='1', updated='2020', old_updated='2020', prev_verified=False, force_change=False, unreleased=False, md5_exempt=False,
                                      old_name=None, gog_data=g.AttrDict()))
        g.save_manifest([g.AttrDict(id=1, title='alpha', folder_name='alpha', long_title='alpha', genre='', store_url='/g', rating=0, release_timestamp=0, changelog='',
                                    has_updates=False, serial='', bg_url='', image_url='', downloads=entries, galaxyDownloads=[], sharedDownloads=[], extras=[])])
        return entries

    def write(self, folder, name, data):
        os.makedirs(os.path.join(folder, 'alpha'), exist_ok=True)
        with open(os.path.join(folder, 'alpha', name), 'wb') as f:
            f.write(data)


class UpdateSummaryTests(TempDirTests):
    def update(self, fail_on_id=None, full=False):
        with mock.patch.object(g, 'request', games_api(fail_on_id)), mock.patch.object(g, 'makeGOGSession', lambda: SimpleNamespace(token={})):
            flags = (False, False, False) if full else (True, True, True)
            g.cmd_update(['windows'], ['en'], *flags, [], [], False, 'both', 'resume', False, False, False, False, False, False, False)

    def test_new_games_are_counted(self):
        self.update()
        self.assertEqual(g.run_report.counts['new games added'][0], 3)
        self.assertEqual(g.run_report.failures, [])

    def test_a_game_that_cannot_be_fetched_is_a_failure_and_the_others_still_work(self):
        self.update(fail_on_id=1001)
        self.assertEqual(g.run_report.counts['new games added'][0], 2)
        self.assertEqual([what for what, why in g.run_report.failures], ['game_1'])      # the title of a game in update is its slug, the name -ids uses
        self.assertIn('could not be fetched', g.run_report.failures[0][1])
        self.assertIn('GOG sent something unexpected', g.run_report.failures[0][1])
        self.assertEqual(g.run_report.exit_status(), 1)
        self.assertEqual(sorted(game.title for game in g.load_manifest()), ['game_0', 'game_2'])

    def test_games_that_are_checked_again_are_counted_separately(self):
        self.update()
        g.run_report.reset()
        self.update(full=True)
        self.assertEqual(g.run_report.counts['known games re-checked'][0], 3)
        self.assertNotIn('new games added', g.run_report.counts)


class VerifySummaryTests(TempDirTests):
    def verify(self):
        g.cmd_verify(self.dir, False, [], True, True, False, False, False, [], ['windows'], ['en'], False, False, False, [], False, False, False, 0)

    def test_everything_fine(self):
        self.library({'ok.exe': b'a' * 50, 'also.exe': b'b' * 60})
        self.write(self.dir, 'ok.exe', b'a' * 50)
        self.write(self.dir, 'also.exe', b'b' * 60)
        self.verify()
        self.assertEqual(g.run_report.failures, [])
        self.assertEqual(g.run_report.counts['files in the manifest'][0], 2)
        self.assertEqual(g.run_report.counts['files present'][0], 2)

    def test_missing_wrong_size_and_wrong_checksum_are_failures(self):
        self.library({'ok.exe': b'a' * 50, 'missing.exe': b'b' * 60, 'short.exe': b'c' * 70, 'changed.exe': b'd' * 80})
        self.write(self.dir, 'ok.exe', b'a' * 50)
        self.write(self.dir, 'short.exe', b'c' * 10)                 # wrong size
        self.write(self.dir, 'changed.exe', b'e' * 80)               # right size, different content
        self.verify()
        reasons = {os.path.basename(what): why for what, why in g.run_report.failures}
        self.assertEqual(reasons, {'missing.exe': 'missing', 'short.exe': 'wrong file size', 'changed.exe': 'wrong checksum (md5)'})
        self.assertEqual(g.run_report.exit_status(), 1)
        self.assertEqual(g.run_report.counts['files in the manifest'][0], 4)


class BackupAndImportSummaryTests(TempDirTests):
    def setUp(self):
        super().setUp()
        self.src, self.dest = os.path.join(self.dir, 'src'), os.path.join(self.dir, 'dest')

    def test_backup_counts_copied_and_unchanged_files(self):
        self.library({'a.exe': b'a' * 50, 'b.exe': b'b' * 60})
        self.write(self.src, 'a.exe', b'a' * 50)
        self.write(self.src, 'b.exe', b'b' * 60)
        g.cmd_backup(self.src, self.dest, False, ['windows'], ['en'], [], [], False, False, False)
        self.assertEqual(g.run_report.counts['files copied'], [2, 110])
        g.run_report.reset()
        g.cmd_backup(self.src, self.dest, False, ['windows'], ['en'], [], [], False, False, False)
        self.assertEqual(g.run_report.counts, {'files already in the backup': [2, 0]})
        self.assertEqual(g.run_report.failures, [])

    def test_backup_reports_a_source_file_with_the_wrong_size(self):
        self.library({'a.exe': b'a' * 50, 'b.exe': b'b' * 60})
        self.write(self.src, 'a.exe', b'a' * 50)
        self.write(self.src, 'b.exe', b'b' * 5)
        g.cmd_backup(self.src, self.dest, False, ['windows'], ['en'], [], [], False, False, False)
        self.assertEqual(g.run_report.counts['files copied'][0], 1)
        self.assertEqual([os.path.basename(what) for what, why in g.run_report.failures], ['b.exe'])

    def test_import_counts_new_and_existing_files(self):
        self.library({'a.exe': b'a' * 50, 'b.exe': b'b' * 60})
        self.write(self.src, 'a.exe', b'a' * 50)
        self.write(self.src, 'b.exe', b'b' * 60)
        g.cmd_import(self.src, self.dest, ['windows'], ['en'], False, [], [], False, False, False, False)
        self.assertEqual(g.run_report.counts['files imported'], [2, 110])
        g.run_report.reset()
        g.cmd_import(self.src, self.dest, ['windows'], ['en'], False, [], [], False, False, False, False)
        self.assertEqual(g.run_report.counts, {'files already in the library': [2, 0]})


class CleanUpSummaryTests(TempDirTests):
    def test_clean_counts_what_it_moved(self):
        self.library({'a.exe': b'a' * 50})
        self.write(self.dir, 'a.exe', b'a' * 50)
        self.write(self.dir, 'junk.txt', b'x' * 30)                  # not in the manifest
        os.makedirs(os.path.join(self.dir, 'old_game'))
        with open(os.path.join(self.dir, 'old_game', 'f.bin'), 'wb') as f:
            f.write(b'y' * 20)
        g.cmd_clean(self.dir, False)
        self.assertEqual(g.run_report.counts['files moved to the orphan folder'], [1, 30])
        self.assertEqual(g.run_report.counts['folders moved to the orphan folder'], [1, 0])
        self.assertEqual(g.run_report.failures, [])

    def test_a_dry_run_moves_and_counts_nothing(self):
        self.library({'a.exe': b'a' * 50})
        self.write(self.dir, 'junk.txt', b'x' * 30)
        g.cmd_clean(self.dir, True)
        self.assertEqual(g.run_report.counts, {})

    def test_a_file_that_cannot_be_moved_is_a_failure(self):
        self.library({'a.exe': b'a' * 50})
        self.write(self.dir, 'a.exe', b'a' * 50)
        self.write(self.dir, 'junk.txt', b'x' * 30)
        with mock.patch.object(g, 'move_with_increment_on_clash', side_effect=OSError('locked')):
            g.cmd_clean(self.dir, False)
        self.assertEqual(len(g.run_report.failures), 1)
        what, why = g.run_report.failures[0]
        self.assertTrue(what.endswith('junk.txt'))
        self.assertIn('locked', why)
        self.assertEqual(g.run_report.exit_status(), 1)

    def partial_downloads(self):
        for folder in ('!downloading/game_a', '!downloading/game_b', '!downloading/!provisional'):
            os.makedirs(os.path.join(self.dir, folder))

    def test_clear_partial_downloads_counts_the_folders_it_deleted(self):
        self.partial_downloads()
        g.cmd_clear_partial_downloads(self.dir, False)
        self.assertEqual(g.run_report.counts['partial download folders deleted'][0], 2)
        self.assertEqual(g.run_report.failures, [])

    def test_a_folder_that_cannot_be_deleted_is_a_failure(self):
        self.partial_downloads()
        with mock.patch.object(g.shutil, 'rmtree', side_effect=OSError('in use')):
            g.cmd_clear_partial_downloads(self.dir, False)
        self.assertEqual(len(g.run_report.failures), 2)
        self.assertTrue(all('in use' in why for _, why in g.run_report.failures))

    def orphaned_folder(self):
        g.save_manifest([])
        os.makedirs(os.path.join(self.dir, g.ORPHAN_DIR_NAME, 'leftover'))

    def test_trash_counts_the_folders_it_deleted(self):
        self.orphaned_folder()
        g.cmd_trash(self.dir, False, False, True, True, False)                # folders, relaxed
        self.assertEqual(g.run_report.counts, {'folders deleted': [1, 0]})
        self.assertFalse(os.path.exists(os.path.join(self.dir, g.ORPHAN_DIR_NAME, 'leftover')))

    def test_trash_does_nothing_and_counts_nothing_in_a_dry_run(self):
        self.orphaned_folder()
        g.cmd_trash(self.dir, False, False, True, True, True)
        self.assertEqual(g.run_report.counts, {})
        self.assertTrue(os.path.exists(os.path.join(self.dir, g.ORPHAN_DIR_NAME, 'leftover')))

    def test_trash_reports_folders_it_cannot_delete(self):
        self.orphaned_folder()
        with mock.patch.object(g.shutil, 'rmtree', side_effect=OSError('in use')):
            g.cmd_trash(self.dir, False, False, True, True, False)
        self.assertEqual(len(g.run_report.failures), 1)
        self.assertIn('in use', g.run_report.failures[0][1])
        self.assertEqual(g.run_report.exit_status(), 1)


RUNNER = ("import runpy, sys, types\n"
          "for name in ('html5lib', 'psutil'):\n"
          "    try:\n        __import__(name)\n    except ImportError:\n        sys.modules[name] = types.ModuleType(name)\n"
          "script = sys.argv[1]; sys.argv = [script] + sys.argv[2:]\n"
          "runpy.run_path(script, run_name='__main__')\n")


class RealScriptExitStatusTests(TempDirTests):
    """Run the script itself, as a scheduled task would, and look at the exit status."""
    def run_script(self, *args):
        return subprocess.run([sys.executable, '-c', RUNNER, SCRIPT] + list(args) + ['-nolog'], capture_output=True, timeout=120,
                              env=dict(os.environ, PYTHONIOENCODING='utf-8'), cwd=self.dir, stdin=subprocess.DEVNULL)

    def test_verify_with_a_problem_exits_with_one_and_prints_the_summary(self):
        self.library({'ok.exe': b'a' * 50, 'gone.exe': b'b' * 60})
        self.write(self.dir, 'ok.exe', b'a' * 50)
        result = self.run_script('verify', self.dir, '-os', 'windows', '-lang', 'en')
        out = result.stdout.decode('utf-8')
        self.assertEqual(result.returncode, 1, out[-500:])
        self.assertIn('-- summary: verify', out)
        self.assertIn('FAILED: 1', out)
        self.assertIn('gone.exe: missing', out)

    def test_a_good_library_exits_with_zero(self):
        self.library({'ok.exe': b'a' * 50})
        self.write(self.dir, 'ok.exe', b'a' * 50)
        result = self.run_script('verify', self.dir, '-os', 'windows', '-lang', 'en')
        out = result.stdout.decode('utf-8')
        self.assertEqual(result.returncode, 0, out[-500:])
        self.assertIn('no failures', out)

    def test_a_command_without_failures_exits_with_zero(self):
        self.library({'ok.exe': b'a' * 50})
        self.assertEqual(self.run_script('export').returncode, 0)

    def test_a_missing_manifest_with_a_backup_stops_a_scheduled_run(self):
        self.library({'ok.exe': b'a' * 50})
        self.library({'ok.exe': b'a' * 50, 'more.exe': b'b' * 5})     # the second save leaves a .bak
        os.remove(g.MANIFEST_FILENAME)
        result = self.run_script('export')
        out = result.stdout.decode('utf-8')
        self.assertEqual(result.returncode, 1, out[-500:])
        self.assertIn('was not found', out)
        self.assertIn('not interactive', out)
        self.assertFalse(os.path.exists(g.MANIFEST_FILENAME))


if __name__ == '__main__':
    unittest.main()
