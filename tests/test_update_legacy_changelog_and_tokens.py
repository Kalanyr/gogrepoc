"""Regression tests for legacy game metadata and the JSON token store."""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import _bootstrap  # noqa: F401
import gogrepo_delta as gog


class WorkingDirectory(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.temp = tempfile.mkdtemp()
        os.chdir(self.temp)
        self.old_password = gog._TOKEN_PASSWORD
        self.old_mode = os.environ.get(gog.TOKEN_MODE_ENV)
        gog._TOKEN_PASSWORD = None

    def tearDown(self):
        gog._TOKEN_PASSWORD = self.old_password
        if self.old_mode is None:
            os.environ.pop(gog.TOKEN_MODE_ENV, None)
        else:
            os.environ[gog.TOKEN_MODE_ENV] = self.old_mode
        os.chdir(self.cwd)
        shutil.rmtree(self.temp, ignore_errors=True)


class HandleGameUpdatesRegression(WorkingDirectory):
    def test_old_manifest_without_changelog_is_accepted(self):
        old = gog.AttrDict(
            title='Example', long_title='Example', serials=[],
            downloads=[], galaxyDownloads=[], sharedDownloads=[], extras=[]
        )
        new = gog.AttrDict(
            title='Example', long_title='Example', folder_name='Example',
            has_updates=False, changelog='New release notes', serials=[],
            downloads=[], galaxyDownloads=[], sharedDownloads=[], extras=[]
        )
        # Old gogrepoc manifests did not always have a changelog key.
        self.assertFalse(hasattr(old, 'changelog'))
        gog.handle_game_updates(old, new, False, False, False)


class TokenStoreTests(WorkingDirectory):
    def test_encrypted_json_round_trip_and_password_prompt_once(self):
        os.environ.pop(gog.TOKEN_MODE_ENV, None)
        with mock.patch.object(gog.getpass, 'getpass', side_effect=['secret-pass', 'secret-pass', 'secret-pass']) as prompt:
            gog.save_token({'access_token': 'ACCESS_SECRET', 'refresh_token': 'REFRESH_SECRET'})
            with open(gog.TOKEN_FILENAME, encoding='utf-8') as f:
                raw = f.read()
            self.assertNotIn('ACCESS_SECRET', raw)
            gog._TOKEN_PASSWORD = None
            loaded = gog.load_token()
        self.assertEqual(loaded['access_token'], 'ACCESS_SECRET')
        self.assertEqual(prompt.call_count, 3)

    def test_plain_json_requires_explicit_mode(self):
        os.environ[gog.TOKEN_MODE_ENV] = 'plain'
        gog.save_token({'access_token': 'plain-token'})
        with open(gog.TOKEN_FILENAME, encoding='utf-8') as f:
            envelope = json.load(f)
        self.assertEqual(envelope['encryption'], 'plain')
        self.assertEqual(gog.load_token()['access_token'], 'plain-token')

    def test_legacy_file_is_read_only_and_migrated_to_json(self):
        os.environ[gog.TOKEN_MODE_ENV] = 'plain'
        legacy_text = "{'access_token': 'legacy-access', 'refresh_token': 'legacy-refresh'}"
        with open(gog.LEGACY_TOKEN_FILENAME, 'w', encoding='utf-8') as f:
            f.write(legacy_text)
        loaded = gog.load_token()
        self.assertEqual(loaded['access_token'], 'legacy-access')
        self.assertTrue(os.path.exists(gog.TOKEN_FILENAME))
        with open(gog.LEGACY_TOKEN_FILENAME, encoding='utf-8') as f:
            self.assertEqual(f.read(), legacy_text)

    def test_bad_json_does_not_fall_back_to_legacy_file(self):
        os.environ[gog.TOKEN_MODE_ENV] = 'plain'
        with open(gog.TOKEN_FILENAME, 'w', encoding='utf-8') as f:
            f.write('{broken')
        with open(gog.LEGACY_TOKEN_FILENAME, 'w', encoding='utf-8') as f:
            f.write("{'access_token': 'stale'}")
        with self.assertRaises(json.JSONDecodeError):
            gog.load_token()

    def test_wrong_password_does_not_fall_back_to_legacy_file(self):
        os.environ.pop(gog.TOKEN_MODE_ENV, None)
        with mock.patch.object(gog.getpass, 'getpass', return_value='right-password'):
            gog.save_token({'access_token': 'secret'})
        with open(gog.LEGACY_TOKEN_FILENAME, 'w', encoding='utf-8') as f:
            f.write("{'access_token': 'stale'}")
        gog._TOKEN_PASSWORD = None
        with mock.patch.object(gog.getpass, 'getpass', return_value='wrong-password'):
            with self.assertRaisesRegex(ValueError, 'could not decrypt'):
                gog.load_token()


if __name__ == '__main__':
    unittest.main()
