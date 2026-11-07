"""0.5.46: a wrong token password is asked for again (up to 3 times, from a terminal) instead of ending with a traceback."""
import logging
import os
import shutil
import tempfile
import unittest
from unittest import mock
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


class PasswordRetryTests(unittest.TestCase):
    def setUp(self):
        self.cwd, self.dir = os.getcwd(), tempfile.mkdtemp(prefix='tok_')
        os.chdir(self.dir)
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.addCleanup(os.chdir, self.cwd)
        self.old_password, self.old_mode = g._TOKEN_PASSWORD, os.environ.pop(g.TOKEN_MODE_ENV, None)
        self.addCleanup(setattr, g, '_TOKEN_PASSWORD', self.old_password)
        if self.old_mode is not None:
            self.addCleanup(os.environ.__setitem__, g.TOKEN_MODE_ENV, self.old_mode)
        g._TOKEN_PASSWORD = None
        with mock.patch.object(g.getpass, 'getpass', return_value='right'):
            g.save_token({'access_token': 'ACCESS', 'refresh_token': 'REFRESH', 'expiry': 1})
        g._TOKEN_PASSWORD = None
        self.log = Capture()
        g.rootLogger.addHandler(self.log)
        self.addCleanup(g.rootLogger.removeHandler, self.log)

    def load(self, answers, terminal=True):
        with mock.patch.object(g.getpass, 'getpass', side_effect=answers) as prompt, mock.patch.object(g, '_can_prompt_again', return_value=terminal):
            try:
                return g.load_token(), prompt
            except Exception as e:
                return e, prompt

    def test_a_wrong_password_is_asked_for_again(self):
        token, prompt = self.load(['wrong', 'right'])
        self.assertEqual('ACCESS', token['access_token'])
        self.assertEqual(2, prompt.call_count)
        self.assertEqual(['Wrong password. Please try again (1 of 3).'], self.log.errors())

    def test_the_second_attempt_may_also_fail_and_the_third_works(self):
        token, prompt = self.load(['a', 'b', 'right'])
        self.assertEqual('ACCESS', token['access_token'])
        self.assertEqual(3, prompt.call_count)
        self.assertEqual(['Wrong password. Please try again (1 of 3).', 'Wrong password. Please try again (2 of 3).'], self.log.errors())

    def test_after_three_wrong_passwords_it_stops_with_the_usual_message(self):
        error, prompt = self.load(['a', 'b', 'c', 'right'])
        self.assertIsInstance(error, g.TokenPasswordError)
        self.assertIsInstance(error, ValueError)                      # callers that expect the old ValueError still work
        self.assertIn('could not decrypt', str(error))
        self.assertEqual(3, prompt.call_count)

    def test_the_wrong_password_is_not_kept(self):
        self.load(['a', 'b', 'c'])
        self.assertIsNone(g._TOKEN_PASSWORD)

    def test_the_right_password_is_kept_so_that_saving_does_not_ask_again(self):
        _token, prompt = self.load(['wrong', 'right'])
        with mock.patch.object(g.getpass, 'getpass', side_effect=AssertionError('must not ask')):
            g.save_token({'access_token': 'NEW'})
        self.assertEqual(2, prompt.call_count)

    def test_an_empty_answer_asks_again(self):
        token, prompt = self.load(['', 'right'])
        self.assertEqual('ACCESS', token['access_token'])
        self.assertEqual(2, prompt.call_count)
        self.assertEqual(['The password must not be empty. Please try again (1 of 3).'], self.log.errors())

    def test_without_a_terminal_there_is_one_attempt(self):
        error, prompt = self.load(['wrong', 'right'], terminal=False)
        self.assertIsInstance(error, g.TokenPasswordError)
        self.assertEqual(1, prompt.call_count)

    def test_without_a_terminal_an_empty_password_is_an_error_as_before(self):
        error, prompt = self.load([''], terminal=False)
        self.assertIsInstance(error, ValueError)
        self.assertIn('must not be empty', str(error))
        self.assertEqual(1, prompt.call_count)

    def test_an_empty_answer_is_not_remembered(self):
        with mock.patch.object(g.getpass, 'getpass', side_effect=['', 'right']) as prompt:
            with self.assertRaises(ValueError):
                g._token_password()
            self.assertEqual('right', g._token_password())
        self.assertEqual(2, prompt.call_count)

    def test_a_damaged_file_ends_the_same_way_after_the_attempts(self):
        with open(g.TOKEN_FILENAME, encoding='utf-8') as f:
            text = f.read()
        import re
        with open(g.TOKEN_FILENAME, 'w', encoding='utf-8') as f:
            f.write(re.sub(r'("ciphertext": ")(.)', lambda m: m.group(1) + ('A' if m.group(2) != 'A' else 'B'), text))
        error, prompt = self.load(['right', 'right', 'right'])
        self.assertIsInstance(error, g.TokenPasswordError)
        self.assertEqual(3, prompt.call_count)


if __name__ == '__main__':
    unittest.main()
