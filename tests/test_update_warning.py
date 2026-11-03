"""The warning when an update is about to narrow the manifest: an update replaces the installers of every game it fetches by the ones for
the chosen operating systems and languages, so entries for the others disappear (the files stay on disk, 'clean' would then see them as
orphans, and a later full update re-adds the entries as new ones). This was found in a real log; the update only warns."""
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g

ALL_OS = ['windows', 'linux', 'mac']


def entry(name, os_type='windows', lang='English'):
    return g.AttrDict(name=name, os_type=os_type, lang=lang, size=10, md5=None)


def game(id, title, downloads, galaxy=None, shared=None):
    item = g.AttrDict(id=id, title=title, long_title=title, folder_name=title, downloads=downloads, extras=[])
    if galaxy is not None:
        item.galaxyDownloads = galaxy
    if shared is not None:
        item.sharedDownloads = shared
    return item


def library():
    return [
        game(1, 'alpha', [entry('a_w_en', 'windows', 'English'), entry('a_m_en', 'mac', 'English'), entry('a_l_en', 'linux', 'English')]),
        game(2, 'beta', [entry('b_w_en', 'windows', 'English'), entry('b_w_de', 'windows', 'Deutsch')]),
        game(3, 'gamma', [entry('g_w_en', 'windows', 'English')]),
        game(4, 'delta', [entry('d_w_en', 'windows', 'English')], galaxy=[entry('d_gal_w_en', 'windows', 'English'), entry('d_gal_m_en', 'mac', 'English')],
             shared=[entry('d_sh_m_en', 'mac', 'English')]),
    ]


class NarrowingTests(unittest.TestCase):
    def narrowing(self, os_list, lang_list, fallback=None, ids=(), skipids=(), items=None):
        return g.update_narrowing(items if items is not None else library(), os_list, lang_list, fallback, list(ids), list(skipids))

    def test_an_update_that_keeps_everything_narrows_nothing(self):
        found = self.narrowing(ALL_OS, ['en', 'de'])
        self.assertEqual((found.files, found.games), (0, 0))

    def test_leaving_out_an_operating_system_drops_its_installers(self):
        found = self.narrowing(['windows', 'linux'], ['en', 'de'])
        self.assertEqual(found.os_types, {'mac'})
        self.assertEqual(found.languages, set())
        self.assertEqual((found.files, found.games), (3, 2))        # alpha's mac installer, delta's galaxy and shared mac installers

    def test_a_strict_language_drops_the_other_languages(self):
        found = self.narrowing(ALL_OS, ['de'])
        self.assertEqual(found.languages, {'English'})
        self.assertEqual(found.os_types, set())
        # alpha 3 (no German at all), beta's English, gamma's, and delta's 4 installers: all of them are English
        self.assertEqual(found.games, 4)
        self.assertEqual(found.files, 3 + 1 + 1 + 4)

    def test_the_english_fallback_of_the_default_language_keeps_what_has_no_german(self):
        found = self.narrowing(ALL_OS, ['de'], fallback='en')
        self.assertEqual((found.files, found.games), (1, 1))        # only beta's English installer: it has a German one
        self.assertEqual(found.languages, {'English'})

    def test_operating_system_and_language_together(self):
        found = self.narrowing(['windows'], ['en'])
        self.assertEqual(found.os_types, {'mac', 'linux'})
        self.assertEqual(found.languages, {'Deutsch'})
        self.assertEqual(found.files, 2 + 1 + 2)                    # alpha mac and linux, beta's German, delta's galaxy and shared mac

    def test_ids_limit_it_to_the_games_that_would_be_fetched(self):
        found = self.narrowing(['windows'], ['en', 'de'], ids=['alpha'])
        self.assertEqual((found.files, found.games), (2, 1))
        found = self.narrowing(['windows'], ['en', 'de'], ids=['2', 'gamma'])                  # beta and gamma have nothing outside
        self.assertEqual((found.files, found.games), (0, 0))

    def test_ids_may_be_written_as_the_name_on_gog(self):
        self.assertEqual(self.narrowing(['windows'], ['en', 'de'], ids=['ALPHA']).games, 1)

    def test_skipids_leave_games_out(self):
        found = self.narrowing(['windows'], ['en', 'de'], skipids=['alpha', 'delta'])
        self.assertEqual((found.files, found.games), (0, 0))

    def test_an_id_that_is_not_in_the_manifest_is_ignored_here(self):
        found = self.narrowing(['windows'], ['en', 'de'], ids=['a_new_game_not_in_the_manifest'])
        self.assertEqual((found.files, found.games), (0, 0))

    def test_old_manifests_without_galaxy_and_shared_lists_work(self):
        items = [game(9, 'old', [entry('o_m', 'mac')])]
        found = self.narrowing(['windows'], ['en'], items=items)
        self.assertEqual((found.files, found.games), (1, 1))

    def test_extras_are_not_touched_because_updates_do_not_filter_them(self):
        items = [game(9, 'x', [entry('x_w')])]
        items[0].extras = [g.AttrDict(name='manual.pdf', size=1)]
        self.assertEqual(self.narrowing(['windows'], ['en'], items=items).files, 0)

    def test_nothing_to_compare_nothing_found(self):
        self.assertEqual(self.narrowing(['windows'], ['en'], items=[]).files, 0)
        self.assertEqual(self.narrowing([], ['en']).files, 0)         # no operating system given: no restriction is known
        self.assertEqual(self.narrowing(['windows'], []).files, 0)


