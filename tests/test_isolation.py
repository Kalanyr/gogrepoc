"""The tests run in a scratch folder, never in the folder they were started from (that may hold a real library and its manifest)."""
import os
import unittest

import _bootstrap
import gogrepo_delta as g


class ScratchFolderTests(unittest.TestCase):
    def test_the_tests_run_in_the_scratch_folder_not_where_they_were_started(self):
        self.assertEqual(os.path.realpath(os.getcwd()), _bootstrap.SCRATCH_DIR)
        self.assertNotEqual(_bootstrap.SCRATCH_DIR, os.path.realpath(_bootstrap.LAUNCH_DIR))

    def test_a_manifest_saved_with_the_default_path_lands_in_the_scratch_folder(self):
        before = set(os.listdir(_bootstrap.LAUNCH_DIR))
        try:
            with self.assertLogs('gogrepoc', level='DEBUG'):
                g.save_manifest([g.AttrDict(id=1, title='x', long_title='x', folder_name='x', downloads=[], extras=[])])
            self.assertTrue(os.path.exists(os.path.join(_bootstrap.SCRATCH_DIR, g.MANIFEST_FILENAME)))
            self.assertEqual(set(os.listdir(_bootstrap.LAUNCH_DIR)), before)
        finally:
            for name in (g.MANIFEST_FILENAME, g.MANIFEST_FILENAME + g.BACKUP_EXT if hasattr(g, 'BACKUP_EXT') else g.MANIFEST_FILENAME + '.bak'):
                try:
                    os.remove(os.path.join(_bootstrap.SCRATCH_DIR, name))
                except OSError:
                    pass

    def test_the_log_file_of_the_script_is_in_the_scratch_folder_too(self):
        self.assertEqual(os.path.dirname(os.path.realpath(g.loggingHandler.baseFilename)), _bootstrap.SCRATCH_DIR)

    def test_the_scratch_folder_is_not_inside_the_repository_or_the_start_folder(self):
        for other in (_bootstrap.ROOT, os.path.realpath(_bootstrap.LAUNCH_DIR)):
            self.assertFalse(_bootstrap.SCRATCH_DIR.startswith(other + os.sep), other)


if __name__ == '__main__':
    unittest.main()
