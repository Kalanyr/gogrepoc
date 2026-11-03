"""Finding games by id or name: normalize_name, resolve_game_ids (-ids / -skipids), suggest_games, search_games, the list command,
and the way download, verify, import and backup use them.

The library is a small made-up manifest with the kinds of titles a real one has: long titles with years and colons, trade mark
signs, apostrophes, accents, Japanese, two games that can be told apart only by their id, and names that are alike."""
import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as g


def make_game(id, title, long_title=None, os_type='windows', lang='English', size=1000, extras=0, **more):
    game = g.AttrDict(id=id, title=title, long_title=long_title if long_title is not None else title, folder_name=title,
                      downloads=[g.AttrDict(name='setup_%s.exe' % title, lang=lang, os_type=os_type, size=size, md5=None,
                                            unpack_url=None, manual_url='/x/%s' % title)],
                      galaxyDownloads=[], sharedDownloads=[],
                      extras=[g.AttrDict(name='extra%d_%s.zip' % (n, title), size=10, md5=None, manual_url='/e') for n in range(extras)])
    game.update(more)
    return game


ALL_OS = ['windows', 'linux', 'mac']      # a real run always has an operating system list (this computer's by default)


def library():
    return [
        make_game(1207658695, 'beneath_a_steel_sky', 'Beneath a Steel Sky (1994)', lang='Deutsch', extras=2, size=5000),
        make_game(1207658924, 'the_witcher_enhanced_edition', 'The Witcher: Enhanced Edition', os_type='linux'),
        make_game(1207658930, 'the_witcher_2_assassins_of_kings', 'The Witcher 2: Assassins of Kings Enhanced Edition'),
        make_game(1971477531, 'gwent_the_witcher_card_game', 'GWENT: The Witcher Card Game'),
        make_game(1207666073, 'akalabeth_world_of_doom', 'Akalabeth: World of Doom'),
        make_game(1207666080, 'ultima_iv_quest_of_the_avatar', 'Ultima\u2122 IV: Quest of the Avatar', os_type='mac'),
        make_game(1207666090, 'baldurs_gate_enhanced_edition', "Baldur's Gate: Enhanced Edition"),
        make_game(1207666100, 'cafe_racer', 'Caf\u00e9 Racer'),
        make_game(1207666110, 'gakkou', '\u304c\u3063\u3053\u3046'),            # the Japanese word "gakkou", with a voiced mark
        make_game(1207666120, 'kakkou', '\u304b\u3063\u3053\u3046'),            # "kakkou": the same without it, a different game
        make_game(1207666130, 'dune', 'Dune'),
        make_game(1207666140, 'dune_remaster', 'Dune!'),
    ]


