"""cmd_update: how often the manifest is saved while game details are fetched, and what Ctrl-C does.

A fake GOG account API (patched `request`) serves product pages and game details, so no network is needed."""
import contextlib
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
import _bootstrap  # noqa: F401
import gogrepo_delta as g


class FakeResponse(object):
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


def fake_api(count, interrupt_on_id=None, fail_on_id=None):
    products = [dict(id=1000 + i, slug='game_%03d' % i, title='Game %d' % i, category='RPG', image='//images.test/%d' % i,
                     url='/game/game_%03d' % i, rating=40, updates=0) for i in range(count)]

    def detail(game_id):
        return dict(backgroundImage='', cdKey='', forumLink='', changelog='', releaseTimestamp=1500000000, messages=[],
                    downloads=[], galaxyDownloads=[], extras=[], dlcs=[])

    def request(session, url, args=None, **kwargs):
        if '/gameDetails/' in url:
            game_id = int(url.rsplit('/', 1)[1].split('.')[0])
            if game_id == interrupt_on_id:
                raise KeyboardInterrupt()
            if game_id == fail_on_id:
                raise g.requests.exceptions.ConnectionError('temporary connection failure')
            return FakeResponse(detail(game_id))
        return FakeResponse(dict(products=products, totalPages=1))
    return request


class UpdateSaveTests(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.dir = tempfile.mkdtemp()
        os.chdir(self.dir)
        self.saves = dict(manifest=0, resume=0)

    def tearDown(self):
        os.chdir(self.cwd)
        shutil.rmtree(self.dir, ignore_errors=True)

    @contextlib.contextmanager
    def api(self, count, interrupt_on_id=None, fail_on_id=None):
        real_save, real_resume = g.save_manifest, g.save_resume_manifest

        def save(*a, **k):
            self.saves['manifest'] += 1
            return real_save(*a, **k)

        def save_resume(*a, **k):
            self.saves['resume'] += 1
            return real_resume(*a, **k)
        with mock.patch.object(g, 'request', fake_api(count, interrupt_on_id, fail_on_id)), \
                mock.patch.object(g, 'makeGOGSession', lambda: SimpleNamespace(token={})), \
                mock.patch.object(g, 'save_manifest', save), mock.patch.object(g, 'save_resume_manifest', save_resume):
            yield

    def update(self, resumemode='resume'):
        # the arguments of a default "update": skipknown, updateonly and partial all on
        g.cmd_update(['windows'], ['en'], True, True, True, [], [], False, 'both', resumemode, False, False, False, False, False, False, False)

    def titles(self):
        return sorted(game.title for game in g.load_manifest())

    def test_default_mode_saves_once_at_the_end_for_a_small_update(self):
        with self.api(7):
            self.update()
        self.assertEqual(self.saves['manifest'], 1)        # used to be 8 (after every game and at the end)
        self.assertEqual(len(self.titles()), 7)

    def test_larger_updates_save_every_fifty_games_and_at_the_end(self):
        with self.api(120):
            self.update()
        self.assertEqual(self.saves['manifest'], 3)        # after game 50, after game 100, final
        self.assertEqual(len(self.titles()), 120)

    def test_ctrl_c_saves_the_games_fetched_so_far_and_re_raises(self):
        with self.api(8, interrupt_on_id=1003), self.assertRaises(KeyboardInterrupt):
            self.update()
        self.assertEqual(self.titles(), ['game_000', 'game_001', 'game_002'])
        self.assertEqual(self.saves['manifest'], 1)
        self.assertEqual([f for f in os.listdir('.') if f.endswith('.tmp')], [])

    def test_an_interrupted_update_resumes_and_completes_without_duplicates(self):
        with self.api(8, interrupt_on_id=1003), self.assertRaises(KeyboardInterrupt):
            self.update()
        with self.api(8):
            self.update()
        self.assertEqual(self.titles(), ['game_%03d' % i for i in range(8)])
        pending = g.load_resume_manifest()
        self.assertTrue(pending[-1]['complete'])

    def test_a_failed_game_stays_in_the_resume_manifest_and_is_not_marked_complete(self):
        with self.api(5, fail_on_id=1002):
            self.update()

        pending = g.load_resume_manifest()
        self.assertFalse(pending[-1]['complete'])
        self.assertEqual([1002], [item.id for item in pending[:-1]])
        self.assertEqual(4, len(self.titles()))

    def test_a_failed_game_is_retried_by_the_next_update(self):
        with self.api(5, fail_on_id=1002):
            self.update()

        with self.api(5):
            self.update()

        self.assertEqual(['game_%03d' % i for i in range(5)], self.titles())
        pending = g.load_resume_manifest()
        self.assertTrue(pending[-1]['complete'])
        self.assertEqual(1, len(pending), 'only the resume properties record should remain')

    def test_a_second_ctrl_c_during_the_save_keeps_the_previous_manifest(self):
        with self.api(8):
            self.update()                                  # a complete manifest exists
        with open(g.MANIFEST_FILENAME, encoding='utf-8') as f:
            before = f.read()
        with mock.patch.object(g.pprint, 'pprint', side_effect=KeyboardInterrupt()), mock.patch.object(g.json, 'dumps', side_effect=KeyboardInterrupt()), \
                self.assertRaises(KeyboardInterrupt):                 # whichever format is written
            g.save_manifest_core_worker(g.load_manifest(), g.MANIFEST_FILENAME)
        with open(g.MANIFEST_FILENAME, encoding='utf-8') as f:
            self.assertEqual(f.read(), before)
        self.assertEqual([x for x in os.listdir('.') if x.endswith('.tmp')], [])


if __name__ == '__main__':
    unittest.main()
