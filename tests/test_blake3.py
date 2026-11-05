"""BLAKE3 (entry 38): hashes kept in the manifest, trust-on-first-verify, bit-rot detection with -forceverify.

The real 'blake3' package is optional and not needed to run these tests: a stand-in module (BLAKE2b with the same small
interface: blake3.blake3(max_threads=...), update(), update_mmap(), hexdigest(), AUTO) is patched into the script."""
import hashlib
import logging
import os
import shutil
import tempfile
import types
import unittest
from unittest import mock
import _bootstrap  # noqa: F401
import gogrepo_delta as g


def expected_b3(data):
    return hashlib.blake2b(data, digest_size=32).hexdigest()


class _Hasher:
    AUTO = -1

    def __init__(self, max_threads=1):
        self._h = hashlib.blake2b(digest_size=32)

    def update(self, data):
        self._h.update(data)

    def hexdigest(self):
        return self._h.hexdigest()


class _HasherWithMmap(_Hasher):
    mmap_calls = 0

    def update_mmap(self, path):
        type(self).mmap_calls += 1
        with open(path, 'rb') as f:
            self._h.update(f.read())


class _HasherWithBrokenMmap(_Hasher):
    def update_mmap(self, path):
        raise OSError('cannot map this file')


def fake_module(cls):
    return types.SimpleNamespace(blake3=cls)


def b3_on(cls=_HasherWithMmap):
    return mock.patch.object(g, '_blake3', fake_module(cls))


class HashFileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def make(self, data):
        path = os.path.join(self.dir, 'f.bin')
        with open(path, 'wb') as f:
            f.write(data)
        return path

    def test_md5_only_matches_hashlib(self):
        for data in (b'', b'abc', os.urandom(3 * g.HASH_BLOCKSIZE + 17)):
            self.assertEqual(g.hash_file(self.make(data)), {'md5': hashlib.md5(data).hexdigest(), 'blake3': None})

    def test_both_hashes_come_from_one_pass_and_match(self):
        data = os.urandom(2 * g.HASH_BLOCKSIZE + 5)
        with b3_on():
            result = g.hash_file(self.make(data), md5=True, blake3=True)
        self.assertEqual(result, {'md5': hashlib.md5(data).hexdigest(), 'blake3': expected_b3(data)})

    def test_custom_block_size(self):
        data = os.urandom(10000)
        with b3_on():
            result = g.hash_file(self.make(data), md5=True, blake3=True, blocksize=7)
        self.assertEqual((result['md5'], result['blake3']), (hashlib.md5(data).hexdigest(), expected_b3(data)))

    def test_blake3_only_uses_the_memory_mapped_path_when_there_is_one(self):
        data = os.urandom(5000)
        _HasherWithMmap.mmap_calls = 0
        with b3_on(_HasherWithMmap):
            result = g.hash_file(self.make(data), md5=False, blake3=True)
        self.assertEqual(result, {'md5': None, 'blake3': expected_b3(data)})
        self.assertEqual(_HasherWithMmap.mmap_calls, 1)

    def test_blake3_only_falls_back_to_reading_when_mapping_fails_or_does_not_exist(self):
        data = os.urandom(5000)
        for cls in (_HasherWithBrokenMmap, _Hasher):
            with b3_on(cls):
                self.assertEqual(g.hash_file(self.make(data), md5=False, blake3=True)['blake3'], expected_b3(data), cls.__name__)

    def test_empty_file(self):
        with b3_on(_HasherWithBrokenMmap):
            self.assertEqual(g.hash_file(self.make(b''), md5=False, blake3=True)['blake3'], expected_b3(b''))

    def test_asking_for_blake3_without_the_package_is_an_error(self):
        with mock.patch.object(g, '_blake3', None):
            self.assertFalse(g.blake3_available())
            with self.assertRaises(RuntimeError):
                g.hash_file(self.make(b'x'), md5=False, blake3=True)

    def test_the_file_is_closed_afterwards(self):
        path = self.make(b'data')
        with b3_on():
            g.hash_file(path, md5=True, blake3=True)
        os.remove(path)    # impossible on Windows while a handle is still open


