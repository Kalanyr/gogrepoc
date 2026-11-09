import os
import tempfile
import unittest

import _bootstrap  # noqa: F401
import gogrepo_delta as app
from gogrepo_delta import AttrDict


class Md5CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        self.old_md5_dir = app.MD5_DIR_NAME
        os.chdir(self.tempdir.name)
        app.MD5_DIR_NAME = "!md5_xmls"

    def tearDown(self):
        app.MD5_DIR_NAME = self.old_md5_dir
        os.chdir(self.old_cwd)
        self.tempdir.cleanup()

    def _write(self, relative_path, content="<md5s/>"):
        path = os.path.join(app.MD5_DIR_NAME, "Game", relative_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as stream:
            stream.write(content)
        return path

    def _save(self, downloads=(), extras=()):
        item = AttrDict(
            title="Game", folder_name="Game",
            downloads=list(downloads), extras=list(extras),
        )
        app.save_manifest([item], filepath="manifest.dat", update_md5_xml=True)

    def test_existing_download_md5_is_preserved_when_another_name_is_unknown(self):
        known = self._write("downloads/windows/en/setup.exe.xml")
        self._write("downloads/windows/en/older-but-valid.xml")
        download = AttrDict(os_type="windows", lang="en", name=None,
                            provisional_name="setup.exe", manualUrl="test", unreleased=False)
        self._save([download])
        self.assertTrue(os.path.isfile(known))
        self.assertTrue(os.path.isfile(os.path.join(
            app.MD5_DIR_NAME, "Game", "downloads", "windows", "en",
            "older-but-valid.xml")))

    def test_existing_extra_md5_is_preserved_when_extra_name_is_unknown(self):
        known = self._write("extras/manual.pdf.xml")
        self._write("extras/another-valid.xml")
        extra = AttrDict(name=None, provisional_name="manual.pdf", manualUrl="test",
                         unreleased=False)
        self._save(extras=[extra])
        self.assertTrue(os.path.isfile(known))
        self.assertTrue(os.path.isfile(os.path.join(
            app.MD5_DIR_NAME, "Game", "extras", "another-valid.xml")))

    def test_stale_md5_is_removed_when_all_download_names_are_known(self):
        self._write("downloads/windows/en/obsolete.xml")
        download = AttrDict(os_type="windows", lang="en", name="current.exe",
                            unreleased=False)
        self._save([download])
        self.assertFalse(os.path.exists(os.path.join(
            app.MD5_DIR_NAME, "Game", "downloads", "windows", "en",
            "obsolete.xml")))

    def test_expected_md5_is_preserved_during_cleanup(self):
        expected = self._write("downloads/windows/en/current.exe.xml")
        download = AttrDict(os_type="windows", lang="en", name="current.exe",
                            unreleased=False)
        self._save([download])
        self.assertTrue(os.path.isfile(expected))


if __name__ == "__main__":
    unittest.main()