class NormalizeTests(unittest.TestCase):
    def test_case_underscores_and_punctuation_do_not_matter(self):
        self.assertEqual(g.normalize_name('Beneath a Steel Sky (1994)'), 'beneath a steel sky 1994')
        self.assertEqual(g.normalize_name('beneath_a_steel_sky'), 'beneath a steel sky')
        self.assertEqual(g.normalize_name('  Akalabeth:   World -- of Doom!! '), 'akalabeth world of doom')

    def test_the_name_on_gog_and_the_title_become_the_same(self):
        self.assertEqual(g.normalize_name('Ultima\u2122 IV: Quest of the Avatar'), g.normalize_name('ultima_iv_quest_of_the_avatar'))
        self.assertEqual(g.normalize_name("Baldur's Gate"), g.normalize_name('baldurs_gate'))
        self.assertEqual(g.normalize_name('Baldur\u2019s Gate'), g.normalize_name('baldurs_gate'))
        self.assertEqual(g.normalize_name('Caf\u00e9'), 'cafe')

    def test_accents_on_latin_letters_go_other_scripts_stay_as_they_are(self):
        self.assertEqual(g.normalize_name('\u00c5ngstr\u00f6m'), 'angstrom')
        self.assertEqual(g.normalize_name('Stra\u00dfe'), 'strasse')
        self.assertNotEqual(g.normalize_name('\u304c\u3063\u3053\u3046'), g.normalize_name('\u304b\u3063\u3053\u3046'))
        self.assertEqual(g.normalize_name('\u304c\u3063\u3053\u3046'), '\u304c\u3063\u3053\u3046')
        self.assertEqual(g.normalize_name('\u30c9\u30e9\u30b4\u30f3 Quest'), '\u30c9\u30e9\u30b4\u30f3 quest')
        self.assertEqual(g.normalize_name('\u4e2d\u6587\u6e38\u620f'), '\u4e2d\u6587\u6e38\u620f')

    def test_look_alike_forms_are_the_same(self):
        self.assertEqual(g.normalize_name('\u2163'), 'iv')                  # roman numeral four in one character
        self.assertEqual(g.normalize_name('\uff21\uff22\uff23'), 'abc')     # full-width letters

    def test_nothing_left_is_an_empty_name(self):
        for text in ('', '   ', '!!!', '\u2122', "'"):
            self.assertEqual(g.normalize_name(text), '', repr(text))

    def test_normalising_twice_changes_nothing(self):
        for text in ('Beneath a Steel Sky (1994)', "Baldur's Gate", '\u304c\u3063\u3053\u3046', 'Caf\u00e9'):
            once = g.normalize_name(text)
            self.assertEqual(g.normalize_name(once), once)

    def test_numbers_are_kept(self):
        self.assertEqual(g.normalize_name('The Witcher 2'), 'the witcher 2')
        self.assertNotEqual(g.normalize_name('The Witcher 2'), g.normalize_name('The Witcher'))


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.items = library()

    def resolve(self, *ids, **kw):
        return g.resolve_game_ids(self.items, list(ids), **kw)

    def titles(self, result):
        return sorted(game.title for game in self.items if game.id in result.selected)

    def test_an_exact_title_or_id_selects_the_game_as_always(self):
        result = self.resolve('beneath_a_steel_sky', '1207658924')
        self.assertEqual(self.titles(result), ['beneath_a_steel_sky', 'the_witcher_enhanced_edition'])
        self.assertEqual((result.notes, result.problems), ([], []))

    def test_the_name_as_shown_on_gog_selects_the_game_and_says_so(self):
        result = self.resolve('Beneath a Steel Sky (1994)')
        self.assertEqual(self.titles(result), ['beneath_a_steel_sky'])
        self.assertEqual(result.problems, [])
        self.assertEqual(len(result.notes), 1)
        for part in ("-ids 'Beneath a Steel Sky (1994)'", 'beneath_a_steel_sky', '1207658695'):
            self.assertIn(part, result.notes[0])

    def test_other_spellings_of_the_name_select_it_too(self):
        for text in ('BENEATH_A_STEEL_SKY', 'beneath a steel sky', 'Ultima IV: Quest of the Avatar', 'ULTIMA\u2122 IV Quest of the avatar',
                     "baldur's gate enhanced edition", 'Baldurs Gate Enhanced Edition', 'cafe racer', 'Caf\u00e9 Racer', '  cafe_racer '):
            result = self.resolve(text)
            self.assertEqual(len(result.selected), 1, text)
            self.assertEqual(result.problems, [], text)

    def test_an_exact_title_wins_over_a_name_that_only_looks_the_same(self):
        self.items.append(make_game(5, 'other_game', 'dune'))              # its long title is the title of another game
        result = self.resolve('dune')
        self.assertEqual(self.titles(result), ['dune'])
        self.assertEqual(result.notes, [])

    def test_a_name_that_fits_two_games_selects_neither_and_names_both(self):
        result = self.resolve('DUNE')                                       # not an exact title; fits 'dune' and 'dune_remaster'
        self.assertEqual(result.selected, set())
        self.assertEqual(len(result.problems), 1)
        what, why, message = result.problems[0]
        self.assertEqual((what, why), ('-ids DUNE', 'could be several games'))
        for part in ('dune (id 1207666130', 'dune_remaster (id 1207666140', 'use the id or the exact title'):
            self.assertIn(part, message)

    def test_a_game_is_never_selected_because_it_looks_a_bit_like_the_text(self):
        for text in ('Witcer', 'steel', 'beneath', 'the witcher 3', 'Akalabeth World of Doom 2', 'ultima'):
            result = self.resolve(text)
            self.assertEqual(result.selected, set(), text)
            self.assertEqual(len(result.problems), 1, text)

    def test_a_typo_is_a_problem_with_suggestions(self):
        result = self.resolve('Witcer 2')
        what, why, message = result.problems[0]
        self.assertEqual((what, why), ('-ids Witcer 2', 'no such game'))
        self.assertIn("-ids 'Witcer 2' matches no game in the manifest. Did you mean: the_witcher_2_assassins_of_kings (id 1207658930",
                      message)

    def test_nothing_alike_points_to_the_list_command(self):
        result = self.resolve('zzzzqqqq')
        self.assertIn("'list' shows the games", result.problems[0][2])
        self.assertNotIn('Did you mean', result.problems[0][2])

    def test_a_number_that_is_no_game_has_no_suggestions(self):
        result = self.resolve('999')
        self.assertEqual(len(result.problems), 1)
        self.assertNotIn('Did you mean', result.problems[0][2])

    def test_the_words_of_one_name_typed_without_quotes_are_recognised(self):
        result = self.resolve('Beneath', 'a', 'Steel', 'Sky')
        self.assertEqual(result.selected, set())            # reported, not guessed
        self.assertEqual(len(result.problems), 1)           # one message, not one per word
        what, why, message = result.problems[0]
        self.assertEqual((what, why), ('-ids Beneath a Steel Sky', 'name typed without quotes'))
        for part in ("'Beneath' 'a' 'Steel' 'Sky'", 'beneath_a_steel_sky (id 1207658695', 'must be in quotes: -ids "Beneath a Steel Sky"'):
            self.assertIn(part, message)

    def test_unquoted_words_next_to_other_ids(self):
        result = self.resolve('xyzzy1', 'Akalabeth', 'World', 'of', 'Doom', 'dune')
        whats = sorted(p[0] for p in result.problems)
        self.assertEqual(whats, ['-ids Akalabeth World of Doom', '-ids xyzzy1'])
        self.assertEqual(self.titles(result), ['dune'])

    def test_words_that_do_not_make_up_a_name_are_not_joined(self):
        result = self.resolve('Steel', 'Sky')                # 'steel sky' is part of a name, not a name
        self.assertEqual(sorted(p[1] for p in result.problems), ['no such game', 'no such game'])

    def test_a_game_that_is_found_in_the_middle_splits_the_run(self):
        result = self.resolve('Beneath', 'dune', 'a', 'Steel', 'Sky')
        self.assertEqual(self.titles(result), ['dune'])
        self.assertEqual(sorted(p[1] for p in result.problems), ['no such game', 'no such game', 'no such game', 'no such game'])

    def test_the_option_name_is_in_the_messages(self):
        result = self.resolve('Witcer', option='-skipids')
        self.assertTrue(result.problems[0][0].startswith('-skipids '))
        self.assertIn("-skipids 'Witcer'", result.problems[0][2])
        self.assertIn('-skipids', self.resolve('Beneath', 'a', 'Steel', 'Sky', option='-skipids').problems[0][2])

    def test_nothing_asked_nothing_found(self):
        result = self.resolve()
        self.assertEqual((result.selected, result.notes, result.problems), (set(), [], []))

    def test_ids_may_be_numbers(self):
        self.assertEqual(self.titles(self.resolve(1207658695)), ['beneath_a_steel_sky'])

    def test_asking_for_the_same_game_twice_is_fine(self):
        result = self.resolve('dune', 'dune', '1207666130')
        self.assertEqual((self.titles(result), result.problems), (['dune'], []))

    def test_two_japanese_names_that_differ_by_a_voiced_mark_stay_apart(self):
        self.assertEqual(self.titles(self.resolve('\u304c\u3063\u3053\u3046')), ['gakkou'])
        self.assertEqual(self.titles(self.resolve('\u304b\u3063\u3053\u3046')), ['kakkou'])

    def test_games_without_a_long_title_work(self):
        item = g.AttrDict(id=7, title='plain_game')
        result = g.resolve_game_ids([item], ['PLAIN game', 'plain_game'])
        self.assertEqual((result.selected, result.problems), ({7}, []))