class VerifyBlake3Tests(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        g.run_report.reset()
        self.data = {'a.exe': b'a' * 5000}

    def library(self, files, **entry_over):
        entries = []
        for name, data in files.items():
            e = g.AttrDict(name=name, desc=name, lang='English', os_type='windows', size=len(data), md5=hashlib.md5(data).hexdigest(), href='http://x/' + name,
                           version='1', updated='2020', old_updated='2020', prev_verified=False, force_change=False, unreleased=False, md5_exempt=False,
                           old_name=None, gog_data=g.AttrDict())
            e.update(entry_over)
            entries.append(e)
        g.save_manifest([g.AttrDict(id=1, title='alpha', folder_name='alpha', long_title='alpha', genre='', store_url='/g', rating=0, release_timestamp=0, changelog='',
                                    has_updates=False, serial='', bg_url='', image_url='', downloads=entries, galaxyDownloads=[], sharedDownloads=[], extras=[])])

    def write(self, name, data):
        os.makedirs(os.path.join(self.dir, 'alpha'), exist_ok=True)
        with open(os.path.join(self.dir, 'alpha', name), 'wb') as f:
            f.write(data)

    def verify(self, check_md5=True, force=False, use_blake3=True):
        g.cmd_verify(self.dir, False, [], check_md5, True, False, False, False, [], ['windows'], ['en'], False, False, False, [], force, False, False, 0, use_blake3=use_blake3)

    def entry(self, name='a.exe'):
        return {d.name: d for d in g.load_manifest()[0].downloads}[name]

    # ---- recording ------------------------------------------------------
    def test_a_file_that_passes_gets_its_blake3_recorded_in_the_manifest(self):
        self.library(self.data)
        self.write('a.exe', self.data['a.exe'])
        with b3_on():
            self.verify()
        self.assertEqual(self.entry().blake3, expected_b3(self.data['a.exe']))
        self.assertTrue(self.entry().prev_verified)
        self.assertEqual(g.run_report.failures, [])

    def test_a_file_that_fails_gets_nothing_recorded(self):
        self.library(self.data)
        self.write('a.exe', b'b' * 5000)                      # right size, wrong content
        with b3_on():
            self.verify()
        self.assertIsNone(getattr(self.entry(), 'blake3', None))
        self.assertEqual([why for _, why in g.run_report.failures], ['wrong checksum (md5)'])

    def test_nothing_is_recorded_when_the_md5_check_was_skipped(self):
        self.library(self.data)
        self.write('a.exe', self.data['a.exe'])
        with b3_on():
            self.verify(check_md5=False)
        self.assertIsNone(getattr(self.entry(), 'blake3', None))

    def test_noblake3_and_a_missing_package_change_nothing(self):
        self.library(self.data)
        self.write('a.exe', self.data['a.exe'])
        with b3_on():
            self.verify(use_blake3=False)
        self.assertIsNone(getattr(self.entry(), 'blake3', None))
        with mock.patch.object(g, '_blake3', None), self.assertLogs('gogrepoc', level='INFO') as logs:
            self.verify(force=True)
        self.assertIsNone(getattr(self.entry(), 'blake3', None))
        self.assertTrue(any('blake3 package is not installed' in m for m in logs.output))
        self.assertEqual(g.run_report.failures, [])

    def test_a_type_without_md5_gets_a_baseline_when_its_size_is_known(self):
        data = {'part.zip.001': b'z' * 4000}
        self.library(data, md5=None)
        self.write('part.zip.001', data['part.zip.001'])
        with b3_on():
            self.verify()
        self.assertEqual(self.entry('part.zip.001').blake3, expected_b3(data['part.zip.001']))

    def test_a_type_without_md5_that_is_flagged_as_changed_is_left_alone(self):
        data = {'part.zip.001': b'z' * 4000}
        self.library(data, md5=None, force_change=True, blake3='stale-value-of-old-content')
        self.write('part.zip.001', data['part.zip.001'])
        with b3_on():
            self.verify()
        self.assertEqual(g.run_report.failures, [])
        self.assertEqual(self.entry('part.zip.001').blake3, 'stale-value-of-old-content')   # neither compared nor replaced

    # ---- comparing (bit-rot) ---------------------------------------------
    def test_forceverify_compares_only_the_blake3_when_there_is_a_baseline(self):
        self.library(self.data)
        self.write('a.exe', self.data['a.exe'])
        with b3_on():
            self.verify()
            with mock.patch.object(g, 'hashfile', side_effect=AssertionError('md5 must not be computed')):
                self.verify(force=True)
        self.assertEqual(g.run_report.failures, [])

    def test_a_flipped_byte_is_found_and_the_md5_decides_when_it_is_checked(self):
        self.library(self.data)
        self.write('a.exe', self.data['a.exe'])
        with b3_on():
            self.verify()
            self.write('a.exe', b'a' * 4999 + b'b')           # same size, one byte differs
            self.verify(force=True)
        self.assertEqual([why for _, why in g.run_report.failures], ['wrong checksum (md5)'])
        self.assertFalse(self.entry().prev_verified)

    def test_a_flipped_byte_is_reported_as_a_blake3_change_when_the_md5_is_skipped(self):
        self.library(self.data)
        self.write('a.exe', self.data['a.exe'])
        with b3_on():
            self.verify()
            self.write('a.exe', b'a' * 4999 + b'b')
            self.verify(check_md5=False, force=True)
        self.assertEqual([why for _, why in g.run_report.failures], ['changed since last verification (blake3)'])
        self.assertFalse(self.entry().prev_verified)

    def test_a_stale_baseline_with_a_matching_md5_is_refreshed_not_reported(self):
        self.library(self.data, blake3='0' * 64, prev_verified=False)
        self.write('a.exe', self.data['a.exe'])
        with b3_on(), self.assertLogs('gogrepoc', level='WARNING') as logs:
            self.verify(force=True)
        self.assertEqual(g.run_report.failures, [])
        self.assertEqual(self.entry().blake3, expected_b3(self.data['a.exe']))
        self.assertTrue(any('was stale' in m for m in logs.output))

    def test_a_missing_file_keeps_its_baseline(self):
        self.library(self.data, blake3='abc', prev_verified=True)
        with b3_on():
            self.verify(force=True)
        self.assertEqual(self.entry().blake3, 'abc')
        self.assertEqual([why for _, why in g.run_report.failures], ['missing'])

    def test_a_matching_baseline_clears_the_change_mark_like_an_md5_match(self):
        self.library(self.data, blake3=expected_b3(self.data['a.exe']), force_change=True, old_updated=None)
        self.write('a.exe', self.data['a.exe'])
        with b3_on():
            self.verify(force=True)
        self.assertFalse(self.entry().force_change)

    def test_the_summary_counts_the_blake3_results(self):
        self.library(self.data)
        self.write('a.exe', self.data['a.exe'])
        with b3_on():
            with self.assertLogs('gogrepoc', level='INFO') as logs:
                self.verify()
            self.assertTrue(any('blake3 recorded..... 1' in m for m in logs.output))
            with self.assertLogs('gogrepoc', level='INFO') as logs:
                self.verify(force=True)
        self.assertTrue(any('blake3 matches...... 1' in m for m in logs.output))
        self.assertTrue(any('blake3 mismatches... 0' in m for m in logs.output))


class UpdateCarryOverTests(unittest.TestCase):
    def game(self, **dl_over):
        def d(**o):
            e = g.AttrDict(name='setup.exe', md5='m1', size=100, lang='en', updated='2020-01-01T00:00:00+00:00', unreleased=False)
            e.update(o)
            return e
        return g.AttrDict(title='Game', long_title='Game', changelog='', has_updates=False, serial='', downloads=[d(**dl_over)],
                          galaxyDownloads=[], sharedDownloads=[], extras=[g.AttrDict(name='m.pdf', md5=None, size=10, updated='2020-01-01T00:00:00+00:00', unreleased=False, **{k: v for k, v in dl_over.items() if k == 'blake3'})])

    def update(self, old, new, strict=False):
        with self.assertLogs('gogrepoc', level='INFO'):
            logging.getLogger('gogrepoc').info('marker')
            g.handle_game_updates(old, new, strict, False, False)

    def test_blake3_is_carried_over_when_md5_and_size_are_unchanged(self):
        old, new = self.game(blake3='B3'), self.game()
        self.update(old, new)
        self.assertEqual(new.downloads[0].blake3, 'B3')

    def test_blake3_is_dropped_when_the_md5_changed(self):
        old, new = self.game(blake3='B3'), self.game(md5='m2')
        self.update(old, new)
        self.assertIsNone(getattr(new.downloads[0], 'blake3', None))

    def test_blake3_survives_a_rename_of_the_same_content(self):
        old, new = self.game(blake3='B3'), self.game(name='setup_v2.exe')
        self.update(old, new)
        self.assertEqual(new.downloads[0].blake3, 'B3')

    def test_old_manifests_without_the_field_are_fine(self):
        old, new = self.game(), self.game()
        self.update(old, new)
        self.assertIsNone(new.downloads[0].blake3)

    def test_without_md5_it_is_carried_but_strict_mode_drops_it(self):
        old, new = self.game(md5=None, blake3='B3'), self.game(md5=None)
        self.update(old, new)
        self.assertEqual(new.downloads[0].blake3, 'B3')
        old, new = self.game(md5=None, blake3='B3'), self.game(md5=None)
        self.update(old, new, strict=True)
        self.assertIsNone(new.downloads[0].blake3)


class CommandLineTests(unittest.TestCase):
    def test_verify_has_a_noblake3_option_that_is_off_by_default(self):
        self.assertFalse(g.process_argv(['gogrepo_delta.py', 'verify', 'd']).noblake3)
        self.assertTrue(g.process_argv(['gogrepo_delta.py', 'verify', 'd', '-noblake3']).noblake3)
        self.assertTrue(g.process_argv(['gogrepo_delta.py', 'verify', 'd', '--noblake3']).noblake3)


if __name__ == '__main__':
    unittest.main()
