"""-tags and -skiptags (entry 39): the tags of your GOG library, kept in the manifest as tag_names."""
import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock
import _bootstrap  # noqa: F401
import gogrepo_delta as g

TAG_LIST = [dict(id='11', name='Favorites'), dict(id='12', name='NEXT TO PLAY'), dict(id='13', name='Completed')]


def api(tags_of, tag_list=TAG_LIST, extra_products=(), only=None):
    """A fake product list: game_0, game_1, game_2 with the tag ids given by tags_of ({index: [ids]})."""
    products = [dict(id=1000 + i, slug='game_%d' % i, title='Game %d' % i, category='RPG', image='//i/%d' % i, url='/game/game_%d' % i,
                     rating=40, updates=0, tags=tags_of.get(i, [])) for i in range(3) if only is None or i in only] + list(extra_products)

    class Response(object):
        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    def request(session, url, args=None, **kwargs):
        if '/gameDetails/' in url:
            return Response(dict(backgroundImage='', cdKey='', forumLink='', changelog='', releaseTimestamp=1500000000, messages=[],
                                 downloads=[], galaxyDownloads=[], extras=[], dlcs=[]))
        return Response(dict(products=products, totalPages=1, tags=tag_list))
    return request


class TempDir(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp()
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        g.run_report.reset()


class HelperTests(unittest.TestCase):
    def test_tag_names_are_found_from_ids_dicts_and_unknown_ids(self):
        tag_map = g.tag_map_of(dict(tags=TAG_LIST))
        self.assertEqual(tag_map, {'11': 'Favorites', '12': 'NEXT TO PLAY', '13': 'Completed'})
        self.assertEqual(g.product_tag_names(dict(tags=['11', 12, '99']), tag_map), ['Favorites', 'NEXT TO PLAY', '99'])
        self.assertEqual(g.product_tag_names(dict(tags=[dict(id='13', name='Completed'), dict(id='11')]), tag_map), ['Completed', 'Favorites'])
        self.assertEqual(g.product_tag_names(dict(tags=['11', '11']), tag_map), ['Favorites'])
        self.assertEqual(g.product_tag_names(dict(), tag_map), [])
        self.assertEqual(g.tag_map_of(dict()), {})

    def test_tags_compare_without_case_accents_punctuation_or_spacing(self):
        self.assertEqual(g.tag_keys(['Next to  play', 'CO-OP']), g.tag_keys(['next to play!', 'co op']))
        game = g.AttrDict(id=1, title='a', tag_names=['NEXT TO PLAY'])
        self.assertTrue(g.game_has_any_tag(game, g.tag_keys(['next to play'])))
        self.assertFalse(g.game_has_any_tag(game, g.tag_keys(['completed'])))
        self.assertFalse(g.game_has_any_tag(g.AttrDict(id=2, title='b'), g.tag_keys(['completed'])))     # an old entry without tag data


def manifest_games():
    return [g.AttrDict(id=1, title='one', tag_names=['Favorites']), g.AttrDict(id=2, title='two', tag_names=['Favorites', 'Completed']),
            g.AttrDict(id=3, title='three', tag_names=['NEXT TO PLAY']), g.AttrDict(id=4, title='four', tag_names=[])]


class SelectionTests(unittest.TestCase):
    def test_any_of_the_tags_selects_and_skiptags_collects(self):
        selection = g.select_games_by_tags(manifest_games(), ['favorites', 'next to play'], ['COMPLETED'])
        self.assertEqual((selection.selected, selection.skipped, selection.problems, selection.fatal), ({1, 2, 3}, {2}, [], False))

    def test_no_tags_given_selects_nothing_in_particular(self):
        selection = g.select_games_by_tags(manifest_games(), [], [])
        self.assertEqual((selection.selected, selection.skipped), (None, set()))

    def test_a_tag_that_no_game_has_is_a_problem_that_lists_the_tags(self):
        selection = g.select_games_by_tags(manifest_games(), ['Nope'], ['Also nope'])
        self.assertEqual([(what, why) for what, why, _ in selection.problems], [('-tags Nope', 'no such tag'), ('-skiptags Also nope', 'no such tag')])
        self.assertIn('Completed, Favorites, NEXT TO PLAY', selection.problems[0][2])

    def test_words_of_one_tag_typed_without_quotes_get_a_hint(self):
        selection = g.select_games_by_tags(manifest_games(), ['NEXT', 'TO', 'PLAY'], [])
        self.assertEqual(len(selection.problems), 3)
        self.assertIn('must be in quotes: -tags "NEXT TO PLAY"', selection.problems[0][2])

    def test_a_manifest_without_any_tag_data_cannot_decide(self):
        selection = g.select_games_by_tags([g.AttrDict(id=1, title='old')], ['x'], [])
        self.assertTrue(selection.fatal)
        self.assertIn("Run 'update'", selection.problems[0][2])


class ApplyTagOptionsTests(TempDir):
    def setUp(self):
        super().setUp()
        g.save_manifest(manifest_games())

    def args(self, tags=(), skiptags=(), ids=(), skipids=()):
        return SimpleNamespace(tags=list(tags), skiptags=list(skiptags), ids=list(ids), skipids=list(skipids))

    def test_nothing_to_do_without_tag_options(self):
        a = self.args()
        self.assertTrue(g.apply_tag_options(a))
        self.assertEqual((a.ids, a.skipids), ([], []))

    def test_tags_become_ids(self):
        a = self.args(tags=['Favorites'])
        self.assertTrue(g.apply_tag_options(a))
        self.assertEqual(a.ids, ['1', '2'])

    def test_tags_with_ids_means_the_games_in_both(self):
        a = self.args(tags=['Favorites'], ids=['two', '3'])
        self.assertTrue(g.apply_tag_options(a))
        self.assertEqual(a.ids, ['2'])

    def test_skiptags_are_added_to_skipids_and_take_games_out_of_tags(self):
        a = self.args(tags=['Favorites'], skiptags=['Completed'], skipids=['4'])
        self.assertTrue(g.apply_tag_options(a))
        self.assertEqual(a.ids, ['1'])
        self.assertEqual(a.skipids, ['4', '2'])
        b = self.args(skiptags=['Completed'])
        self.assertTrue(g.apply_tag_options(b))
        self.assertEqual((b.ids, b.skipids), ([], ['2']))

    def test_an_empty_selection_stops_instead_of_meaning_all_games(self):
        for a in (self.args(tags=['Favorites'], ids=['3']), self.args(tags=['Favorites'], skiptags=['Favorites'])):
            with self.assertLogs('gogrepoc', level='WARNING'):
                self.assertFalse(g.apply_tag_options(a))

    def test_an_unknown_tag_is_reported_and_fails_the_run(self):
        a = self.args(tags=['Favorites', 'Nope'])
        with self.assertLogs('gogrepoc', level='ERROR'):
            self.assertTrue(g.apply_tag_options(a))
        self.assertEqual(a.ids, ['1', '2'])
        self.assertEqual([why for _, why in g.run_report.failures], ['no such tag'])

    def test_a_manifest_without_tag_data_stops_the_command(self):
        g.save_manifest([g.AttrDict(id=1, title='old')])
        with self.assertLogs('gogrepoc', level='ERROR'):
            self.assertFalse(g.apply_tag_options(self.args(skiptags=['x'])))
        self.assertEqual(g.run_report.exit_status(), 1)


class MainDispatchTests(TempDir):
    def setUp(self):
        super().setUp()
        g.save_manifest(manifest_games())

    def run_verify(self, *extra):
        args = g.process_argv(['gogrepo_delta.py', 'verify', self.dir] + list(extra))
        with mock.patch.object(g, 'cmd_verify') as verify:
            status = g.main(args)
        return verify, status

    def test_the_command_gets_the_ids_of_the_tagged_games(self):
        verify, status = self.run_verify('-tags', 'Favorites', '-skiptags', 'Completed')
        self.assertEqual(verify.call_count, 1)
        positional = verify.call_args[0]
        self.assertEqual(positional[8], ['1'])          # ids
        self.assertEqual(positional[2], ['2'])          # skipids
        self.assertEqual(status, 0)

    def test_the_command_does_not_run_when_nothing_is_left(self):
        verify, status = self.run_verify('-tags', 'Favorites', '-ids', '3')
        self.assertEqual(verify.call_count, 0)

    def test_without_tag_options_nothing_changes(self):
        verify, status = self.run_verify()
        self.assertEqual((verify.call_args[0][8], verify.call_args[0][2]), ([], []))

    def test_every_command_that_takes_ids_takes_tags(self):
        for command, extra in (('update', []), ('download', ['d']), ('verify', ['d']), ('import', ['s', 'd']), ('backup', ['s', 'd'])):
            a = g.process_argv(['gogrepo_delta.py', command] + extra + ['-tags', 'a', 'b c', '-skiptags', 'd'])
            self.assertEqual((a.tags, a.skiptags), (['a', 'b c'], ['d']), command)
            b = g.process_argv(['gogrepo_delta.py', command] + extra)
            self.assertEqual((b.tags, b.skiptags), ([], []), command)


class UpdateTagTests(TempDir):
    def update(self, request, tags=(), skiptags=(), full=True):
        flags = (False, False, False) if full else (True, True, True)
        with mock.patch.object(g, 'request', request), mock.patch.object(g, 'makeGOGSession', lambda: SimpleNamespace(token={})):
            g.cmd_update(['windows'], ['en'], *flags, [], [], False, 'both', 'resume', False, False, False, False, False, False, False,
                         tags=list(tags), skiptags=list(skiptags))

    def names(self):
        return dict((game.title, game.tag_names) for game in g.load_manifest())

    TAGS = {0: ['11'], 1: ['11', '13'], 2: []}

    def test_the_tag_names_are_stored_with_every_game(self):
        self.update(api(self.TAGS))
        self.assertEqual(self.names(), {'game_0': ['Favorites'], 'game_1': ['Favorites', 'Completed'], 'game_2': []})

    def test_tags_limit_the_update_to_the_tagged_games(self):
        self.update(api(self.TAGS), tags=['favorites'])
        self.assertEqual(sorted(self.names()), ['game_0', 'game_1'])

    def test_skiptags_leave_games_out(self):
        self.update(api(self.TAGS), skiptags=['Completed'])
        self.assertEqual(sorted(self.names()), ['game_0', 'game_2'])

    def test_tags_and_skiptags_together(self):
        self.update(api(self.TAGS), tags=['Favorites'], skiptags=['Completed'])
        self.assertEqual(sorted(self.names()), ['game_0'])

    def test_the_tags_of_games_that_are_not_fetched_again_are_refreshed(self):
        self.update(api(self.TAGS))
        self.update(api({0: ['12'], 1: [], 2: ['11']}), full=False)       # nothing new, nothing updated
        self.assertEqual(self.names(), {'game_0': ['NEXT TO PLAY'], 'game_1': [], 'game_2': ['Favorites']})

    def test_a_tag_limited_update_never_removes_games_from_the_manifest(self):
        self.update(api(self.TAGS))
        # game_2 has left the account. A normal full update removes it from the manifest (the control) ...
        self.update(api(self.TAGS, only=(0, 1)))
        self.assertEqual(sorted(self.names()), ['game_0', 'game_1'])
        # ... but a tag-limited one must not remove anything
        g.run_report.reset()
        self.update(api(self.TAGS))                                         # game_2 is back
        self.update(api(self.TAGS, only=(0, 1)), tags=['Favorites'])
        self.assertEqual(sorted(self.names()), ['game_0', 'game_1', 'game_2'])
        self.update(api(self.TAGS, only=(0, 1)), skiptags=['Completed'])
        self.assertEqual(sorted(self.names()), ['game_0', 'game_1', 'game_2'])

    def test_a_tag_that_is_not_in_the_library_fails_the_run(self):
        with self.assertLogs('gogrepoc', level='ERROR'):
            self.update(api(self.TAGS), tags=['Nope'])
        self.assertEqual([why for _, why in g.run_report.failures], ['no such tag'])

    def test_a_tag_without_games_is_not_an_error(self):
        self.update(api({0: ['11']}), tags=['Completed'])       # the tag exists in the library, no game has it
        self.assertEqual(g.run_report.failures, [])
        self.assertEqual(g.load_manifest(), [])


if __name__ == '__main__':
    unittest.main()