class SuggestTests(unittest.TestCase):
    def setUp(self):
        self.items = library()

    def titles(self, query, **kw):
        return [game.title for game in g.suggest_games(self.items, query, **kw)]

    def test_typos_are_suggested(self):
        self.assertEqual(self.titles('Witcer 2')[0], 'the_witcher_2_assassins_of_kings')
        self.assertEqual(self.titles('akalabth')[0], 'akalabeth_world_of_doom')
        self.assertEqual(self.titles('stell sky')[0], 'beneath_a_steel_sky')

    def test_part_of_a_name_and_other_word_order_are_suggested(self):
        self.assertEqual(self.titles('sky steel'), ['beneath_a_steel_sky'])
        self.assertIn('ultima_iv_quest_of_the_avatar', self.titles('avatar quest'))

    def test_best_first_and_at_most_the_limit(self):
        found = self.titles('witcher')
        self.assertEqual(len(found), g.SUGGESTION_LIMIT)
        self.assertEqual(len(self.titles('witcher', limit=2)), 2)
        self.assertEqual(self.titles('the witcher 2')[0], 'the_witcher_2_assassins_of_kings')

    def test_the_order_is_the_same_every_time(self):
        self.assertEqual(self.titles('witcher'), self.titles('witcher'))
        self.assertEqual(self.titles('witcher'), sorted(self.titles('witcher'), key=lambda t: 0))   # no randomness: just stable

    def test_nothing_alike_gives_nothing(self):
        for text in ('zzzzqqqq', 'qwertyuiop', '12345678'):
            self.assertEqual(self.titles(text), [], text)

    def test_very_short_or_empty_queries_give_nothing(self):
        for text in ('', 'a', 'it', '!!!', '  '):
            self.assertEqual(self.titles(text), [], repr(text))

    def test_japanese(self):
        self.assertEqual(self.titles('\u304c\u3063\u3053'), ['gakkou'])
        self.assertEqual(self.titles('\u304b\u3063\u3053'), ['kakkou'])

    def test_a_large_library_is_not_slow(self):
        import time
        big = [make_game(i, 'game_number_%d_of_the_big_library' % i, 'Game Number %d of the Big Library' % i) for i in range(3000)]
        start = time.time()
        g.suggest_games(big, 'game numbr 2999 of the big libary')
        self.assertLess(time.time() - start, 15)


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.items = library()

    def titles(self, *words):
        return [game.title for game in g.search_games(self.items, words)]

    def test_without_words_all_games_by_title(self):
        found = self.titles()
        self.assertEqual(len(found), len(self.items))
        self.assertEqual(found, sorted(found))
        self.assertEqual(self.titles(''), found)
        self.assertEqual(self.titles(' ', ''), found)

    def test_all_words_must_be_found_in_any_order(self):
        self.assertEqual(self.titles('witcher', '2'), ['the_witcher_2_assassins_of_kings'])
        self.assertEqual(self.titles('sky', 'steel'), ['beneath_a_steel_sky'])
        self.assertEqual(self.titles('witcher', 'card'), ['gwent_the_witcher_card_game'])
        self.assertEqual(self.titles('witcher', 'dune'), [])

    def test_case_accents_and_punctuation_do_not_matter(self):
        self.assertEqual(self.titles('CAFE'), ['cafe_racer'])
        self.assertEqual(self.titles('caf\u00e9'), ['cafe_racer'])
        self.assertEqual(self.titles("baldur's"), ['baldurs_gate_enhanced_edition'])
        self.assertEqual(self.titles('ultima\u2122', 'iv'), ['ultima_iv_quest_of_the_avatar'])

    def test_a_part_of_a_word_matches(self):
        self.assertEqual(self.titles('steel'), ['beneath_a_steel_sky'])
        self.assertEqual(self.titles('witch'), ['gwent_the_witcher_card_game', 'the_witcher_2_assassins_of_kings', 'the_witcher_enhanced_edition'])

    def test_the_best_matches_come_first(self):
        found = self.titles('dune')
        self.assertEqual(found, ['dune', 'dune_remaster'])
        self.items.append(make_game(9, 'a_dune_adventure', 'A Dune Adventure'))    # sorts first by title, but only contains the word
        self.items.append(make_game(10, 'dunes_of_war', 'Dunes of War'))
        self.assertEqual(self.titles('dune'), ['dune', 'dune_remaster', 'dunes_of_war', 'a_dune_adventure'])   # exact, starts with, contains

    def test_the_id_can_be_searched_with_four_or_more_digits(self):
        self.assertEqual(self.titles('1207658695'), ['beneath_a_steel_sky'])
        self.assertEqual(self.titles('12076586'), ['beneath_a_steel_sky'])
        self.assertEqual(self.titles('2'), ['the_witcher_2_assassins_of_kings'])    # a short number is only looked for in the names
        self.assertEqual(self.titles('123'), [])

    def test_only_punctuation_matches_nothing(self):
        self.assertEqual(self.titles('!!!'), [])
        self.assertEqual(self.titles('(', ')'), [])

    def test_no_match_is_an_empty_list(self):
        self.assertEqual(self.titles('zzzz'), [])


