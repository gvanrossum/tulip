from asyncio import subprocess
import asyncio
import signal
import sys
import unittest
if sys.platform != 'win32':
    from asyncio import unix_events

# Program exiting quickly
PROGRAM_EXIT_FAST = [sys.executable, '-c', 'pass']

# Program blocking
PROGRAM_BLOCKED = [sys.executable, '-c', 'import time; time.sleep(3600)']

# Program copying input to output
PROGRAM_CAT = [
    sys.executable, '-c',
    ';'.join(('import sys',
              'data = sys.stdin.buffer.read()',
              'sys.stdout.buffer.write(data)'))]

class SubprocessTests:
    def test_stdin_stdout(self):
        args = PROGRAM_CAT

        @asyncio.coroutine
        def run(data):
            proc = yield from asyncio.create_subprocess_exec(
                                          *args,
                                          stdin=subprocess.PIPE,
                                          stdout=subprocess.PIPE,
                                          loop=self.loop)

            # feed data
            proc.stdin.write(data)
            yield from proc.stdin.drain()
            proc.stdin.close()

            # get output and exitcode
            data = yield from proc.stdout.read()
            exitcode = yield from proc.wait()
            return (exitcode, data)

        task = run(b'some data')
        task = asyncio.wait_for(task, 10.0, loop=self.loop)
        exitcode, stdout = self.loop.run_until_complete(task)
        self.assertEqual(exitcode, 0)
        self.assertEqual(stdout, b'some data')

    def test_communicate(self):
        args = PROGRAM_CAT

        @asyncio.coroutine
        def run(data):
            proc = yield from asyncio.create_subprocess_exec(
                                          *args,
                                          stdin=subprocess.PIPE,
                                          stdout=subprocess.PIPE,
                                          loop=self.loop)
            stdout, stderr = yield from proc.communicate(data)
            return proc.returncode, stdout

        task = run(b'some data')
        task = asyncio.wait_for(task, 10.0, loop=self.loop)
        exitcode, stdout = self.loop.run_until_complete(task)
        self.assertEqual(exitcode, 0)
        self.assertEqual(stdout, b'some data')

    def test_shell(self):
        create = asyncio.create_subprocess_shell('exit 7',
                                                 loop=self.loop)
        proc = self.loop.run_until_complete(create)
        exitcode = self.loop.run_until_complete(proc.wait())
        self.assertEqual(exitcode, 7)

    def test_start_new_session(self):
        # start the new process in a new session
        create = asyncio.create_subprocess_shell('exit 8',
                                                 start_new_session=True,
                                                 loop=self.loop)
        proc = self.loop.run_until_complete(create)
        exitcode = self.loop.run_until_complete(proc.wait())
        self.assertEqual(exitcode, 8)

    def test_kill(self):
        args = PROGRAM_BLOCKED
        create = asyncio.create_subprocess_exec(*args, loop=self.loop)
        proc = self.loop.run_until_complete(create)
        proc.kill()
        returncode = self.loop.run_until_complete(proc.wait())
        if sys.platform == 'win32':
            self.assertIsInstance(returncode, int)
            # expect 1 but sometimes get 0
        else:
            self.assertEqual(-signal.SIGKILL, returncode)

    def test_terminate(self):
        args = PROGRAM_BLOCKED
        create = asyncio.create_subprocess_exec(*args, loop=self.loop)
        proc = self.loop.run_until_complete(create)
        proc.terminate()
        returncode = self.loop.run_until_complete(proc.wait())
        if sys.platform == 'win32':
            self.assertIsInstance(returncode, int)
            # expect 1 but sometimes get 0
        else:
            self.assertEqual(-signal.SIGTERM, returncode)

    @unittest.skipIf(sys.platform == 'win32', "Don't have SIGHUP")
    def test_send_signal(self):
        args = PROGRAM_BLOCKED
        create = asyncio.create_subprocess_exec(*args, loop=self.loop)
        proc = self.loop.run_until_complete(create)
        proc.send_signal(signal.SIGHUP)
        returncode = self.loop.run_until_complete(proc.wait())
        self.assertEqual(-signal.SIGHUP, returncode)

    def test_get_subprocess(self):
        args = PROGRAM_EXIT_FAST

        @asyncio.coroutine
        def run():
            proc = yield from asyncio.create_subprocess_exec(*args,
                                                             loop=self.loop)
            yield from proc.wait()

            popen = proc.get_subprocess()
            popen.wait()
            return (proc, popen)

        proc, popen = self.loop.run_until_complete(run())
        self.assertEqual(popen.returncode, proc.returncode)
        self.assertEqual(popen.pid, proc.pid)


if sys.platform != 'win32':
    # Unix
    class SubprocessWatcherTests(SubprocessTests):
        Watcher = None

        def setUp(self):
            policy = asyncio.get_event_loop_policy()
            self.loop = policy.new_event_loop()

            # ensure that the event loop is passed explicitly in the code
            policy.set_event_loop(None)

            watcher = self.Watcher()
            watcher.attach_loop(self.loop)
            policy.set_child_watcher(watcher)

        def tearDown(self):
            policy = asyncio.get_event_loop_policy()
            policy.set_child_watcher(None)
            self.loop.close()
            policy.set_event_loop(None)

    class SubprocessSafeWatcherTestCase(SubprocessWatcherTests, unittest.TestCase):
        Watcher = unix_events.SafeChildWatcher

    class SubprocessFastWatcherTestCase(SubprocessWatcherTests, unittest.TestCase):
        Watcher = unix_events.FastChildWatcher
else:
    # Windows
    class SubprocessProactorTestCase(SubprocessTests, unittest.TestCase):
        def setUp(self):
            policy = asyncio.get_event_loop_policy()
            self.loop = asyncio.ProactorEventLoop()

            # ensure that the event loop is passed explicitly in the code
            policy.set_event_loop(None)

        def tearDown(self):
            policy = asyncio.get_event_loop_policy()
            self.loop.close()
            policy.set_event_loop(None)


if __name__ == '__main__':
    unittest.main()