class WarningTests(unittest.TestCase):
    def warn(self, os_list, lang_list, fallback=None, ids=(), skipids=(), partial=True):
        with self.assertLogs('gogrepoc', level='DEBUG') as logs:
            g.warn_if_update_narrows_manifest(library(), os_list, lang_list, fallback, list(ids), list(skipids), partial)
            g.info('end of test')
        return [r for r in logs.records if r.levelname == 'WARNING'], '\n'.join(r.getMessage() for r in logs.records if r.levelname == 'WARNING')

    def test_nothing_is_said_when_nothing_is_narrowed(self):
        records, text = self.warn(ALL_OS, ['en', 'de'])
        self.assertEqual(records, [])

    def test_the_warning_names_what_is_dropped_how_much_and_what_to_do(self):
        records, text = self.warn(['windows', 'linux'], ['en', 'de'])
        for part in ('limited to operating system(s) windows, linux and language(s) en, de', '3 installer file(s) of 2 game(s)',
                     'operating system(s) mac', "'clean'", '!orphaned', 'added back as new entries', 'Ctrl-C', '-os', '-lang'):
            self.assertIn(part, text)
        self.assertGreaterEqual(len(records), 2)

    def test_a_language_is_named_when_it_is_the_language_that_narrows(self):
        records, text = self.warn(ALL_OS, ['de'])
        self.assertIn('language(s) English', text)
        self.assertNotIn('operating system(s) mac', text)

    def test_both_reasons_are_named_together(self):
        records, text = self.warn(['windows'], ['en'])
        self.assertIn('operating system(s) linux, mac', text)
        self.assertIn('language(s) Deutsch', text)

    def test_a_partial_update_says_up_to_and_a_full_one_does_not(self):
        partial = self.warn(['windows'], ['en', 'de'], partial=True)[1]
        full = self.warn(['windows'], ['en', 'de'], partial=False)[1]
        self.assertIn('up to', partial)
        self.assertNotIn('up to', full)
        self.assertIn('every game', full)

    def test_it_only_warns_it_does_not_stop_anything(self):
        self.warn(['windows'], ['en'])        # returns normally; no exit, no question

    def test_the_figures_follow_ids(self):
        records, text = self.warn(['windows'], ['en', 'de'], ids=['alpha'])
        self.assertIn('2 installer file(s) of 1 game(s)', text)


class UpdateStartTests(unittest.TestCase):
    """cmd_update calls the check once, with the lists it is going to use, and only for a new update (not when it resumes one)."""

    def run_update(self, resume):
        class Resp(object):
            def json(self_inner):
                return {'products': [], 'totalPages': 1}
        resumeprops = {'complete': False, 'resume_manifest_syntax_version': g.RESUME_MANIFEST_SYNTAX_VERSION, 'os_list': ['mac'],
                       'lang_list': ['fr'], 'lang_fallback': None, 'installers': 'standalone', 'strict': False}
        patches = [mock.patch.object(g, 'load_manifest', lambda *a, **k: library()),
                   mock.patch.object(g, 'makeGOGSession', lambda *a, **k: object()),
                   mock.patch.object(g, 'request', lambda *a, **k: Resp()),
                   mock.patch.object(g, 'save_manifest'), mock.patch.object(g, 'save_resume_manifest')]
        if resume:      # an interrupted update with no games left to fetch; once it is done, the next update is a fresh one
            patches.append(mock.patch.object(g, 'load_resume_manifest', side_effect=[[resumeprops], IOError('none')]))
        else:
            patches.append(mock.patch.object(g, 'load_resume_manifest', side_effect=IOError('none')))
        spy = mock.Mock()
        patches.append(mock.patch.object(g, 'warn_if_update_narrows_manifest', spy))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        try:
            with self.assertLogs('gogrepoc', level='DEBUG'):
                g.cmd_update(['windows'], ['en'], False, False, True, ['alpha'], ['beta'], False, 'standalone', 'resume', False, True, True, False,
                             True, False, False, lang_fallback='en')
                g.info('end of test')
        except SystemExit:
            pass
        return spy

    def test_a_new_update_checks_with_the_lists_it_will_use(self):
        spy = self.run_update(resume=False)
        spy.assert_called_once()
        args = spy.call_args[0]
        self.assertEqual(args[1:], (['windows'], ['en'], 'en', ['alpha'], ['beta'], True))

    def test_resuming_an_interrupted_update_does_not_warn_for_the_lists_of_the_resumed_one(self):
        # the resumed update was decided earlier; but when it is done, cmd_update starts the update that was asked for, and that one is checked
        spy = self.run_update(resume=True)
        spy.assert_called_once()
        self.assertEqual(spy.call_args[0][1:3], (['windows'], ['en']))          # the lists that were typed, not the resumed ['mac'] / ['fr']


if __name__ == '__main__':
    unittest.main()