class ScreenTextTests(unittest.TestCase):
    def test_width_on_the_screen(self):
        self.assertEqual(g._display_width('abc'), 3)
        self.assertEqual(g._display_width('\u304c\u3063\u3053\u3046'), 8)            # Japanese: two columns each
        self.assertEqual(g._display_width('e\u0301'), 1)                              # letter with a combining accent
        self.assertEqual(g._display_width(''), 0)

    def test_cutting_to_a_width(self):
        self.assertEqual(g._fit('short', 10), 'short')
        self.assertEqual(g._fit('a very long game name', 10), 'a very ...')
        cut = g._fit('\u304c\u3063\u3053\u3046\u304c\u3063\u3053\u3046', 9)
        self.assertLessEqual(g._display_width(cut), 9)
        self.assertTrue(cut.endswith('...'))
        self.assertEqual(g._fit('ab', 2), 'ab')

    def test_padding_by_width_on_the_screen(self):
        self.assertEqual(g._pad('ab', 5), 'ab   ')
        self.assertEqual(g._pad('ab', 5, right=True), '   ab')
        self.assertEqual(g._display_width(g._pad('\u304c\u3063', 8)), 8)
        self.assertEqual(g._pad('toolong', 3), 'toolong')


class Tty(io.StringIO):
    def isatty(self):
        return True


