"""Entry 42: cmd_download records a BLAKE3 in the manifest for every file that has arrived (and been confirmed), like verify would.

Runs cmd_download against the local fake GOG server of tests/download_rig (needs no network). A stand-in module with the interface of the
blake3 package (BLAKE2b) is used, so the real package is not needed."""
import functools
import hashlib
import os
import sys
import unittest
import _bootstrap  # noqa: F401
import gogrepo_delta as g

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'download_rig'))
import rig  # noqa: E402


@functools.lru_cache(maxsize=None)
def result(name):
    return rig.run(g, name)


def b3(data):
    return hashlib.blake2b(data, digest_size=32).hexdigest()


def entries(r):
    """name -> manifest entry, over all lists of all games."""
    found = {}
    for game in r['manifest_obj']:
        for kind in ('downloads', 'galaxyDownloads', 'sharedDownloads', 'extras'):
            for e in game[kind]:
                found[e['name']] = e
    return found


def messages(r, level=None):
    return [m for lvl, m in r['logs'] if level is None or lvl == level]


class RecordedAfterDownloadTests(unittest.TestCase):
    def test_every_downloaded_file_gets_its_blake3(self):
        r = result('blake3_fresh')
        e = entries(r)
        self.assertEqual(10, len(e))
        self.assertEqual(b3(rig.blob(1, 2500)), e['setup_alpha.exe']['blake3'])            # md5 in the manifest, confirmed by the checksum data
        self.assertEqual(b3(rig.blob(9, 2100)), e['setup_beta.exe']['blake3'])
        self.assertEqual(b3(rig.blob(8, 1700)), e['soundtrack.zip']['blake3'])             # no checksum data: confirmed by its size
        self.assertTrue(all(x.get('blake3') for x in e.values()), [n for n, x in e.items() if not x.get('blake3')])

    def test_a_file_without_md5_gets_it_by_its_size(self):
        r = result('blake3_fresh')
        entry = entries(r)['setup_alpha-1.bin']
        self.assertIsNone(entry['md5'])
        self.assertEqual(b3(rig.blob(2, 3100)), entry['blake3'])

    def test_the_download_itself_is_unchanged(self):
        r = result('blake3_fresh')
        self.assertEqual([], r['report']['failures'])
        self.assertEqual(10, r['report']['counts']['files downloaded'][0])
        self.assertFalse(any(e['prev_verified'] for e in entries(r).values()), 'verify, not download, marks a file as verified')

    def test_a_file_recovered_from_an_earlier_run_gets_its_blake3_too(self):
        r = result('blake3_recovered')
        self.assertEqual(b3(rig.blob(7, 700)), entries(r)['manual.pdf']['blake3'])


class NothingRecordedTests(unittest.TestCase):
    def test_noblake3_records_nothing(self):
        r = result('blake3_off')
        self.assertFalse(any(x.get('blake3') for x in entries(r).values()))
        self.assertEqual([], r['report']['failures'])

    def test_without_the_package_nothing_is_recorded_and_it_says_so(self):
        r = result('blake3_missing_package')
        self.assertFalse(any(x.get('blake3') for x in entries(r).values()))
        self.assertEqual([], r['report']['failures'])
        self.assertTrue(any('blake3 package is not installed' in m for m in messages(r, 'INFO')))

    def test_a_dry_run_hashes_nothing_and_does_not_mention_the_package(self):
        r = result('blake3_dry_run')
        self.assertFalse(any('blake3' in m.lower() for m in messages(r)))

    def test_a_manifest_md5_that_does_not_match_gives_no_baseline_but_keeps_the_download(self):
        r = result('blake3_md5_differs')
        e = entries(r)
        self.assertFalse(e['setup_alpha.exe'].get('blake3'))
        self.assertTrue(e['setup_beta.exe'].get('blake3'))                                 # the others are not affected
        self.assertEqual([], r['report']['failures'])
        self.assertTrue(any('no BLAKE3 recorded for setup_alpha.exe' in m for m in messages(r, 'WARNING')))
        self.assertIn('alpha/setup_alpha.exe', {k for k, v in r['tree'].items() if v is not None})


class ChangedFileTests(unittest.TestCase):
    def test_a_redownloaded_file_replaces_the_old_blake3(self):
        r = result('blake3_replaced')
        entry = entries(r)['setup_alpha.exe']
        self.assertEqual(b3(rig.blob(1, 2500)), entry['blake3'])
        self.assertFalse(entry['force_change'])

    def test_a_redownloaded_file_never_keeps_a_blake3_of_the_old_content(self):
        r = result('blake3_dropped')                                                       # new content, but no package to hash it
        entry = entries(r)['setup_alpha.exe']
        self.assertFalse(entry.get('blake3'))
        self.assertFalse(entry['force_change'])


class OptionTests(unittest.TestCase):
    def test_the_download_command_accepts_noblake3(self):
        p1, _sp = g.build_parser()
        args = p1.parse_args(['download', '-noblake3'])
        self.assertTrue(args.noblake3)
        self.assertFalse(p1.parse_args(['download']).noblake3)


if __name__ == '__main__':
    unittest.main()
