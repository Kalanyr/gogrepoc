"""Tests for atomic manifest/token/config saving."""
import os, shutil, stat, sys, tempfile, unittest
from unittest import mock
import _bootstrap  # noqa: F401
import gogrepo_delta as NEW

def items(mod, n=3, tag=''):
    return [mod.AttrDict(id=i, title='game%s%d' % (tag, i), size=100 + i, updated='2020-01-01T00:00:00') for i in range(n)]

class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.cwd = os.getcwd(); os.chdir(self.d)
        self.path = os.path.join(self.d, 'gog-manifest.dat')
    def tearDown(self):
        os.chdir(self.cwd); shutil.rmtree(self.d, ignore_errors=True)
    def read(self, p):
        with open(p, encoding='utf-8') as f: return f.read()
    def leftovers(self): return [f for f in os.listdir(self.d) if f.endswith('.tmp')]

class ManifestSave(Base):
    def test_roundtrip(self):
        NEW.save_manifest_core_worker(items(NEW), self.path)
        self.assertEqual(NEW.load_manifest(self.path), items(NEW))
        self.assertEqual(self.leftovers(), [])

    def test_backup_holds_previous_version(self):
        NEW.save_manifest_core_worker(items(NEW, tag='a'), self.path); first = self.read(self.path)
        NEW.save_manifest_core_worker(items(NEW, tag='b'), self.path)
        self.assertEqual(self.read(self.path + '.bak'), first)
        self.assertNotEqual(self.read(self.path), first)

    def test_crash_at_swap_keeps_old_manifest(self):
        NEW.save_manifest_core_worker(items(NEW, tag='a'), self.path); before = self.read(self.path)
        with mock.patch.object(os, 'replace', side_effect=OSError('simulated crash')):
            with self.assertRaises(OSError): NEW.save_manifest_core_worker(items(NEW, tag='b'), self.path)
        self.assertEqual(self.read(self.path), before)
        self.assertEqual(self.leftovers(), [])

    def test_serialisation_failure_keeps_old_manifest(self):
        NEW.save_manifest_core_worker(items(NEW, tag='a'), self.path); before = self.read(self.path)
        class Boom(object):
            def __repr__(self): raise RuntimeError('cannot serialise')
        with self.assertRaises(RuntimeError): NEW.save_manifest_core_worker([Boom()], self.path)
        self.assertEqual(self.read(self.path), before)
        self.assertEqual(self.leftovers(), [])

    def test_ctrl_c_during_write_keeps_old_manifest(self):
        NEW.save_manifest_core_worker(items(NEW, tag='a'), self.path); before = self.read(self.path)
        class Interrupt(object):
            def __repr__(self): raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt): NEW.save_manifest_core_worker([Interrupt()], self.path)
        self.assertEqual(self.read(self.path), before)
        self.assertEqual(self.leftovers(), [])

    def test_stale_tmp_from_earlier_crash_is_overwritten(self):
        with open(self.path + '.tmp', 'w') as f: f.write('garbage from a crashed run')
        NEW.save_manifest_core_worker(items(NEW), self.path)
        self.assertEqual(NEW.load_manifest(self.path), items(NEW)); self.assertEqual(self.leftovers(), [])

    @unittest.skipIf(os.name == 'nt', 'POSIX permissions')
    def test_permissions_preserved(self):
        NEW.save_manifest_core_worker(items(NEW), self.path); os.chmod(self.path, 0o600)
        NEW.save_manifest_core_worker(items(NEW, tag='b'), self.path)
        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)