class ListCommandTests(unittest.TestCase):
    def setUp(self):
        self.items = library()
        self.patches = [mock.patch.object(g, 'load_manifest', lambda *a, **k: self.items)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        g.run_report.reset('list')

    def run_list(self, *args, stdout=None, **kw):
        out = stdout or io.StringIO()
        with contextlib.redirect_stdout(out), self.assertLogs('gogrepoc', level='DEBUG') as logs:
            g.cmd_list(*args, **kw)
            g.info('end of test')
        return out.getvalue(), '\n'.join(logs.output)

    def lines(self, text):
        return text.splitlines()

    def test_all_games_in_a_table(self):
        out, log = self.run_list([], [], [], [], [])
        lines = self.lines(out)
        self.assertEqual(lines[0].split(), ['ID', 'TITLE', 'NAME', 'OS', 'LANG', 'FILES', 'SIZE'])
        self.assertEqual(len(lines), 1 + len(self.items))
        for game in self.items:
            self.assertEqual(sum(1 for l in lines if game.title in l), 1 if game.title not in ('dune',) else 2, game.title)
        self.assertIn('%d of %d games' % (len(self.items), len(self.items)), log)

    def test_one_row_shows_the_id_title_name_os_languages_files_and_size(self):
        out, log = self.run_list(['steel'], [], [], [], [])
        row = self.lines(out)[1]
        for part in ('1207658695', 'beneath_a_steel_sky', 'Beneath a Steel Sky (1994)', 'win', 'de', ' 3 ', '4.90KB'):
            self.assertIn(part, row)
        self.assertIn('1 of %d games' % len(self.items), log)

    def test_the_columns_line_up(self):
        out, log = self.run_list([], [], [], [], [])
        lines = self.lines(out)
        header = lines[0]
        starts = [header.index(h) for h in ('TITLE', 'NAME', 'OS')]
        for line in lines[1:]:
            if any(ord(c) > 0x2e80 for c in line):
                continue                                 # wide characters: character positions are not screen columns (own test)
            for start in starts:
                self.assertEqual(line[start - 2:start], '  ', line)

    def test_columns_line_up_with_japanese_names(self):
        out, log = self.run_list(['gakkou'], [], [], [], [])
        # the two games with Japanese names: every other column starts at the same place on the screen
        out2, log2 = self.run_list([], [], [], [], [])
        rows = [l for l in self.lines(out2)[1:] if 'gakkou' in l or 'kakkou' in l or 'cafe_racer' in l]
        positions = set()
        for row in rows:
            name = [g_.long_title for g_ in self.items if g_.title in row.split()][0]
            before = row[:row.index(name)]
            positions.add(g._display_width(before))
        self.assertEqual(len(positions), 1)

    def test_os_and_language_filters(self):
        out, log = self.run_list([], ['linux'], [], [], [])
        self.assertEqual([l.split()[1] for l in self.lines(out)[1:]], ['the_witcher_enhanced_edition'])
        out, log = self.run_list([], [], ['windows', 'linux'], [], [])
        self.assertEqual([l.split()[1] for l in self.lines(out)[1:]], ['ultima_iv_quest_of_the_avatar'])
        out, log = self.run_list([], [], [], ['de'], [])
        self.assertEqual([l.split()[1] for l in self.lines(out)[1:]], ['beneath_a_steel_sky'])
        out, log = self.run_list([], [], [], [], ['en'])
        self.assertEqual([l.split()[1] for l in self.lines(out)[1:]], ['beneath_a_steel_sky'])

    def test_search_words_and_filters_together(self):
        out, log = self.run_list(['witcher'], ['linux'], [], [], [])
        self.assertEqual([l.split()[1] for l in self.lines(out)[1:]], ['the_witcher_enhanced_edition'])

    def test_format_ids_prints_only_the_titles_one_per_line(self):
        out, log = self.run_list(['witcher'], [], [], [], [], output_format='ids')
        self.assertEqual(self.lines(out), ['gwent_the_witcher_card_game', 'the_witcher_2_assassins_of_kings', 'the_witcher_enhanced_edition'])
        out, log = self.run_list([], [], [], [], [], output_format='ids')
        self.assertEqual(self.lines(out), sorted(game.title for game in self.items))

    def test_the_list_itself_has_no_log_lines_in_it(self):
        out, log = self.run_list([], [], [], [], [])
        self.assertNotIn('|', out)
        self.assertNotIn('games', out.splitlines()[-1].lower())

    def test_nothing_found_gives_suggestions_and_a_failed_run(self):
        out, log = self.run_list(['Witcer'], [], [], [], [])
        self.assertEqual(out, '')
        self.assertIn("no game matches 'Witcer'. Did you mean:", log)
        self.assertIn('the_witcher', log)
        self.assertEqual(g.run_report.exit_status(), 1)

    def test_nothing_found_and_nothing_alike(self):
        out, log = self.run_list(['zzzzqqqq'], [], [], [], [])
        self.assertIn("no game matches 'zzzzqqqq'.", log)
        self.assertNotIn('Did you mean', log)
        self.assertEqual(g.run_report.exit_status(), 1)

    def test_words_that_match_games_which_the_filter_removed_say_so(self):
        # the game exists (beneath_a_steel_sky has German files only); the language filter takes it out of the list
        out, log = self.run_list(['steel'], [], [], ['en'], [])
        self.assertEqual(out, '')
        self.assertIn("1 game matches 'steel' (beneath_a_steel_sky)", log)
        self.assertIn('but none has files for the chosen operating system / language', log)
        self.assertNotIn('no game matches', log)
        self.assertNotIn('Did you mean', log)
        self.assertEqual(g.run_report.exit_status(), 1)
        self.assertEqual([f[0] for f in g.run_report.failures], ['list steel'])

    def test_the_active_filter_is_named_so_that_a_filter_from_the_config_file_is_not_a_surprise(self):
        out, log = self.run_list(['steel'], ['linux', 'mac'], [], ['en'], [])
        self.assertIn('-os linux mac', log)
        self.assertIn('-lang en', log)
        self.assertIn('config file', log)
        out, log = self.run_list(['steel'], [], ['windows'], [], ['de'])
        self.assertIn('-skipos windows', log)
        self.assertIn('-skiplang de', log)

    def test_several_filtered_out_games_are_counted_and_only_the_first_are_named(self):
        for n in range(8):
            self.items.append(make_game(500 + n, 'ultima_%d' % n, 'Ultima %d' % n, os_type='mac'))
        out, log = self.run_list(['ultima'], ['windows'], [], [], [])
        self.assertIn("9 games match 'ultima'", log)                 # the 8 new ones and ultima_iv_quest_of_the_avatar
        self.assertIn('and 4 more', log)                              # five are named
        self.assertEqual(out, '')

    def test_words_that_match_no_game_at_all_still_get_suggestions_from_all_games_when_a_filter_is_set(self):
        out, log = self.run_list(['Witcer'], ['mac'], [], [], [])
        self.assertIn("no game matches 'Witcer'. Did you mean:", log)
        self.assertIn('the_witcher', log)
        self.assertEqual(g.run_report.exit_status(), 1)

    def test_a_filter_that_leaves_nothing_names_the_filter(self):
        out, log = self.run_list([], ['mac'], [], ['de'], [])
        self.assertIn('no game has files for this operating system / language', log)
        self.assertIn('-os mac', log)
        self.assertIn('-lang de', log)

    def test_games_that_pass_the_filter_are_listed_as_before(self):
        out, log = self.run_list(['steel'], [], [], ['de'], [])
        self.assertIn('beneath_a_steel_sky', out)
        self.assertEqual(g.run_report.exit_status(), 0)

    def test_a_filter_that_leaves_nothing_is_a_failed_run(self):
        out, log = self.run_list([], ['mac'], [], ['de'], [])
        self.assertEqual(out, '')
        self.assertIn('no game has files for this operating system / language', log)
        self.assertEqual(g.run_report.exit_status(), 1)

    def test_an_empty_manifest_is_not_a_failure(self):
        self.items[:] = []
        out, log = self.run_list([], [], [], [], [])
        self.assertEqual(out, '')
        self.assertIn('the manifest has no games', log)
        self.assertEqual(g.run_report.exit_status(), 0)

    def test_a_successful_list_is_not_a_failure(self):
        self.run_list(['dune'], [], [], [], [])
        self.assertEqual(g.run_report.exit_status(), 0)

    def test_on_a_screen_the_table_is_made_to_fit(self):
        self.items.append(make_game(77, 'a_game_with_a_very_long_title_' + 'x' * 40, 'A game with a very long name ' + 'y' * 80))
        with mock.patch.object(g.shutil, 'get_terminal_size', lambda fallback=None: os.terminal_size((80, 24))):
            out, log = self.run_list([], [], [], [], [], stdout=Tty())
        for line in self.lines(out):
            self.assertLessEqual(g._display_width(line), 79, line)
        self.assertIn('...', out)

    def test_not_on_a_screen_nothing_is_cut(self):
        long_name = 'A game with a very long name ' + 'y' * 80
        self.items.append(make_game(77, 'long_one', long_name))
        out, log = self.run_list([], [], [], [], [])
        self.assertIn(long_name, out)
        self.assertNotIn('...', out)

    def test_extras_count_as_files_and_in_the_size(self):
        out, log = self.run_list(['steel'], [], [], [], [])
        self.assertIn(' 3 ', self.lines(out)[1])                  # one installer and two extras

    def test_old_manifests_without_galaxy_or_shared_lists_work(self):
        old = g.AttrDict(id=3, title='old_game', long_title='Old Game', downloads=[g.AttrDict(name='a', lang='English', os_type='windows', size=1)],
                         extras=[])
        self.items.append(old)
        out, log = self.run_list(['old'], [], [], [], [])
        self.assertIn('old_game', out)


class ListMainTests(unittest.TestCase):
    """The command through main(): where the table and the messages go."""

    def setUp(self):
        previous = g.consoleHandler.stream
        self.addCleanup(g.consoleHandler.setStream, previous)
        g.rootLogger.addHandler(g.consoleHandler)                  # the test bootstrap takes it off to keep the output quiet
        self.addCleanup(g.rootLogger.removeHandler, g.consoleHandler)
        patcher = mock.patch.object(g, 'load_manifest', lambda *a, **k: library())
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_main(self, *argv):
        args = g.process_argv(['gogrepo_delta.py', 'list'] + list(argv) + ['-nolog'])
        out, err = io.StringIO(), io.StringIO()
        g.consoleHandler.setStream(out)           # what the console handler writes to before main redirects it (stdout)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = g.main(args)
        return status, out.getvalue(), err.getvalue()

    def test_the_table_is_on_stdout_and_the_messages_are_on_stderr(self):
        status, out, err = self.run_main('witcher')
        self.assertEqual(status, 0)
        self.assertIn('the_witcher_2_assassins_of_kings', out)
        self.assertNotIn('total time', out)
        self.assertNotIn('|', out)
        self.assertIn('total time', err)
        self.assertIn('3 of 12 games', err)

    def test_exit_status_is_1_when_nothing_matches(self):
        status, out, err = self.run_main('Witcer')
        self.assertEqual((status, out), (1, ''))
        self.assertIn('Did you mean', err)

    def test_the_options_reach_the_command(self):
        status, out, err = self.run_main('-os', 'linux', '-format', 'ids')
        self.assertEqual(out.split(), ['the_witcher_enhanced_edition'])

    def test_unknown_os_or_language_is_refused(self):
        for bad in (['-os', 'amiga'], ['-lang', 'xx']):
            with self.assertRaises(SystemExit), self.assertLogs('gogrepoc', level='ERROR'):
                g.process_argv(['gogrepo_delta.py', 'list'] + bad + ['-nolog'])

    def test_os_and_skipos_exclude_each_other(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            g.process_argv(['gogrepo_delta.py', 'list', '-os', 'linux', '-skipos', 'mac', '-nolog'])

    def test_the_words_go_before_the_options(self):
        a = g.process_argv(['gogrepo_delta.py', 'list', 'steel', 'sky', '-os', 'windows', '-nolog'])
        self.assertEqual((a.words, a.os), (['steel', 'sky'], ['windows']))
        b = g.process_argv(['gogrepo_delta.py', 'list', '-format', 'ids', 'steel', 'sky', '-nolog'])      # after an option with one value
        self.assertEqual((b.words, b.format), (['steel', 'sky'], 'ids'))

    def test_words_after_an_option_that_takes_several_values_are_taken_as_its_values(self):
        # -os takes any number of values, so 'steel' and 'sky' here are operating systems (and are refused as such)
        with self.assertRaises(SystemExit), self.assertLogs('gogrepoc', level='ERROR'):
            g.process_argv(['gogrepo_delta.py', 'list', '-os', 'windows', 'steel', 'sky', '-nolog'])


class ListWithConfigTests(unittest.TestCase):
    """With a config file present the command line is read twice; several words must still work."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='listcfg_')
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.path = os.path.join(self.dir, 'gogrepo_delta.cfg')
        patcher = mock.patch.dict(os.environ, {g.USER_CONFIG_ENV_VAR: self.path})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_several_words_with_a_config_file_present(self):
        for text in ('[common]\nos = linux\n', '[list]\nformat = ids\n', g.default_config_text(g.build_parser()[1])):
            with open(self.path, 'w', encoding='utf-8') as w:
                w.write(text)
            args = g.process_argv(['gogrepo_delta.py', 'list', 'steel', 'sky', 'x', '-nolog'])
            self.assertEqual(args.words, ['steel', 'sky', 'x'], text)

    def test_the_search_words_cannot_be_set_in_the_file(self):
        with open(self.path, 'w', encoding='utf-8') as w:
            w.write('[list]\nwords = witcher\n')
        with self.assertLogs('gogrepoc', level='WARNING') as logs:
            args = g.process_argv(['gogrepo_delta.py', 'list', '-nolog'])
        self.assertEqual(args.words, [])
        self.assertIn("no option 'words'", '\n'.join(logs.output))

    def test_the_format_can_be_set_in_the_file_and_os_is_shared_with_the_other_commands(self):
        with open(self.path, 'w', encoding='utf-8') as w:
            w.write('[list]\nformat = ids\n[common]\nos = linux\n')
        args = g.process_argv(['gogrepo_delta.py', 'list', '-nolog'])
        self.assertEqual((args.format, args.os), ('ids', ['linux']))
        self.assertEqual(g.process_argv(['gogrepo_delta.py', 'list', '-format', 'table', '-nolog']).format, 'table')

    def test_the_generated_file_has_a_list_section_with_the_format_only(self):
        text = g.default_config_text(g.build_parser()[1])
        section = text.split('[list]')[1].split('\n[')[0]
        self.assertIn('format = table', section)
        self.assertNotIn('words', section)
        self.assertNotIn('\nwords =', text)


class HookTests(unittest.TestCase):
    """-ids and -skipids in download, verify, import and backup."""

    def setUp(self):
        self.items = library()
        g.run_report.reset('test')
        self.dir = tempfile.mkdtemp(prefix='hooks_')
        self.addCleanup(shutil.rmtree, self.dir, True)
        saver = mock.patch.object(g, 'save_manifest')          # the commands save the manifest at the end: not into a real file
        saver.start()
        self.addCleanup(saver.stop)

    def select(self, ids=(), skipids=()):
        with self.assertLogs('gogrepoc', level='DEBUG') as logs:
            result = g._select_download_items(list(self.items), list(ids), list(skipids), [])
            g.info('end of test')
        self.log = '\n'.join(logs.output)
        return [game.title for game in result]

    def old_select(self, ids, skipids):
        """What the code did before: exact title or id only."""
        items = list(self.items)
        if ids:
            items = [i for i in items if i.title in ids or str(i.id) in ids]
        if skipids:
            items = [i for i in items if i.title not in skipids and str(i.id) not in skipids]
        return [i.title for i in items]

    # --- download ---

    def test_exact_ids_and_titles_select_exactly_what_they_did_before(self):
        cases = [(['dune'], []), (['1207658695', 'cafe_racer'], []), ([], ['dune', 'gakkou']), (['dune', 'cafe_racer', 'kakkou'], ['kakkou']),
                 (['gakkou', 'kakkou'], ['1207666110']), ([], ['1207658695']), (['dune_remaster'], ['dune'])]
        for ids, skipids in cases:
            self.assertEqual(self.select(ids, skipids), self.old_select(ids, skipids), (ids, skipids))
            self.assertEqual(g.run_report.exit_status(), 0)

    def test_the_name_as_on_gog_selects_a_game_for_download(self):
        self.assertEqual(self.select(['Beneath a Steel Sky (1994)']), ['beneath_a_steel_sky'])
        self.assertIn("is taken as beneath_a_steel_sky", self.log)
        self.assertEqual(g.run_report.exit_status(), 0)

    def test_the_name_as_on_gog_in_skipids_skips_the_game(self):
        found = self.select([], ['Beneath a Steel Sky (1994)', "Baldur's Gate: Enhanced Edition"])
        self.assertNotIn('beneath_a_steel_sky', found)
        self.assertNotIn('baldurs_gate_enhanced_edition', found)
        self.assertEqual(len(found), len(self.items) - 2)

    def test_a_typo_among_matching_ids_is_a_failure_but_the_rest_is_still_selected(self):
        found = self.select(['dune', 'Witcer 2'])
        self.assertEqual(found, ['dune'])
        self.assertIn('Did you mean: the_witcher_2_assassins_of_kings', self.log)
        self.assertEqual(g.run_report.exit_status(), 1)
        self.assertEqual([f[0] for f in g.run_report.failures], ['-ids Witcer 2'])

    def test_a_typo_in_skipids_is_a_failure_and_skips_nothing(self):
        found = self.select([], ['beneath_a_steel_sky', 'dun'])
        self.assertNotIn('beneath_a_steel_sky', found)
        self.assertEqual(len(found), len(self.items) - 1)
        self.assertEqual(g.run_report.exit_status(), 1)
        self.assertIn("-skipids 'dun' matches no game", self.log)

    def test_a_skip_id_that_is_outside_the_selected_games_is_not_a_failure(self):
        # it exists in the manifest; it just is not among the games that -ids selected
        found = self.select(['dune'], ['cafe_racer'])
        self.assertEqual(found, ['dune'])
        self.assertEqual(g.run_report.exit_status(), 0)

    def test_nothing_selected_still_stops_the_run_and_the_suggestions_come_first(self):
        with self.assertLogs('gogrepoc', level='DEBUG') as logs, self.assertRaises(SystemExit) as stop:
            g._select_download_items(list(self.items), ['Witcer 2'], [], [])
        self.assertEqual(stop.exception.code, 1)
        text = '\n'.join(logs.output)
        self.assertLess(text.index('Did you mean'), text.index('was found'))

    def test_unquoted_words_stop_with_the_quote_hint(self):
        with self.assertLogs('gogrepoc', level='DEBUG') as logs, self.assertRaises(SystemExit):
            g._select_download_items(list(self.items), ['Beneath', 'a', 'Steel', 'Sky'], [], [])
        self.assertIn('must be in quotes', '\n'.join(logs.output))

    def test_an_ambiguous_name_is_not_guessed(self):
        with self.assertLogs('gogrepoc', level='DEBUG') as logs, self.assertRaises(SystemExit):
            g._select_download_items(list(self.items), ['DUNE'], [], [])
        self.assertIn('so none was chosen', '\n'.join(logs.output))

    # --- verify, import, backup: which games are reached ---

    def reached(self, command):
        """The titles of the games that a command goes on with after -ids / -skipids."""
        seen = []

        def recorder(entries, valid_langs, fallback_lang=None):
            if entries:
                seen.append(entries[0].name)
            return []
        return seen, recorder

    def id_failures(self):
        """The failures about -ids / -skipids (verify has failures of its own, for files that are not on disk)."""
        return [f[0] for f in g.run_report.failures if f[0].startswith(('-ids', '-skipids'))]

    def run_verify(self, ids=(), skipids=()):
        self.items = library()          # the commands change the games they are given: every run starts with a fresh library
        seen, recorder = self.reached('verify')
        with mock.patch.object(g, 'load_manifest', lambda *a, **k: self.items), mock.patch.object(g, 'filter_languages', recorder), \
                self.assertLogs('gogrepoc', level='DEBUG') as logs:
            g.cmd_verify(self.dir, False, list(skipids), True, True, True, False, True, list(ids), ALL_OS, [], False, False, False, [],
                         False, False, False, True, lang_fallback=None)
            g.info('end of test')
        self.log = '\n'.join(logs.output)
        return sorted(name[len('setup_'):-len('.exe')] for name in seen if name.startswith('setup_'))

    def run_import_or_backup(self, command, ids=(), skipids=()):
        self.items = library()
        seen, recorder = self.reached(command)
        shutil.rmtree(self.dir, True)
        src, dst = os.path.join(self.dir, 'src'), os.path.join(self.dir, 'dst')
        os.makedirs(src)
        os.makedirs(dst)
        with mock.patch.object(g, 'load_manifest', lambda *a, **k: self.items), mock.patch.object(g, 'filter_languages', recorder), \
                self.assertLogs('gogrepoc', level='DEBUG') as logs:
            if command == 'import':
                g.cmd_import(src, dst, ALL_OS, [], False, list(skipids), list(ids), False, False, False, False, lang_fallback=None)
            else:
                g.cmd_backup(src, dst, False, ALL_OS, [], list(ids), list(skipids), False, False, False, lang_fallback=None)
            g.info('end of test')
        self.log = '\n'.join(logs.output)
        return sorted(name[len('setup_'):-len('.exe')] for name in seen if name.startswith('setup_'))

    def test_verify_ids_by_title_by_id_and_by_name(self):
        self.assertEqual(self.run_verify(ids=['dune', '1207666100']), ['cafe_racer', 'dune'])
        self.assertEqual(self.id_failures(), [])
        self.assertEqual(self.run_verify(ids=['Beneath a Steel Sky (1994)']), ['beneath_a_steel_sky'])
        self.assertEqual(self.id_failures(), [])
        self.assertIn("is taken as beneath_a_steel_sky", self.log)

    def test_verify_skipids_by_name_and_with_a_typo(self):
        everything = self.run_verify()
        self.assertEqual(len(everything), len(self.items))
        found = self.run_verify(skipids=['Beneath a Steel Sky (1994)'])
        self.assertEqual(sorted(set(everything) - set(found)), ['beneath_a_steel_sky'])
        g.run_report.reset('test')
        found = self.run_verify(skipids=['dun', 'cafe_racer'])
        self.assertEqual(sorted(set(everything) - set(found)), ['cafe_racer'])
        self.assertEqual(self.id_failures(), ['-skipids dun'])

    def test_verify_typo_in_ids_is_a_failure_and_the_rest_is_verified(self):
        self.assertEqual(self.run_verify(ids=['dune', 'Witcer 2']), ['dune'])
        self.assertEqual(self.id_failures(), ['-ids Witcer 2'])
        self.assertIn('Did you mean', self.log)

    def test_verify_with_nothing_found_warns_as_before_and_reports_the_failure(self):
        self.assertEqual(self.run_verify(ids=['Witcer 2']), [])
        self.assertIn('no known files with ids in {Witcer 2} where found', self.log)
        self.assertEqual(self.id_failures(), ['-ids Witcer 2'])
        self.assertEqual(g.run_report.exit_status(), 1)

    def test_import_and_backup_ids_and_skipids(self):
        for command in ('import', 'backup'):
            g.run_report.reset('test')
            self.assertEqual(self.run_import_or_backup(command, ids=['dune', 'Caf\u00e9 Racer']), ['cafe_racer', 'dune'], command)
            self.assertEqual(g.run_report.exit_status(), 0, command)
            found = self.run_import_or_backup(command, skipids=['dune', "Baldur's Gate: Enhanced Edition"])
            self.assertEqual(len(found), len(self.items) - 2, command)
            self.assertNotIn('dune', found)
            self.assertNotIn('baldurs_gate_enhanced_edition', found)
            self.assertEqual(g.run_report.exit_status(), 0, command)

    def test_import_and_backup_report_what_matches_no_game(self):
        for command in ('import', 'backup'):
            g.run_report.reset('test')
            found = self.run_import_or_backup(command, ids=['dune', 'Witcer 2'])
            self.assertEqual(found, ['dune'], command)
            self.assertEqual(g.run_report.exit_status(), 1, command)
            self.assertIn('Did you mean', self.log, command)
            g.run_report.reset('test')
            self.assertEqual(self.run_import_or_backup(command, ids=['nothing_like_it_zzz']), [], command)
            self.assertEqual(g.run_report.exit_status(), 1, command)         # before this was silent

    def test_without_ids_nothing_is_resolved_and_nothing_is_reported(self):
        with mock.patch.object(g, 'resolve_ids_and_report', side_effect=AssertionError('not expected')):
            self.assertEqual(len(self.select()), len(self.items))
            self.assertEqual(len(self.run_import_or_backup('import')), len(self.items))
            self.assertEqual(len(self.run_import_or_backup('backup')), len(self.items))


if __name__ == '__main__':
    unittest.main()
