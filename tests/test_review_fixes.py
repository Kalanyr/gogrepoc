"""Regression tests for the fixes of 0.5.40: the download queue race, the token refresh (timeout, expired login in a thread),
get_fs_type on the root mount, ConditionalWriter, macOS without PyObjC, and the Python version gate (3.8 / 3.9)."""
import collections
import io
import os
import queue
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import _bootstrap  # noqa: F401
import requests
import gogrepo_delta as g

WORK_ITEM = ('http://example.invalid/f', 10, 0, 9, 'game/f.bin', 'dl/f.bin', 'prov/f.bin', None, [])


def run_worker(job, seconds=5):
    """Runs _download_worker in a thread; returns True if the thread ended within the time."""
    thread = threading.Thread(target=g._download_worker, args=(job,), daemon=True)
    thread.start()
    thread.join(seconds)
    return not thread.is_alive()


class AlwaysNonEmptyQueue(queue.Queue):
    """Plays the race deterministically: empty() says 'not empty' even when the last file was taken by another thread."""
    def empty(self):
        return False


class DownloadWorkerTests(unittest.TestCase):
    def setUp(self):
        g.run_report.reset('download')

    def tearDown(self):
        g.run_report.reset()

    def job(self, queue_class=queue.Queue):
        job = g._DownloadJob(None, False, None)
        job.work = queue_class()
        job.work.put(WORK_ITEM)
        return job

    def test_worker_ends_when_the_queue_runs_dry_while_empty_lies(self):
        job = self.job(AlwaysNonEmptyQueue)
        with mock.patch.object(g, '_prepare_download_file', side_effect=IOError('stop here')):
            self.assertTrue(run_worker(job), 'the worker waits forever in Queue.get() (the old empty()/get() race)')

    def test_two_workers_and_one_file_both_end(self):
        job = self.job()
        with mock.patch.object(g, '_prepare_download_file', side_effect=IOError('stop here')):
            threads = [threading.Thread(target=g._download_worker, args=(job,), daemon=True) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(5)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual({'game/f.bin'}, job.failed)

    def test_expired_login_marks_the_file_failed_and_stops_the_other_workers(self):
        job = self.job()
        job.work.put(('http://example.invalid/g', 10, 0, 9, 'game/g.bin', 'dl/g.bin', 'prov/g.bin', None, []))
        with mock.patch.object(g, '_prepare_download_file', side_effect=g.AuthExpired()):
            self.assertTrue(run_worker(job))
        self.assertTrue(job.abort.is_set())
        self.assertEqual({'game/f.bin'}, job.failed)
        self.assertEqual(1, job.work.qsize(), 'the second file must not be started once the login has expired')
        self.assertTrue(any('login expired' in why for _what, why in g.run_report.failures))

    def test_a_worker_does_not_start_when_the_job_is_aborted(self):
        job = self.job()
        job.abort.set()
        with mock.patch.object(g, '_prepare_download_file', side_effect=AssertionError('must not run')):
            self.assertTrue(run_worker(job))
        self.assertEqual(1, job.work.qsize())

    def test_auth_expired_is_a_system_exit_with_status_1(self):
        with self.assertRaises(SystemExit) as caught:
            raise g.AuthExpired()
        self.assertEqual(1, caught.exception.code)


class StalledServer(object):
    """Accepts connections and never answers."""
    def __enter__(self):
        self.sock = socket.socket()
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(5)
        self.url = 'http://127.0.0.1:%d/token' % self.sock.getsockname()[1]
        return self

    def __exit__(self, *exc):
        self.sock.close()


class TokenRefreshTests(unittest.TestCase):
    def expired_session(self):
        session = requests.Session()
        session.token = {'access_token': 'a', 'refresh_token': 'r', 'expiry': time.time() - 100}
        return session

    def test_the_refresh_request_has_a_timeout(self):
        session = self.expired_session()
        calls = []

        def fake_get(url, **kwargs):
            calls.append(kwargs)
            raise requests.exceptions.ConnectTimeout('slow')
        session.get = fake_get
        with mock.patch.object(g, 'HTTP_TIMEOUT', 7), self.assertRaises(g.AuthExpired):
            g.renew_token(session, retries=0)
        self.assertEqual(7, calls[0].get('timeout'))

    def test_a_stalled_token_server_does_not_hang(self):
        session = self.expired_session()
        started = time.time()
        with StalledServer() as server, mock.patch.object(g, 'GOG_TOKEN_URL', server.url), mock.patch.object(g, 'HTTP_TIMEOUT', 0.5):
            with self.assertRaises(g.AuthExpired):
                g.renew_token(session, retries=0)
        self.assertLess(time.time() - started, 5)


Part = collections.namedtuple('Part', 'mountpoint fstype')


class FsTypeTests(unittest.TestCase):
    def fs_type(self, path, parts, is_windows=False, sep='/'):
        with mock.patch.object(g.psutil, 'disk_partitions', create=True, return_value=parts), \
                mock.patch.object(g.os.path, 'realpath', return_value=path), mock.patch.object(g.os, 'sep', sep):
            return g.get_fs_type(path, is_windows)

    def test_a_folder_on_the_root_file_system_is_found(self):
        self.assertEqual('ext4', self.fs_type('/data/games', [Part('/', 'ext4'), Part('/boot', 'vfat')]))

    def test_the_longest_mount_still_wins(self):
        self.assertEqual('xfs', self.fs_type('/mnt/big/games', [Part('/', 'ext4'), Part('/mnt/big', 'xfs')]))

    def test_unknown_without_any_matching_mount(self):
        self.assertEqual('unknown', self.fs_type('/data/games', [Part('/boot', 'vfat')]))

    def test_windows_drive_letters_still_work(self):
        self.assertEqual('NTFS', self.fs_type('D:\\games\\x', [Part('C:\\', 'FAT32'), Part('D:\\', 'NTFS')], True, '\\'))


class ConditionalWriterTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='cw_')
        self.path = os.path.join(self.dir, '!info.txt')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, True)

    def read(self):
        with open(self.path, encoding='utf-8') as f:
            return f.read()

    def test_new_file_is_written(self):
        with g.ConditionalWriter(self.path) as w:
            w.write('one\n')
        self.assertEqual('one\n', self.read())

    def test_an_exception_in_the_body_writes_nothing_and_propagates(self):
        with self.assertRaises(RuntimeError):
            with g.ConditionalWriter(self.path) as w:
                w.write('half')
                raise RuntimeError('boom')
        self.assertFalse(os.path.exists(self.path))

    def test_an_exception_in_the_body_keeps_the_old_content(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('old\n')
        with self.assertRaises(RuntimeError):
            with g.ConditionalWriter(self.path) as w:
                w.write('new but incomplete')
                raise RuntimeError('boom')
        self.assertEqual('old\n', self.read())

    def test_changed_content_replaces_the_file_and_leaves_no_temp_files(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('old\n')
        with g.ConditionalWriter(self.path) as w:
            w.write('new\n')
        self.assertEqual('new\n', self.read())
        self.assertEqual(['!info.txt'], os.listdir(self.dir))

    def test_unchanged_content_is_not_rewritten(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('same\n')
        with mock.patch.object(g, 'atomic_write_text', side_effect=AssertionError('must not write')):
            with g.ConditionalWriter(self.path) as w:
                w.write('same\n')

    @unittest.skipIf(os.name == 'nt', 'POSIX permissions')
    def test_permissions_of_an_existing_file_are_kept(self):
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write('old\n')
        os.chmod(self.path, 0o644)
        with g.ConditionalWriter(self.path) as w:
            w.write('new\n')
        self.assertEqual(0o644, os.stat(self.path).st_mode & 0o777)


class MacOSWithoutPyObjCTests(unittest.TestCase):
    def test_missing_pyobjc_gives_none_instead_of_an_import_error(self):
        with mock.patch.dict(sys.modules, {'CoreFoundation': None, 'objc': None}):    # None in sys.modules makes the import fail
            self.assertEqual((None, None), g._import_macos_modules())

    def test_wakelock_is_skipped_with_one_warning(self):
        wakelock = g.Wakelock.__new__(g.Wakelock)             # no IOKit on this machine: skip __init__
        with mock.patch.object(g.platform, 'system', return_value='Darwin'), mock.patch.object(g, 'CoreFoundation', None), \
                mock.patch.object(g, 'objc', None), mock.patch.object(g, 'warn') as warn:
            wakelock.take_wakelock()
            wakelock.release_wakelock()
            wakelock.take_wakelock()
        self.assertEqual(1, warn.call_count)


class PythonVersionTests(unittest.TestCase):
    def check(self, version):
        out = io.StringIO()
        try:
            g.check_python_version(version, out)
        except SystemExit as e:
            return e.code, out.getvalue()
        return None, out.getvalue()

    def test_below_3_8_stops(self):
        code, text = self.check((3, 7, 9))
        self.assertEqual(1, code)
        self.assertIn('not supported', text)

    def test_3_8_and_3_9_start_with_a_warning(self):
        for version in ((3, 8, 10), (3, 9, 18)):
            code, text = self.check(version)
            self.assertIsNone(code)
            self.assertIn('Warning', text)

    def test_3_10_and_newer_are_silent(self):
        for version in ((3, 10, 0), (3, 14, 0)):
            self.assertEqual((None, ''), self.check(version))


class MultiZipPartsTests(unittest.TestCase):
    def test_finds_the_numbered_parts_next_to_the_first_one(self):
        with tempfile.TemporaryDirectory(prefix='[zip] ') as folder:             # brackets in the folder name must not act as a pattern
            for name in ('x.zip.001', 'x.zip.002', 'x.zip.003', 'y.zip.001', 'x.txt'):
                open(os.path.join(folder, name), 'w').close()
            found = g._multi_zip_parts('x.zip.001', os.path.join(folder, 'x.zip.001'))
        self.assertEqual(['x.zip.001', 'x.zip.002', 'x.zip.003'], sorted(found))

    def test_does_not_use_the_python_3_10_only_root_dir_argument(self):
        with mock.patch.object(g.glob, 'glob', side_effect=lambda pattern, **kw: self.assertFalse(kw) or []):
            g._multi_zip_parts('x.zip.001', '/tmp/x.zip.001')


if __name__ == '__main__':
    unittest.main()
