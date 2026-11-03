"""The download read loop: stall watchdog and read size (CPU usage). Uses fake responses, no network."""
import io
import logging
import threading
import time
import unittest
from unittest import mock
import _bootstrap  # noqa: F401
import requests
import gogrepo_delta as g


class FakeResponse(object):
    def __init__(self, chunks=(), block_after_chunks=False):
        self.chunks, self.block_after_chunks = list(chunks), block_after_chunks
        self.closed = threading.Event()
        self.chunk_sizes_requested = []

    def close(self):
        self.closed.set()

    def iter_content(self, chunk_size=1):
        self.chunk_sizes_requested.append(chunk_size)
        for chunk in self.chunks:
            yield chunk
        if self.block_after_chunks:                      # a server that stops sending
            self.closed.wait(10)
            raise requests.exceptions.ConnectionError('closed by the stall watchdog')


def job_for(path, size):
    job = g._DownloadJob(None, False, None)
    job.sizes[path] = size
    return job


class StallWatchdogTests(unittest.TestCase):
    def test_closes_the_response_when_nothing_arrives(self):
        response = FakeResponse()
        watchdog = g._StallWatchdog(response, 0.2)
        self.assertTrue(response.closed.wait(2))
        watchdog.stop()

    def test_does_not_close_while_data_keeps_arriving(self):
        response = FakeResponse()
        watchdog = g._StallWatchdog(response, 0.3)
        for _ in range(15):                               # 0.75 s of activity, more than twice the timeout
            time.sleep(0.05)
            watchdog.pause()
            watchdog.resume()
        self.assertFalse(response.closed.is_set())
        watchdog.stop()

    def test_time_spent_processing_a_chunk_does_not_count(self):
        response = FakeResponse()
        watchdog = g._StallWatchdog(response, 0.2)
        watchdog.pause()
        time.sleep(0.7)                                   # e.g. a slow disk write
        self.assertFalse(response.closed.is_set())
        watchdog.resume()
        self.assertTrue(response.closed.wait(2))           # but waiting for the next chunk does
        watchdog.stop()

    def test_stop_prevents_closing(self):
        response = FakeResponse()
        watchdog = g._StallWatchdog(response, 0.2)
        watchdog.stop()
        time.sleep(0.6)
        self.assertFalse(response.closed.is_set())

    def test_restarting_does_not_create_threads(self):
        response = FakeResponse()
        watchdog = g._StallWatchdog(response, 60)

        try:
            original_timer = watchdog.timer

            for _ in range(20000):
                watchdog.pause()
                watchdog.resume()

            self.assertIs(watchdog.timer, original_timer)
            self.assertTrue(original_timer.is_alive())
        finally:
            watchdog.stop()

class DownloadLoopTests(unittest.TestCase):
    def test_all_data_is_written_and_accounted(self):
        chunks = [bytes([i % 251]) * 1000 for i in range(50)]
        out, job = io.BytesIO(), job_for('p', 50000)
        written = g._download_ioloop(job, 1, 'p', FakeResponse(chunks), out)
        self.assertEqual(written, 50000)
        self.assertEqual(out.getvalue(), b''.join(chunks))
        self.assertEqual(job.sizes['p'], 0)
        self.assertEqual(sum(sz for _, (sz, _) in job.rates['p']), 50000)

    def test_empty_keep_alive_chunks_are_ignored(self):
        out, job = io.BytesIO(), job_for('p', 3)
        self.assertEqual(g._download_ioloop(job, 1, 'p', FakeResponse([b'', b'abc', b'']), out), 3)

    def test_reads_in_large_pieces(self):
        # 4 KB pieces made the loop spin (and start threads) thousands of times per second
        response = FakeResponse([b'x'])
        g._download_ioloop(job_for('p', 1), 1, 'p', response, io.BytesIO())
        self.assertEqual(response.chunk_sizes_requested, [g.DOWNLOAD_CHUNK_SIZE])
        self.assertGreaterEqual(g.DOWNLOAD_CHUNK_SIZE, 32 * 1024)

    def test_no_thread_is_started_per_chunk(self):
        response = FakeResponse([b'x' * 100] * 5000)
        started = []
        real_start = threading.Thread.start

        def counting_start(thread):
            started.append(thread)
            return real_start(thread)
        with mock.patch.object(threading.Thread, 'start', counting_start):
            g._download_ioloop(job_for('p', 500000), 1, 'p', response, io.BytesIO())
        self.assertLessEqual(len(started), 2, 'threads started for 5000 chunks: %d' % len(started))

    def test_a_stalled_download_is_cut_off_and_reported(self):
        response = FakeResponse([b'a' * 100], block_after_chunks=True)
        with mock.patch.object(g, 'HTTP_TIMEOUT', 0.3), self.assertLogs('gogrepoc', level='ERROR') as logs:
            started = time.time()
            written = g._download_ioloop(job_for('p', 1000), 1, 'p', response, io.BytesIO())
        self.assertEqual(written, 100)                    # what arrived before the stall is kept
        self.assertLess(time.time() - started, 5)
        self.assertTrue(any('server response issue' in m for m in logs.output))

    def test_a_slow_but_steady_download_is_not_cut_off(self):
        def slow_chunks():
            for _ in range(8):
                time.sleep(0.1)                           # 0.8 s in total, more than the 0.3 s timeout
                yield b'z' * 10
        response = FakeResponse()
        response.iter_content = lambda chunk_size=1: slow_chunks()
        with mock.patch.object(g, 'HTTP_TIMEOUT', 0.3):
            self.assertEqual(g._download_ioloop(job_for('p', 80), 1, 'p', response, io.BytesIO()), 80)
        self.assertTrue(response.closed.is_set())


if __name__ == '__main__':
    unittest.main()