class DescriptorOwnership(Base):
    """After a failed save, the file descriptor of the temporary file must not be closed a second time: the file object that
    took it over has already closed it, and the number may belong to another thread's file by then."""

    def test_a_failed_swap_does_not_close_the_descriptor_again(self):
        closed = []
        real_close = os.close
        with mock.patch.object(NEW, '_replace_file', side_effect=PermissionError('locked by the virus scanner')), \
                mock.patch.object(NEW.os, 'close', lambda fd: (closed.append(fd), real_close(fd))[1]):
            with self.assertRaises(PermissionError):
                NEW.atomic_write_text(self.path, lambda w: w.write('data'))
        self.assertEqual(closed, [])                      # the file object closed it; nobody else may
        self.assertEqual(self.leftovers(), [])            # the temporary file is still removed

    def test_another_threads_file_survives_a_failed_save(self):
        other = {}

        def replace_while_another_thread_opens_a_file(src, dst):
            other['file'] = open(os.path.join(self.d, 'other.bin'), 'wb')       # gets the number that was just freed
            raise PermissionError('locked')
        with mock.patch.object(NEW, '_replace_file', replace_while_another_thread_opens_a_file):
            with self.assertRaises(PermissionError):
                NEW.atomic_write_text(self.path, lambda w: w.write('data'))
        try:
            other['file'].write(b'still usable')
            other['file'].flush()
        finally:
            other['file'].close()

    def test_when_the_file_object_cannot_be_made_the_descriptor_is_closed_once(self):
        closed = []
        real_close = os.close
        with mock.patch.object(NEW.os, 'fdopen', side_effect=OSError('no file object')), \
                mock.patch.object(NEW.os, 'close', lambda fd: (closed.append(fd), real_close(fd))[1]):
            with self.assertRaises(OSError):
                NEW.atomic_write_text(self.path, lambda w: w.write('data'))
        self.assertEqual(len(closed), 1)                  # nobody owned it, so it is closed here, exactly once
        self.assertEqual(self.leftovers(), [])

    def test_an_error_while_writing_closes_nothing_twice_and_keeps_the_old_file(self):
        NEW.atomic_write_text(self.path, lambda w: w.write('old'))
        closed = []
        real_close = os.close

        def failing_write(w):
            w.write('new')
            raise ValueError('serialisation failed')
        with mock.patch.object(NEW.os, 'close', lambda fd: (closed.append(fd), real_close(fd))[1]):
            with self.assertRaises(ValueError):
                NEW.atomic_write_text(self.path, failing_write)
        self.assertEqual(closed, [])
        self.assertEqual(self.read(self.path), 'old')
        self.assertEqual(self.leftovers(), [])


class TokenAndConfig(Base):
    def test_token_roundtrip_and_crash_safety(self):
        tok = {'user': 'u', 'access_token': 'abc', 'refresh_token': 'def'}
        with mock.patch.object(NEW, 'TOKEN_FILENAME', os.path.join(self.d, 'gog-token.dat')):
            NEW.save_token(tok)
            self.assertEqual(NEW.load_token(NEW.TOKEN_FILENAME), tok)
            before = self.read(NEW.TOKEN_FILENAME)
            with mock.patch.object(os, 'replace', side_effect=OSError('simulated crash')):
                with self.assertRaises(OSError): NEW.save_token({'user': 'other'})
            self.assertEqual(self.read(NEW.TOKEN_FILENAME), before); self.assertEqual(self.leftovers(), [])

    @unittest.skipIf(os.name == 'nt', 'POSIX permissions')
    def test_token_stays_private(self):
        p = os.path.join(self.d, 'gog-token.dat')
        with mock.patch.object(NEW, 'TOKEN_FILENAME', p):
            NEW.save_token({'a': 1}); os.chmod(p, 0o600); NEW.save_token({'a': 2})
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)

    @unittest.skipIf(os.name == 'nt', 'POSIX permissions')
    def test_new_token_is_private_from_first_creation(self):
        p = os.path.join(self.d, 'new-gog-token.dat')
        with mock.patch.object(NEW, 'TOKEN_FILENAME', p):
            NEW.save_token({'access_token': 'secret'})
        self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600)

    def test_token_loader_does_not_execute_python(self):
        p = os.path.join(self.d, 'malicious-token.dat')
        marker = os.path.join(self.d, 'executed')
        with open(p, 'w', encoding='utf-8') as f:
            f.write("__import__('pathlib').Path(%r).write_text('bad')" % marker)
        with self.assertRaises((ValueError, SyntaxError, TypeError)):
            NEW.load_token(p)
        self.assertFalse(os.path.exists(marker))

    def test_legacy_literal_restores_nested_attrdict(self):
        loaded = NEW._load_legacy_literal("AttrDict(**{'outer': AttrDict(**{'value': 7}), 'rows': [{'x': 1}], 'text': 'keep }) exactly'})")
        self.assertEqual(loaded.outer.value, 7)
        self.assertEqual(loaded.rows[0].x, 1)
        self.assertEqual(loaded.text, 'keep }) exactly')

    def test_config_roundtrip(self):
        p = os.path.join(self.d, 'gog-config.dat')
        with mock.patch.object(NEW, 'CONFIG_FILENAME', p):
            cfg = [NEW.AttrDict(a=1), NEW.AttrDict(b=2)]
            NEW.save_config_file(cfg); self.assertEqual(NEW.load_config_file(p), cfg)

if __name__ == '__main__':
    unittest.main(verbosity=2)
