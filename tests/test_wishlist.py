"""Entry 44: the wishlist command. A local HTTP server plays GOG (the answers of embed.gog.com/user/wishlist.json and
api.gog.com/products/<id>[/prices] as seen from a real account), so no network is needed."""
import csv
import json
import logging
import os
import shutil
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock
import _bootstrap  # noqa: F401
import requests
import gogrepo_delta as g

# the real answers (shortened): prices are "<cents> <currency>" strings, one entry per currency
PRICES_ANSWER = {"_links": {"self": {"href": "/api/products/1106055337/prices?countryCode=DE"}},
                 "_embedded": {"prices": [
                     {"currency": {"code": "EUR"}, "basePrice": "1999 EUR", "finalPrice": "999 EUR", "promoId": "20261105_fantasy_promo", "bonusWalletFunds": "0 EUR"},
                     {"currency": {"code": "USD"}, "basePrice": "2189 USD", "finalPrice": "1095 USD", "promoId": "20261105_fantasy_promo", "bonusWalletFunds": "0 USD"}]}}


def price_answer(base, final, promo=None):
    return {"_embedded": {"prices": [{"currency": {"code": "EUR"}, "basePrice": "%d EUR" % base, "finalPrice": "%d EUR" % final, "promoId": promo}]}}


class FakeGog(object):
    """State of the fake GOG; the handler reads it, the tests change it."""
    def __init__(self):
        self.wishlist = {}
        self.products = {}          # id -> product answer
        self.prices = {}            # id -> prices answer
        self.raw_wishlist = None    # a text to send instead of the wishlist JSON
        self.bad_countries = set()  # countryCode values that get 400 Bad Request, like GOG does for UK
        self.requests = []

    def start(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send(self, status, body, ctype='application/json'):
                data = body.encode('utf-8') if isinstance(body, str) else json.dumps(body).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', ctype)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                outer.requests.append(self.path)
                path = self.path.split('?')[0]
                parts = path.strip('/').split('/')
                if path == '/user/wishlist.json':
                    if outer.raw_wishlist is not None:
                        return self.send(200, outer.raw_wishlist, 'text/html')
                    return self.send(200, {'wishlist': {i: True for i in outer.wishlist}, 'checksum': 'x'})
                if len(parts) == 2 and parts[0] == 'products' and parts[1] in outer.products:
                    return self.send(200, outer.products[parts[1]])
                if len(parts) == 3 and parts[0] == 'products' and parts[2] == 'prices' and any('countryCode=' + c in self.path for c in outer.bad_countries):
                    return self.send(400, {'error': 'bad country'})
                if len(parts) == 3 and parts[0] == 'products' and parts[2] == 'prices' and parts[1] in outer.prices:
                    return self.send(200, outer.prices[parts[1]])
                self.send(404, {'error': 'not found'})

        self.server = HTTPServer(('127.0.0.1', 0), Handler)
        self.url = 'http://127.0.0.1:%d' % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def product(self, game_id, title):
        slug = title.lower().replace(' ', '_')
        self.products[game_id] = {'id': int(game_id), 'title': title, 'slug': slug, 'release_date': '2020-01-02T00:00:00+0200',
                                  'links': {'product_card': 'https://www.gog.com/game/' + slug}}

    def count(self, text):
        return len([r for r in self.requests if text in r])


class Capture(logging.Handler):
    def __init__(self):
        logging.Handler.__init__(self)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def messages(self, *levels):
        return [r.getMessage() for r in self.records if not levels or r.levelname in levels]


def fake_session():
    session = requests.Session()
    session.token = {'access_token': 't', 'refresh_token': 'r', 'expiry': time.time() + 3600}
    return session


class WishlistBase(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp(prefix='wl_')
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        self.gog = FakeGog()
        self.gog.start()
        self.addCleanup(self.gog.stop)
        for patch in (mock.patch.object(g, 'GOG_EMBED_URL', self.gog.url), mock.patch.object(g, 'GOG_API_URL', self.gog.url),
                      mock.patch.object(g, 'makeGOGSession', fake_session), mock.patch.object(g, 'load_manifest', return_value=[])):
            patch.start()
            self.addCleanup(patch.stop)
        g.run_report.reset('wishlist')
        self.addCleanup(g.run_report.reset)
        self.log = Capture()
        g.rootLogger.addHandler(self.log)
        self.addCleanup(g.rootLogger.removeHandler, self.log)
        self.gog.wishlist = {'111': True, '222': True, '333': True}
        for game_id, title in (('111', 'Alpha Quest'), ('222', 'Beta Racer'), ('333', 'Gamma Tactics')):
            self.gog.product(game_id, title)

    def saved(self, path='gog-wishlist.json'):
        with open(path, encoding='utf-8') as f:
            return json.load(f)


class MoneyAndPriceTests(unittest.TestCase):
    def test_parse_gog_money(self):
        self.assertEqual((1999, 'EUR'), g.parse_gog_money('1999 EUR'))
        self.assertEqual((0, 'USD'), g.parse_gog_money(' 0 usd '))
        for bad in (None, '', '19.99 EUR', 'EUR 1999', '1999', 1999):
            self.assertIsNone(g.parse_gog_money(bad), bad)

    def test_the_first_currency_is_used_by_default(self):
        self.assertEqual({'currency': 'EUR', 'base': 1999, 'final': 999, 'promo': '20261105_fantasy_promo'},
                         g.choose_price(PRICES_ANSWER['_embedded']['prices']))

    def test_a_currency_can_be_chosen(self):
        self.assertEqual(1095, g.choose_price(PRICES_ANSWER['_embedded']['prices'], 'usd')['final'])
        self.assertIsNone(g.choose_price(PRICES_ANSWER['_embedded']['prices'], 'JPY'))

    def test_unusable_entries_are_skipped(self):
        broken = [{'currency': {'code': 'EUR'}, 'basePrice': 'free', 'finalPrice': '0 EUR'}, {'currency': {'code': 'USD'}, 'basePrice': '500 USD', 'finalPrice': '500 USD'}]
        self.assertEqual('USD', g.choose_price(broken)['currency'])
        self.assertIsNone(g.choose_price([]))
        self.assertIsNone(g.choose_price(None))

    def test_format_money(self):
        self.assertEqual('9.99 EUR', g.format_money(999, 'EUR'))
        self.assertEqual('0,05', g.format_money(5, '', ','))
        self.assertEqual('20.00 EUR', g.format_money(2000, 'EUR'))


class ChangesTests(unittest.TestCase):
    def test_changes(self):
        old = {'1': {'price': {'currency': 'EUR', 'final': 1000}}, '2': {'price': {'currency': 'EUR', 'final': 500}}, '3': {}, '4': {'price': {'currency': 'EUR', 'final': 100}},
               '5': {'price': {'currency': 'EUR', 'final': 100}}}
        new = {'1': {'price': {'currency': 'EUR', 'final': 800}}, '2': {'price': {'currency': 'EUR', 'final': 600}}, '3': {}, '6': {},
               '5': {'price': {'currency': 'USD', 'final': 1}}}
        changes = g.wishlist_changes(old, new, library_ids=[4, '99'])
        self.assertEqual(['6'], changes['added'])
        self.assertEqual(['4'], changes['removed'])
        self.assertEqual(['4'], changes['now_owned'])
        self.assertEqual(['1'], changes['cheaper'])
        self.assertEqual(['2'], changes['dearer'])                       # '5' changed the currency: not comparable, so not reported


class ReadingTheWishlistTests(WishlistBase):
    def test_ids_are_read_from_the_real_format_and_sorted(self):
        self.gog.wishlist = {'2141922451': True, '1645689113': True, '1373009324': True}
        self.assertEqual(['1373009324', '1645689113', '2141922451'], g.fetch_wishlist_ids(fake_session()))

    def test_entries_that_are_not_true_are_ignored(self):
        self.gog.raw_wishlist = '{"wishlist": {"1": true, "2": false}, "checksum": "x"}'
        self.assertEqual(['1'], g.fetch_wishlist_ids(fake_session()))

    def test_an_answer_that_is_not_json_is_an_error_that_mentions_the_login(self):
        self.gog.raw_wishlist = '<html>please log in</html>'
        with self.assertRaises(g.WishlistError) as caught:
            g.fetch_wishlist_ids(fake_session())
        self.assertIn('login', str(caught.exception))

    def test_an_answer_without_a_wishlist_is_an_error(self):
        self.gog.raw_wishlist = '{"something": 1}'
        with self.assertRaises(g.WishlistError):
            g.fetch_wishlist_ids(fake_session())


class CommandTests(WishlistBase):
    def test_first_run_saves_the_games_with_their_details(self):
        g.cmd_wishlist()
        games = self.saved()['games']
        self.assertEqual({'111', '222', '333'}, set(games))
        self.assertEqual('Alpha Quest', games['111']['title'])
        self.assertEqual('https://www.gog.com/game/alpha_quest', games['111']['store_url'])
        self.assertEqual('2020-01-02T00:00:00+0200', games['111']['release_date'])
        self.assertIsNone(games['111']['price'])
        self.assertEqual(0, self.gog.count('/prices'), 'no prices are requested without -prices')
        self.assertIn('first run: nothing to compare with yet', self.log.messages())
        self.assertEqual([], g.run_report.failures)
        self.assertEqual(3, g.run_report.counts['wishlist games'][0])

    def test_second_run_does_not_fetch_known_details_again(self):
        g.cmd_wishlist()
        before = self.gog.count('/products/')
        g.cmd_wishlist()
        self.assertEqual(before, self.gog.count('/products/'))
        self.assertIn('no changes since the last run', self.log.messages())

    def test_added_removed_and_now_owned_are_reported(self):
        g.cmd_wishlist()
        del self.gog.wishlist['222']
        del self.gog.wishlist['333']
        self.gog.wishlist['444'] = True
        self.gog.product('444', 'Delta Force')
        with mock.patch.object(g, 'load_manifest', return_value=[g.AttrDict(id=333)]):
            g.cmd_wishlist()
        messages = self.log.messages()
        self.assertIn('new on the wishlist: Delta Force', messages)
        self.assertIn('no longer on the wishlist: Beta Racer', messages)
        self.assertIn('no longer on the wishlist: Gamma Tactics (now in your library)', messages)
        self.assertEqual({'111', '444'}, set(self.saved()['games']))

    def test_prices_are_saved_in_cents_for_the_chosen_country_and_currency(self):
        self.gog.prices = {'111': PRICES_ANSWER}
        g.cmd_wishlist(prices=True, country='de')
        saved = self.saved()
        self.assertEqual('DE', saved['country'])
        self.assertEqual({'currency': 'EUR', 'base': 1999, 'final': 999, 'promo': '20261105_fantasy_promo'}, saved['games']['111']['price'])
        self.assertIsNone(saved['games']['222']['price'], 'a game without a price (404) has none, and that is not a failure')
        self.assertEqual([], g.run_report.failures)
        self.assertTrue(any('countryCode=DE' in r for r in self.gog.requests))

    def test_a_currency_can_be_chosen_for_the_prices(self):
        self.gog.prices = {'111': PRICES_ANSWER}
        g.cmd_wishlist(prices=True, country='DE', currency='USD')
        self.assertEqual(1095, self.saved()['games']['111']['price']['final'])

    def test_a_price_change_is_reported(self):
        self.gog.prices = {'111': price_answer(2000, 2000)}
        g.cmd_wishlist(prices=True, country='DE')
        self.gog.prices = {'111': price_answer(2000, 1000, 'sale')}
        g.cmd_wishlist(prices=True, country='DE')
        self.assertIn('Alpha Quest: 20.00 EUR -> 10.00 EUR (cheaper)', self.log.messages())

    def test_without_prices_the_known_prices_are_kept_and_not_reported(self):
        self.gog.prices = {'111': price_answer(2000, 1500)}
        g.cmd_wishlist(prices=True, country='DE')
        g.cmd_wishlist()
        self.assertEqual(1500, self.saved()['games']['111']['price']['final'])
        self.assertIn('no changes since the last run', self.log.messages())

    def test_a_game_gog_does_not_know_is_kept_without_details_and_is_asked_again_next_time(self):
        del self.gog.products['222']
        g.cmd_wishlist()
        self.assertNotIn('title', {k for k, v in self.saved()['games']['222'].items() if v})
        self.assertEqual([], g.run_report.failures)
        self.assertTrue(any('222' in m for m in self.log.messages('WARNING')))
        self.gog.product('222', 'Beta Racer')
        g.cmd_wishlist()
        self.assertEqual('Beta Racer', self.saved()['games']['222']['title'])

    def test_a_wishlist_that_cannot_be_read_is_a_failure_and_writes_nothing(self):
        self.gog.raw_wishlist = '<html>login</html>'
        g.cmd_wishlist()
        self.assertFalse(os.path.exists('gog-wishlist.json'))
        self.assertEqual([('wishlist', 'could not be read')], g.run_report.failures)
        self.assertEqual(1, g.run_report.exit_status())

    def test_a_bad_country_is_refused_before_anything_is_requested(self):
        g.cmd_wishlist(prices=True, country='Germany')
        self.assertEqual([], self.gog.requests)
        self.assertEqual(1, g.run_report.exit_status())

    def test_a_damaged_saved_file_means_a_first_run(self):
        with open('gog-wishlist.json', 'w') as f:
            f.write('{ not json')
        g.cmd_wishlist()
        self.assertTrue(any('cannot be read' in m for m in self.log.messages('WARNING')))
        self.assertEqual({'111', '222', '333'}, set(self.saved()['games']))

    def test_the_output_file_can_be_chosen(self):
        g.cmd_wishlist(output='mine.json')
        self.assertTrue(os.path.exists('mine.json'))
        self.assertFalse(os.path.exists('gog-wishlist.json'))


class CsvTests(WishlistBase):
    def read(self, path, delimiter):
        with open(path, encoding='utf-8-sig', newline='') as f:
            return list(csv.reader(f, delimiter=delimiter))

    def test_csv_has_one_row_per_game_with_prices_and_library_flag(self):
        self.gog.prices = {'111': PRICES_ANSWER}
        with mock.patch.object(g, 'load_manifest', return_value=[g.AttrDict(id=222)]):
            g.cmd_wishlist(csv_output='w.csv', prices=True, country='DE', delimiter=',')
        rows = self.read('w.csv', ',')
        self.assertEqual(['game id', 'title', 'release date', 'store url', 'in library', 'currency', 'regular price', 'price', 'discount %', 'promo'], rows[0])
        by_id = {r[0]: r for r in rows[1:]}
        self.assertEqual(['Alpha Quest', '2020-01-02', 'https://www.gog.com/game/alpha_quest', 'no', 'EUR', '19.99', '9.99', '50', '20261105_fantasy_promo'], by_id['111'][1:])
        self.assertEqual('yes', by_id['222'][4])
        self.assertEqual(['', '', '', ''], by_id['333'][5:9])               # no price: empty cells
        self.assertEqual(['Alpha Quest', 'Beta Racer', 'Gamma Tactics'], [r[1] for r in rows[1:]])

    def test_a_semicolon_file_uses_decimal_commas(self):
        self.gog.prices = {'111': PRICES_ANSWER}
        g.cmd_wishlist(csv_output='w.csv', prices=True, country='DE', delimiter=';')
        row = [r for r in self.read('w.csv', ';') if r[0] == '111'][0]
        self.assertEqual(['19,99', '9,99'], row[6:8])


class DateFormatTests(unittest.TestCase):
    RAW = '2026-06-23T18:59:00+0200'

    def test_the_date_is_written_in_iso_form_whatever_the_time_and_offset(self):
        self.assertEqual('2026-06-23', g.format_release_date(self.RAW))
        self.assertEqual('2026-11-05', g.format_release_date('2026-11-05T19:00:00+0100'))
        self.assertEqual('2027-01-01', g.format_release_date('2027-01-01'))

    def test_the_day_is_the_one_in_the_text(self):
        self.assertEqual('2026-12-31', g.format_release_date('2026-12-31T23:30:00-0800'))      # no time zone conversion

    def test_something_that_is_not_a_date_comes_back_unchanged(self):
        self.assertEqual('soon', g.format_release_date('soon'))
        self.assertEqual('', g.format_release_date(None))
        self.assertEqual('', g.format_release_date(''))

    def test_a_date_that_a_spreadsheet_could_misread_is_never_written(self):
        # 11/05/2026 is 11 May on a German Excel and 06/23/2026 stays text: only the ISO form means the same everywhere
        self.assertNotIn('/', g.format_release_date('2026-11-05T19:00:00+0100'))
        self.assertNotIn('.', g.format_release_date('2026-11-05T19:00:00+0100'))


class CountryAndEmptyListTests(WishlistBase):
    def read(self, path):
        with open(path, encoding='utf-8-sig', newline='') as f:
            return list(csv.reader(f, delimiter=','))

    def test_csv_dates_are_iso_whatever_the_country(self):
        g.cmd_wishlist(csv_output='de.csv', country='DE', delimiter=',')
        g.cmd_wishlist(csv_output='us.csv', country='US', delimiter=',')
        g.cmd_wishlist(csv_output='none.csv', delimiter=',')
        for name in ('de.csv', 'us.csv', 'none.csv'):
            self.assertEqual('2020-01-02', self.read(name)[1][2], name)
        self.assertEqual('2020-01-02T00:00:00+0200', self.saved()['games']['111']['release_date'], 'the saved file keeps the original')

    def test_the_country_still_selects_the_prices_and_nothing_else(self):
        self.gog.prices = {'111': PRICES_ANSWER}
        g.cmd_wishlist(prices=True, country='DE', csv_output='de.csv', delimiter=',')
        self.assertTrue(any('countryCode=DE' in r for r in self.gog.requests))
        self.assertEqual('DE', self.saved()['country'])
        self.assertEqual('2020-01-02', self.read('de.csv')[1][2])

    def test_the_prices_need_no_country_option(self):
        self.gog.prices = {'111': PRICES_ANSWER}
        g.cmd_wishlist(prices=True)
        self.assertTrue(any('countryCode=US' in r for r in self.gog.requests))

    def test_uk_is_taken_as_gb(self):
        self.gog.prices = {'111': PRICES_ANSWER}
        g.cmd_wishlist(prices=True, country='UK', csv_output='uk.csv', delimiter=',')
        self.assertTrue(any('countryCode=GB' in r for r in self.gog.requests))
        self.assertFalse(any('countryCode=UK' in r for r in self.gog.requests))
        self.assertIn("'UK' is not an ISO country code; using GB", self.log.messages('INFO'))
        self.assertEqual('2020-01-02', self.read('uk.csv')[1][2])
        self.assertEqual([], g.run_report.failures)

    def test_a_country_gog_refuses_stops_the_price_requests_after_the_first(self):
        self.gog.bad_countries = {'XX'}
        started = time.time()
        g.cmd_wishlist(prices=True, country='XX')
        self.assertLess(time.time() - started, 4, 'no retries for a 400')
        self.assertEqual(1, self.gog.count('/prices'))
        self.assertEqual([('prices', 'country not accepted')], g.run_report.failures)
        self.assertTrue(any('two-letter ISO code' in m for m in self.log.messages('ERROR')))
        self.assertEqual({'111', '222', '333'}, set(self.saved()['games']), 'the wishlist itself is still saved')

    def test_a_400_is_not_retried_when_the_caller_says_so(self):
        self.gog.bad_countries = {'XX'}
        with self.assertRaises(requests.HTTPError):
            g.request(fake_session(), self.gog.url + '/products/1/prices', args={'countryCode': 'XX'}, quiet_statuses=(400,), no_retry_statuses=(400,))
        self.assertEqual(1, self.gog.count('/prices'))

    def test_an_empty_wishlist_comes_as_a_list(self):
        self.gog.raw_wishlist = '{"wishlist": [], "checksum": "x"}'
        g.cmd_wishlist()
        self.assertEqual({}, self.saved()['games'])
        self.assertEqual([], g.run_report.failures)
        self.assertIn('the wishlist has 0 games', self.log.messages())

    def test_a_list_of_ids_is_accepted_too(self):
        self.gog.raw_wishlist = '{"wishlist": [222, 111]}'
        self.assertEqual(['111', '222'], g.fetch_wishlist_ids(fake_session()))

    def test_games_removed_when_the_list_becomes_empty_are_reported(self):
        g.cmd_wishlist()
        self.gog.raw_wishlist = '{"wishlist": []}'
        g.cmd_wishlist()
        self.assertIn('no longer on the wishlist: Alpha Quest', self.log.messages())


class CsvOptionTests(unittest.TestCase):
    def parse(self, *words):
        p1, _sp = g.build_parser()
        return p1.parse_args(['wishlist'] + list(words))

    def test_csv_without_a_file_name_uses_the_default(self):
        self.assertEqual('gog-wishlist.csv', self.parse('-csv').csv)
        self.assertEqual(g.WISHLIST_CSV_FILENAME, self.parse('-csv').csv)

    def test_csv_with_a_file_name_uses_it(self):
        self.assertEqual('mine.csv', self.parse('-csv', 'mine.csv').csv)

    def test_no_csv_option_means_no_csv_file(self):
        self.assertIsNone(self.parse().csv)

    def test_csv_followed_by_another_option_does_not_swallow_it(self):
        args = self.parse('-csv', '-prices', '-country', 'DE')
        self.assertEqual(('gog-wishlist.csv', True, 'DE'), (args.csv, args.prices, args.country))

    def test_csv_can_come_last_or_first(self):
        self.assertEqual('gog-wishlist.csv', self.parse('-prices', '-csv').csv)
        self.assertTrue(self.parse('-csv', '-prices').prices)


class LockedFileTests(WishlistBase):
    """On Windows a CSV file that is open in Excel cannot be written (PermissionError)."""
    def test_a_csv_file_that_cannot_be_opened_is_reported_before_anything_is_fetched(self):
        os.mkdir('blocked.csv')                                  # cannot be opened for writing, on every system
        g.cmd_wishlist(csv_output='blocked.csv')
        self.assertEqual([], self.gog.requests, 'nothing is requested')
        self.assertFalse(os.path.exists('gog-wishlist.json'))
        errors = self.log.messages('ERROR')
        self.assertEqual(1, len(errors))
        self.assertIn('cannot write blocked.csv', errors[0])
        self.assertIn('please close it and run the command again', errors[0])
        self.assertEqual([('csv', 'file cannot be written')], g.run_report.failures)
        self.assertEqual(1, g.run_report.exit_status())

    def test_the_early_check_is_the_one_a_locked_file_fails(self):
        real_open = open

        def refuse_append(path, mode='r', *args, **kwargs):
            if str(path).endswith('locked.csv') and 'a' in mode:
                raise PermissionError(13, 'Permission denied')
            return real_open(path, mode, *args, **kwargs)
        with mock.patch('builtins.open', refuse_append):
            g.cmd_wishlist(csv_output='locked.csv')
        self.assertEqual([], self.gog.requests)
        self.assertIn('Permission denied', self.log.messages('ERROR')[0])

    def test_a_file_that_gets_locked_during_the_run_is_reported_and_the_saved_list_is_not_updated(self):
        g.cmd_wishlist()
        self.gog.wishlist['444'] = True
        self.gog.product('444', 'Delta Force')
        before = self.saved()
        with mock.patch.object(g, 'write_wishlist_csv', side_effect=PermissionError(13, 'Permission denied')):
            g.cmd_wishlist(csv_output='w.csv')
        self.assertIn('please close it and run the command again', self.log.messages('ERROR')[-1])
        self.assertEqual(before, self.saved(), 'the list is unchanged, so the next run reports the new game again')
        self.assertEqual(1, g.run_report.exit_status())
        g.run_report.reset('wishlist')
        self.log.records[:] = []
        g.cmd_wishlist(csv_output='w.csv')
        self.assertIn('new on the wishlist: Delta Force', self.log.messages())
        self.assertTrue(os.path.exists('w.csv'))

    def test_a_writable_csv_is_not_changed_by_the_check_and_a_missing_one_is_not_left_behind(self):
        with open('keep.csv', 'w', encoding='utf-8') as f:
            f.write('keep me')
        before = os.stat('keep.csv')
        self.assertIsNone(g.file_write_problem('keep.csv'))
        with open('keep.csv', encoding='utf-8') as f:
            self.assertEqual('keep me', f.read())
        self.assertEqual(before.st_mtime, os.stat('keep.csv').st_mtime)
        self.assertIsNone(g.file_write_problem('new.csv'))
        self.assertFalse(os.path.exists('new.csv'))

    def test_the_saved_list_that_cannot_be_written_is_reported_too(self):
        with mock.patch.object(g, 'atomic_write_text', side_effect=PermissionError(13, 'Permission denied')):
            g.cmd_wishlist()
        self.assertIn('cannot write gog-wishlist.json', self.log.messages('ERROR')[-1])
        self.assertEqual([('wishlist', 'file cannot be written')], g.run_report.failures)

    def test_a_normal_run_still_writes_both_files(self):
        g.cmd_wishlist(csv_output='w.csv')
        self.assertTrue(os.path.exists('w.csv') and os.path.exists('gog-wishlist.json'))
        self.assertEqual([], g.run_report.failures)


class CsvConfigFileTests(unittest.TestCase):
    def process(self, config_text, *words):
        folder = tempfile.mkdtemp(prefix='cfg_')
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        path = os.path.join(folder, 'c.cfg')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(config_text)
        with mock.patch.dict(os.environ, {'GOGREPO_DELTA_CONFIG': path}):
            return g.process_argv(['gogrepo_delta.py', 'wishlist'] + list(words))

    def test_the_config_file_value_is_used_without_the_option(self):
        self.assertEqual('from-config.csv', self.process('[wishlist]\ncsv = from-config.csv\n').csv)

    def test_the_option_without_a_name_beats_the_config_file(self):
        self.assertEqual('gog-wishlist.csv', self.process('[wishlist]\ncsv = from-config.csv\n', '-csv').csv)

    def test_the_option_with_a_name_beats_the_config_file(self):
        self.assertEqual('cli.csv', self.process('[wishlist]\ncsv = from-config.csv\n', '-csv', 'cli.csv').csv)


class CsvDefaultFileTests(WishlistBase):
    def test_the_default_file_is_written(self):
        g.cmd_wishlist(csv_output=self.parse_default(), delimiter=',')
        self.assertTrue(os.path.exists('gog-wishlist.csv'))
        with open('gog-wishlist.csv', encoding='utf-8-sig', newline='') as f:
            self.assertEqual(4, len(list(csv.reader(f))))                # the header and three games

    def parse_default(self):
        p1, _sp = g.build_parser()
        return p1.parse_args(['wishlist', '-csv']).csv


class OptionTests(unittest.TestCase):
    def test_the_command_and_its_defaults(self):
        p1, _sp = g.build_parser()
        args = p1.parse_args(['wishlist'])
        self.assertEqual((g.WISHLIST_FILENAME, None, False, None, None, None), (args.output, args.csv, args.prices, args.country, args.currency, args.delimiter))
        args = p1.parse_args(['wishlist', '-prices', '-country', 'DE', '-currency', 'EUR', '-csv', 'x.csv'])
        self.assertEqual((True, 'DE', 'EUR', 'x.csv'), (args.prices, args.country, args.currency, args.csv))


if __name__ == '__main__':
    unittest.main()
